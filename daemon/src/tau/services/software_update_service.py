"""
Software Update Service - GitHub Releases-based OTA update system

Coordinates the entire update workflow including:
- Checking for updates from GitHub Releases
- Downloading and verifying update packages
- Creating backups before updates
- Applying updates with automatic rollback on failure
- Managing version history and rollback capability
"""
import asyncio
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
from packaging import version as pkg_version

import structlog
from sqlalchemy import select, update as sql_update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from tau.models.software_update import (
    Installation,
    VersionHistory,
    AvailableRelease,
    UpdateCheck,
    UpdateConfig,
    DEFAULT_UPDATE_CONFIG,
)
from tau.services.github_client import GitHubClient, GitHubRelease, GitHubAPIError, RateLimitError
from tau.services.backup_manager import (
    BackupManager,
    BackupInfo,
    BackupError,
    InsufficientSpaceError,
)

logger = structlog.get_logger(__name__)

# Update states for state machine
UPDATE_STATES = [
    "idle",
    "checking",
    "downloading",
    "verifying",
    "backing_up",
    "stopping_services",
    "installing",
    "migrating",
    "starting_services",
    "verifying_install",
    "complete",
    "failed",
    "rolling_back",
]

# Services to manage during updates
# Note: Only tau-daemon needs to be restarted - frontend is served via nginx/static build
SERVICES = ["tau-daemon"]

# Operation timeouts (in seconds)
SERVICE_STOP_TIMEOUT = 30.0
SERVICE_START_TIMEOUT = 30.0
PACKAGE_INSTALL_TIMEOUT = 120.0
MIGRATION_TIMEOUT = 60.0
SERVICE_HEALTH_CHECK_TIMEOUT = 10.0


class UpdateError(Exception):
    """Base exception for update errors"""

    pass


class ChecksumMismatchError(UpdateError):
    """Raised when asset checksum verification fails"""

    pass


class InstallationError(UpdateError):
    """Raised when package installation fails"""

    pass


class RollbackError(UpdateError):
    """Raised when rollback fails - requires manual intervention"""

    pass


class SoftwareUpdateService:
    """
    Service for managing software updates via GitHub Releases

    Handles the complete update lifecycle including checking, downloading,
    backup, installation, and rollback.
    """

    def __init__(
        self,
        db_session: AsyncSession,
        app_root: str = "/opt/tau-daemon",
    ):
        """
        Initialize SoftwareUpdateService

        Args:
            db_session: Database session for state management
            app_root: Root directory of the application
        """
        self.db_session = db_session
        self.app_root = Path(app_root)
        self._github_client: Optional[GitHubClient] = None
        self._backup_manager: Optional[BackupManager] = None
        self._current_state = "idle"
        self._update_progress: Dict[str, Any] = {}

    async def _get_config(self, key: str) -> str:
        """Get a configuration value from the database"""
        result = await self.db_session.execute(
            select(UpdateConfig).where(UpdateConfig.key == key)
        )
        config = result.scalar_one_or_none()
        if config:
            return config.value
        # Return default if not in database
        if key in DEFAULT_UPDATE_CONFIG:
            return DEFAULT_UPDATE_CONFIG[key][0]
        return ""

    async def _get_config_bool(self, key: str) -> bool:
        """Get a boolean configuration value from the database"""
        value = await self._get_config(key)
        return value.lower() in ("true", "1", "yes", "on")

    async def _get_config_int(self, key: str, default: int = 0) -> int:
        """Get an integer configuration value from the database"""
        value = await self._get_config(key)
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    async def _set_config(self, key: str, value: str):
        """Set a configuration value in the database"""
        result = await self.db_session.execute(
            select(UpdateConfig).where(UpdateConfig.key == key)
        )
        config = result.scalar_one_or_none()
        if config:
            config.value = value
            config.updated_at = datetime.utcnow()
        else:
            description = DEFAULT_UPDATE_CONFIG.get(key, (None, None))[1]
            new_config = UpdateConfig(
                key=key,
                value=value,
                description=description,
                updated_at=datetime.utcnow(),
            )
            self.db_session.add(new_config)
        await self.db_session.commit()

    async def _get_github_client(self) -> GitHubClient:
        """Get or create GitHub client"""
        if self._github_client is None:
            repo = await self._get_config("github_repo")
            token = await self._get_config("github_token")
            if not repo:
                raise UpdateError("GitHub repository not configured")
            self._github_client = GitHubClient(repo=repo, token=token or None)
        return self._github_client

    async def _get_backup_manager(self) -> BackupManager:
        """Get or create backup manager"""
        if self._backup_manager is None:
            backup_location = await self._get_config("backup_location")
            max_backups = await self._get_config_int("max_backups", default=3)
            min_free_space = await self._get_config_int("min_free_space_mb", default=500)
            self._backup_manager = BackupManager(
                backup_location=backup_location,
                app_root=str(self.app_root),
                max_backups=max_backups,
                min_free_space_mb=min_free_space,
            )
        return self._backup_manager

    async def _get_installation(self) -> Installation:
        """Get or create the installation record"""
        result = await self.db_session.execute(
            select(Installation).where(Installation.id == 1)
        )
        installation = result.scalar_one_or_none()
        if not installation:
            installation = Installation(
                id=1,
                current_version="0.0.0",
                install_method="fresh",
            )
            self.db_session.add(installation)
            await self.db_session.commit()
        return installation

    def _compare_versions(self, v1: str, v2: str) -> int:
        """
        Compare two semantic versions

        Returns:
            -1 if v1 < v2
            0 if v1 == v2
            1 if v1 > v2
        """
        try:
            ver1 = pkg_version.parse(v1)
            ver2 = pkg_version.parse(v2)
            if ver1 < ver2:
                return -1
            elif ver1 > ver2:
                return 1
            return 0
        except Exception:
            # Fallback to string comparison
            if v1 < v2:
                return -1
            elif v1 > v2:
                return 1
            return 0

    async def get_current_version(self) -> str:
        """Get the currently installed version"""
        installation = await self._get_installation()
        return installation.current_version

    async def check_for_updates(self, source: str = "manual") -> Dict[str, Any]:
        """
        Check if updates are available from GitHub Releases

        Args:
            source: Source of check ("manual", "scheduled", "startup")

        Returns:
            Dict with update information:
            {
                "update_available": bool,
                "current_version": str,
                "latest_version": str,
                "release_notes": str,
                "published_at": str,
                "prerelease": bool,
            }
        """
        self._current_state = "checking"
        logger.info("checking_for_updates", source=source)

        try:
            github = await self._get_github_client()
            include_prereleases = await self._get_config_bool("include_prereleases")

            # Fetch releases from GitHub
            releases = await github.get_releases(include_prereleases=include_prereleases)

            # Cache releases in database
            await self._cache_releases(releases)

            # Get current version
            current_version = await self.get_current_version()

            # Find latest release with valid assets
            latest_release = None
            for release in releases:
                if release.asset_url:  # Has downloadable asset
                    latest_release = release
                    break

            if not latest_release:
                result = {
                    "update_available": False,
                    "current_version": current_version,
                    "latest_version": current_version,
                    "release_notes": "",
                    "published_at": None,
                    "prerelease": False,
                }
            else:
                update_available = self._compare_versions(latest_release.version, current_version) > 0
                result = {
                    "update_available": update_available,
                    "current_version": current_version,
                    "latest_version": latest_release.version,
                    "release_notes": latest_release.release_notes,
                    "published_at": latest_release.published_at.isoformat(),
                    "prerelease": latest_release.prerelease,
                }

            # Log the check
            await self._log_update_check(
                source=source,
                result="update_available" if result["update_available"] else "up_to_date",
                current_version=current_version,
                latest_version=result["latest_version"],
            )

            self._current_state = "idle"
            logger.info("update_check_complete", **result)
            return result

        except RateLimitError as e:
            await self._log_update_check(
                source=source,
                result="rate_limited",
                error_message=f"Rate limited until {e.reset_at.isoformat()}",
            )
            self._current_state = "idle"

            # Suggest adding GitHub token for higher rate limits
            has_token = bool(await self._get_config("github_token"))
            token_hint = "" if has_token else " Configure a GitHub token in settings for higher rate limits (5000 req/hour vs 60 req/hour)."

            raise UpdateError(
                f"GitHub API rate limit exceeded. Try again after {e.reset_at.strftime('%H:%M:%S')}.{token_hint}"
            ) from e

        except GitHubAPIError as e:
            await self._log_update_check(
                source=source,
                result="error",
                error_message=str(e),
            )
            self._current_state = "idle"
            raise UpdateError(f"Failed to check for updates: {str(e)}") from e

    async def _cache_releases(self, releases: List[GitHubRelease]):
        """Cache releases in the database"""
        # Clear old cache
        await self.db_session.execute(delete(AvailableRelease))

        # Insert new releases
        for release in releases:
            available_release = AvailableRelease(
                version=release.version,
                tag_name=release.tag_name,
                published_at=release.published_at,
                release_notes=release.release_notes,
                asset_url=release.asset_url,
                asset_name=release.asset_name,
                asset_size=release.asset_size,
                asset_checksum=release.asset_checksum,
                prerelease=release.prerelease,
                draft=release.draft,
                checked_at=datetime.now(timezone.utc),
            )
            self.db_session.add(available_release)

        await self.db_session.commit()

    async def _log_update_check(
        self,
        source: str,
        result: str,
        current_version: Optional[str] = None,
        latest_version: Optional[str] = None,
        error_message: Optional[str] = None,
    ):
        """Log an update check to the database"""
        check = UpdateCheck(
            source=source,
            result=result,
            current_version=current_version,
            latest_version=latest_version,
            error_message=error_message,
        )
        self.db_session.add(check)
        await self.db_session.commit()

    async def get_available_releases(self) -> List[Dict[str, Any]]:
        """Get cached available releases"""
        result = await self.db_session.execute(
            select(AvailableRelease).order_by(AvailableRelease.published_at.desc())
        )
        releases = result.scalars().all()

        return [
            {
                "version": r.version,
                "tag_name": r.tag_name,
                "published_at": r.published_at.isoformat(),
                "release_notes": r.release_notes,
                "asset_url": r.asset_url,
                "asset_name": r.asset_name,
                "asset_size": r.asset_size,
                "prerelease": r.prerelease,
                "has_asset": r.asset_url is not None,
            }
            for r in releases
        ]

    async def get_update_status(self) -> Dict[str, Any]:
        """
        Get comprehensive update status

        Returns:
            Dict with current status information
        """
        installation = await self._get_installation()

        # Get latest cached release
        result = await self.db_session.execute(
            select(AvailableRelease)
            .where(AvailableRelease.asset_url.isnot(None))
            .order_by(AvailableRelease.published_at.desc())
            .limit(1)
        )
        latest_release = result.scalar_one_or_none()

        update_available = False
        available_version = None
        release_notes = None

        if latest_release:
            update_available = self._compare_versions(latest_release.version, installation.current_version) > 0
            if update_available:
                available_version = latest_release.version
                release_notes = latest_release.release_notes

        # Get last check time
        check_result = await self.db_session.execute(
            select(UpdateCheck).order_by(UpdateCheck.checked_at.desc()).limit(1)
        )
        last_check = check_result.scalar_one_or_none()

        return {
            "current_version": installation.current_version,
            "installed_at": installation.installed_at.isoformat(),
            "install_method": installation.install_method,
            "update_available": update_available,
            "available_version": available_version,
            "release_notes": release_notes,
            "last_check_at": last_check.checked_at.isoformat() if last_check else None,
            "state": self._current_state,
            "progress": self._update_progress,
        }

    async def apply_update(
        self,
        target_version: str,
        progress_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Apply an update to a specific version

        Args:
            target_version: Version to update to
            progress_callback: Optional callback(state, progress, message)

        Returns:
            Dict with update result

        Raises:
            UpdateError: If update fails (automatic rollback attempted)
        """
        logger.info("starting_update", target_version=target_version)

        # Get release info
        result = await self.db_session.execute(
            select(AvailableRelease).where(AvailableRelease.version == target_version)
        )
        release = result.scalar_one_or_none()

        if not release:
            raise UpdateError(f"Release {target_version} not found. Run check first.")

        if not release.asset_url:
            raise UpdateError(f"Release {target_version} has no downloadable asset.")

        current_version = await self.get_current_version()
        backup_info: Optional[BackupInfo] = None
        download_path: Optional[Path] = None

        try:
            # Step 1: Download asset
            self._current_state = "downloading"
            self._update_progress = {"stage": "downloading", "percent": 0}
            if progress_callback:
                progress_callback("downloading", 0, "Downloading update package...")

            github = await self._get_github_client()
            download_dir = Path(tempfile.gettempdir()) / "tau-updates"
            download_dir.mkdir(parents=True, exist_ok=True)
            download_path = download_dir / (release.asset_name or f"{target_version}.deb")

            def download_progress(downloaded: int, total: int):
                if total > 0:
                    percent = int(downloaded / total * 100)
                    self._update_progress = {"stage": "downloading", "percent": percent}
                    if progress_callback:
                        progress_callback("downloading", percent, f"Downloaded {downloaded}/{total} bytes")

            await github.download_asset(
                asset_url=release.asset_url,
                destination=download_path,
                expected_checksum=release.asset_checksum,
                progress_callback=download_progress,
            )

            # Step 2: Verify checksum (already done during download if checksum provided)
            self._current_state = "verifying"
            self._update_progress = {"stage": "verifying", "percent": 100}
            if progress_callback:
                progress_callback("verifying", 100, "Package verified")

            # Step 3: Create backup
            self._current_state = "backing_up"
            self._update_progress = {"stage": "backing_up", "percent": 0}
            if progress_callback:
                progress_callback("backing_up", 0, "Creating backup...")

            backup_manager = await self._get_backup_manager()

            def backup_progress(stage: str, percent: int):
                self._update_progress = {"stage": "backing_up", "percent": percent}
                if progress_callback:
                    progress_callback("backing_up", percent, f"Backup: {stage}")

            installation = await self._get_installation()
            backup_info = await backup_manager.create_backup(
                version=current_version,
                commit_sha=installation.commit_sha,
                progress_callback=backup_progress,
            )

            # Record in version history
            version_history = VersionHistory(
                version=current_version,
                commit_sha=installation.commit_sha,
                installed_at=installation.installed_at,
                uninstalled_at=datetime.now(timezone.utc),
                backup_path=backup_info.backup_path,
                backup_valid=True,
                release_notes=None,
            )
            self.db_session.add(version_history)
            await self.db_session.commit()

            # Step 4: Stop services
            self._current_state = "stopping_services"
            self._update_progress = {"stage": "stopping_services", "percent": 0}
            if progress_callback:
                progress_callback("stopping_services", 0, "Stopping services...")

            await self._stop_services()

            # Step 5: Install package
            self._current_state = "installing"
            self._update_progress = {"stage": "installing", "percent": 0}
            if progress_callback:
                progress_callback("installing", 0, "Installing update...")

            await self._install_package(download_path)

            # Step 6: Run migrations
            self._current_state = "migrating"
            self._update_progress = {"stage": "migrating", "percent": 0}
            if progress_callback:
                progress_callback("migrating", 0, "Running database migrations...")

            await self._run_migrations()

            # Step 7: Start services
            self._current_state = "starting_services"
            self._update_progress = {"stage": "starting_services", "percent": 0}
            if progress_callback:
                progress_callback("starting_services", 0, "Starting services...")

            await self._start_services()

            # Step 8: Verify installation
            self._current_state = "verifying_install"
            self._update_progress = {"stage": "verifying_install", "percent": 0}
            if progress_callback:
                progress_callback("verifying_install", 0, "Verifying installation...")

            verify_after = await self._get_config_bool("verify_after_install")
            if verify_after:
                if not await self._verify_installation(target_version):
                    raise InstallationError("Installation verification failed")

            # Step 9: Update installation record
            installation.current_version = target_version
            installation.installed_at = datetime.now(timezone.utc)
            installation.install_method = "update"
            await self.db_session.commit()

            # Step 10: Prune old backups
            await backup_manager.prune_old_backups()

            # Cleanup download
            if download_path and download_path.exists():
                download_path.unlink()

            self._current_state = "complete"
            self._update_progress = {"stage": "complete", "percent": 100}
            if progress_callback:
                progress_callback("complete", 100, "Update complete!")

            logger.info("update_complete", from_version=current_version, to_version=target_version)

            return {
                "success": True,
                "from_version": current_version,
                "to_version": target_version,
                "message": f"Successfully updated from {current_version} to {target_version}",
            }

        except Exception as e:
            logger.error("update_failed", error=str(e), target_version=target_version)

            # Attempt rollback
            if backup_info and backup_info.backup_path:
                self._current_state = "rolling_back"
                self._update_progress = {"stage": "rolling_back", "percent": 0}
                if progress_callback:
                    progress_callback("rolling_back", 0, f"Update failed: {str(e)}. Rolling back...")

                try:
                    await self._perform_rollback(backup_info.backup_path)
                    if progress_callback:
                        progress_callback("failed", 100, f"Update failed. Rolled back to {current_version}")
                except RollbackError as re:
                    logger.critical("rollback_failed", error=str(re))
                    if progress_callback:
                        progress_callback("failed", 100, f"CRITICAL: Rollback failed! {str(re)}")
                    raise RollbackError(f"Update and rollback both failed: {str(re)}") from e

            # Cleanup download
            if download_path and download_path.exists():
                download_path.unlink(missing_ok=True)

            self._current_state = "failed"
            raise UpdateError(f"Update failed: {str(e)}") from e

    async def rollback(self, target_version: Optional[str] = None) -> Dict[str, Any]:
        """
        Rollback to a previous version

        Args:
            target_version: Specific version to rollback to, or None for most recent backup

        Returns:
            Dict with rollback result

        Raises:
            UpdateError: If no valid backup available
            RollbackError: If rollback fails
        """
        current_version = await self.get_current_version()
        backup_manager = await self._get_backup_manager()

        # Find backup
        if target_version:
            backup_info = await backup_manager.get_backup_for_version(target_version)
        else:
            backups = await backup_manager.list_backups()
            backup_info = next((b for b in backups if b.valid), None)

        if not backup_info:
            raise UpdateError(
                f"No valid backup found for version {target_version}" if target_version else "No valid backups available"
            )

        logger.info("starting_rollback", from_version=current_version, to_version=backup_info.version)

        self._current_state = "rolling_back"
        self._update_progress = {"stage": "rolling_back", "percent": 0}

        try:
            await self._perform_rollback(backup_info.backup_path)

            # Update installation record
            installation = await self._get_installation()
            installation.current_version = backup_info.version
            installation.installed_at = datetime.now(timezone.utc)
            installation.install_method = "rollback"
            await self.db_session.commit()

            self._current_state = "idle"
            self._update_progress = {}

            logger.info("rollback_complete", from_version=current_version, to_version=backup_info.version)

            return {
                "success": True,
                "from_version": current_version,
                "to_version": backup_info.version,
                "message": f"Successfully rolled back from {current_version} to {backup_info.version}",
            }

        except Exception as e:
            self._current_state = "failed"
            logger.critical("rollback_failed", error=str(e))
            raise RollbackError(f"Rollback failed: {str(e)}. Manual intervention required.") from e

    async def _perform_rollback(self, backup_path: str):
        """Perform the actual rollback operation"""
        backup_manager = await self._get_backup_manager()

        # Stop services
        await self._stop_services()

        # Restore from backup
        await backup_manager.restore_backup(backup_path)

        # Start services
        await self._start_services()

    async def _stop_services(self):
        """Stop lighting control services"""
        for service in SERVICES:
            try:
                process = await asyncio.create_subprocess_exec(
                    "systemctl",
                    "stop",
                    service,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(process.communicate(), timeout=SERVICE_STOP_TIMEOUT)
                logger.info("service_stopped", service=service)
            except asyncio.TimeoutError:
                logger.warning("service_stop_timeout", service=service, timeout=SERVICE_STOP_TIMEOUT)
            except Exception as e:
                logger.warning("service_stop_failed", service=service, error=str(e))

    async def _start_services(self):
        """Start lighting control services"""
        for service in SERVICES:
            try:
                process = await asyncio.create_subprocess_exec(
                    "systemctl",
                    "start",
                    service,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=SERVICE_START_TIMEOUT
                )

                if process.returncode != 0:
                    raise InstallationError(f"Failed to start {service}: {stderr.decode()}")

                logger.info("service_started", service=service)
            except asyncio.TimeoutError:
                raise InstallationError(f"Timeout starting {service} after {SERVICE_START_TIMEOUT}s")

    async def _install_package(self, package_path: Path):
        """Install a .deb package"""
        try:
            process = await asyncio.create_subprocess_exec(
                "dpkg",
                "-i",
                str(package_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=PACKAGE_INSTALL_TIMEOUT
            )

            if process.returncode != 0:
                # Try to fix dependencies
                fix_process = await asyncio.create_subprocess_exec(
                    "apt-get",
                    "install",
                    "-f",
                    "-y",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                fix_stdout, fix_stderr = await asyncio.wait_for(
                    fix_process.communicate(), timeout=PACKAGE_INSTALL_TIMEOUT
                )

                if fix_process.returncode != 0:
                    raise InstallationError(
                        f"Package installation failed: {stderr.decode()}. "
                        f"Dependency fix also failed: {fix_stderr.decode()}"
                    )

            logger.info("package_installed", path=str(package_path))

        except asyncio.TimeoutError:
            raise InstallationError(f"Package installation timed out after {PACKAGE_INSTALL_TIMEOUT}s")

    async def _run_migrations(self):
        """Run database migrations"""
        try:
            process = await asyncio.create_subprocess_exec(
                "alembic",
                "upgrade",
                "head",
                cwd=str(self.app_root / "daemon"),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=MIGRATION_TIMEOUT
            )

            if process.returncode != 0:
                logger.warning("migration_warning", stderr=stderr.decode())

            logger.info("migrations_complete")

        except asyncio.TimeoutError:
            logger.warning("migration_timeout")
        except Exception as e:
            logger.warning("migration_error", error=str(e))

    async def _verify_installation(self, expected_version: str) -> bool:
        """Verify the installation is working correctly"""
        # Check services are running
        for service in SERVICES:
            try:
                process = await asyncio.create_subprocess_exec(
                    "systemctl",
                    "is-active",
                    service,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await process.communicate()
                if stdout.decode().strip() != "active":
                    logger.warning("service_not_active", service=service)
                    return False
            except Exception:
                return False

        return True

    async def recover_from_interrupted_update(self) -> Dict[str, Any]:
        """
        Recover from an interrupted update on daemon startup.

        Called when the daemon starts to handle cases where an update was in progress
        when the daemon crashed or was restarted. This method:
        1. Checks if an update was in progress
        2. Attempts to complete or rollback the update
        3. Cleans up any partial state

        Returns:
            Dict with recovery status and actions taken
        """
        logger.info("checking_for_interrupted_update")

        # Check if we were in the middle of an update
        if self._current_state not in ["idle", "complete", "failed"]:
            # State was persisted - we were interrupted
            interrupted_state = self._current_state
            logger.warning("interrupted_update_detected", state=interrupted_state)

            recovery_actions = []

            try:
                # Clean up any partial downloads
                download_dir = Path(tempfile.gettempdir()) / "tau-updates"
                if download_dir.exists():
                    import shutil
                    shutil.rmtree(download_dir, ignore_errors=True)
                    recovery_actions.append("cleaned_partial_downloads")

                # If we were past the backup stage but before completion,
                # check if we need to rollback
                if interrupted_state in [
                    "stopping_services",
                    "installing",
                    "migrating",
                    "starting_services",
                    "verifying_install",
                ]:
                    # Check if services are running
                    services_healthy = await self._verify_installation("")

                    if not services_healthy:
                        # Attempt to start services
                        logger.info("attempting_service_recovery")
                        try:
                            await self._start_services()
                            recovery_actions.append("restarted_services")
                        except Exception as e:
                            logger.error("service_recovery_failed", error=str(e))

                            # Check if we should auto-rollback
                            should_rollback = await self._get_config_bool("rollback_on_service_failure")
                            if should_rollback:
                                # Find the most recent backup
                                backup_manager = await self._get_backup_manager()
                                backups = await backup_manager.list_backups()
                                valid_backup = next((b for b in backups if b.valid), None)

                                if valid_backup:
                                    logger.warning(
                                        "auto_rollback_triggered",
                                        target_version=valid_backup.version,
                                    )
                                    await self._perform_rollback(valid_backup.backup_path)
                                    recovery_actions.append(f"rolled_back_to_{valid_backup.version}")

                # Reset state
                self._current_state = "idle"
                self._update_progress = {}
                recovery_actions.append("reset_state")

                return {
                    "recovered": True,
                    "interrupted_state": interrupted_state,
                    "actions": recovery_actions,
                }

            except Exception as e:
                logger.error("update_recovery_failed", error=str(e))
                self._current_state = "failed"
                return {
                    "recovered": False,
                    "interrupted_state": interrupted_state,
                    "error": str(e),
                }

        # No interrupted update
        self._current_state = "idle"
        return {"recovered": False, "message": "No interrupted update detected"}

    async def get_version_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get version history with rollback capability

        Args:
            limit: Maximum entries to return

        Returns:
            List of version history entries
        """
        result = await self.db_session.execute(
            select(VersionHistory)
            .order_by(VersionHistory.installed_at.desc())
            .limit(limit)
        )
        history = result.scalars().all()

        current_version = await self.get_current_version()

        entries = []
        for h in history:
            entries.append({
                "version": h.version,
                "installed_at": h.installed_at.isoformat(),
                "uninstalled_at": h.uninstalled_at.isoformat() if h.uninstalled_at else None,
                "backup_path": h.backup_path,
                "backup_valid": h.backup_valid,
                "can_rollback": h.backup_valid and h.backup_path is not None,
                "is_current": h.version == current_version,
                "release_notes": h.release_notes,
            })

        return entries

    async def get_config(self) -> Dict[str, Any]:
        """Get all update configuration"""
        result = await self.db_session.execute(select(UpdateConfig))
        configs = result.scalars().all()

        config_dict = {}
        for c in configs:
            # Don't expose sensitive values
            if c.key == "github_token" and c.value:
                config_dict[c.key] = "***configured***"
            else:
                config_dict[c.key] = c.value

        return config_dict

    async def update_config(self, key: str, value: str) -> Dict[str, Any]:
        """
        Update a configuration value

        Args:
            key: Configuration key
            value: New value

        Returns:
            Updated configuration
        """
        if key not in DEFAULT_UPDATE_CONFIG and key != "github_token":
            raise UpdateError(f"Unknown configuration key: {key}")

        await self._set_config(key, value)

        # Clear cached clients if relevant config changed
        if key in ["github_repo", "github_token"]:
            self._github_client = None
        elif key in ["backup_location", "max_backups", "min_free_space_mb"]:
            self._backup_manager = None

        return await self.get_config()

    async def get_backups(self) -> List[Dict[str, Any]]:
        """Get list of available backups"""
        backup_manager = await self._get_backup_manager()
        backups = await backup_manager.list_backups()

        return [
            {
                "version": b.version,
                "backup_path": b.backup_path,
                "created_at": b.created_at.isoformat(),
                "size_bytes": b.size_bytes,
                "size_mb": round(b.size_bytes / (1024 * 1024), 2),
                "valid": b.valid,
            }
            for b in backups
        ]
