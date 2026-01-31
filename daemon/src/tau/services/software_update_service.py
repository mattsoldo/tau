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
import os
import shutil
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
    SoftwareUpdateJob,
    DEFAULT_UPDATE_CONFIG,
)
from tau.services.github_client import GitHubClient, GitHubRelease, GitHubAPIError, RateLimitError
from tau.services.backup_manager import (
    BackupManager,
    BackupInfo,
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

# Persisted job states
UPDATE_JOB_ACTIVE_STATES = {"queued", "running", "rolling_back"}
UPDATE_JOB_TERMINAL_STATES = {"complete", "failed"}

# Services to manage during updates
# Note: Only tau-daemon needs to be restarted - frontend is served via nginx/static build
SERVICES = ["tau-daemon"]

# Operation timeouts (in seconds)
SERVICE_STOP_TIMEOUT = 30.0
SERVICE_START_TIMEOUT = 30.0
PACKAGE_INSTALL_TIMEOUT = 120.0
DEPENDENCY_UPDATE_TIMEOUT = 300.0
MIGRATION_TIMEOUT = 60.0
SERVICE_HEALTH_CHECK_TIMEOUT = 10.0
FRONTEND_BUILD_TIMEOUT = 600.0


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

    async def _get_latest_job(self) -> Optional[SoftwareUpdateJob]:
        """Get the most recent software update job."""
        result = await self.db_session.execute(
            select(SoftwareUpdateJob).order_by(SoftwareUpdateJob.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_active_job(self) -> Optional[SoftwareUpdateJob]:
        """Get the most recent active update job, if any."""
        result = await self.db_session.execute(
            select(SoftwareUpdateJob)
            .where(SoftwareUpdateJob.state.in_(UPDATE_JOB_ACTIVE_STATES))
            .order_by(SoftwareUpdateJob.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def has_active_job(self) -> bool:
        """Return True if an update job is currently active."""
        return await self._get_active_job() is not None

    async def start_update_job(self, operation: str, target_version: Optional[str]) -> SoftwareUpdateJob:
        """Create a new update job if none are active."""
        if await self.has_active_job():
            raise UpdateError("Another update is already in progress.")
        return await self._create_update_job(operation, target_version)

    async def _create_update_job(self, operation: str, target_version: Optional[str]) -> SoftwareUpdateJob:
        """Create a persisted update job record."""
        from_version = await self.get_current_version()
        job = SoftwareUpdateJob(
            operation=operation,
            target_version=target_version,
            from_version=from_version,
            state="queued",
            stage="queued",
            progress_percent=0,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.db_session.add(job)
        await self.db_session.commit()
        return job

    async def _update_job(
        self,
        job_id: int,
        *,
        state: Optional[str] = None,
        stage: Optional[str] = None,
        progress_percent: Optional[int] = None,
        message: Optional[str] = None,
        error_message: Optional[str] = None,
        to_version: Optional[str] = None,
        completed: bool = False,
    ) -> None:
        """Persist update job progress."""
        values: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
        if state is not None:
            values["state"] = state
        if stage is not None:
            values["stage"] = stage
        if progress_percent is not None:
            values["progress_percent"] = progress_percent
        if message is not None:
            values["message"] = message
        if error_message is not None:
            values["error_message"] = error_message
        if to_version is not None:
            values["to_version"] = to_version
        if completed:
            values["completed_at"] = datetime.now(timezone.utc)

        await self.db_session.execute(
            sql_update(SoftwareUpdateJob).where(SoftwareUpdateJob.id == job_id).values(**values)
        )
        await self.db_session.commit()

    async def _set_state(
        self,
        state: str,
        *,
        stage: Optional[str] = None,
        percent: Optional[int] = None,
        message: Optional[str] = None,
        error_message: Optional[str] = None,
        job_id: Optional[int] = None,
    ) -> None:
        """Update in-memory and persisted state."""
        self._current_state = state
        progress: Dict[str, Any] = {"stage": stage or state}
        if percent is not None:
            progress["percent"] = percent
        if message is not None:
            progress["message"] = message
        self._update_progress = progress

        if job_id is not None:
            if state in UPDATE_JOB_ACTIVE_STATES or state in UPDATE_JOB_TERMINAL_STATES:
                job_state = state
            else:
                job_state = "running"
            await self._update_job(
                job_id,
                state=job_state,
                stage=stage or state,
                progress_percent=percent,
                message=message,
                error_message=error_message,
                completed=job_state in UPDATE_JOB_TERMINAL_STATES,
            )

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
            config.updated_at = datetime.now(timezone.utc)
        else:
            description = DEFAULT_UPDATE_CONFIG.get(key, (None, None))[1]
            new_config = UpdateConfig(
                key=key,
                value=value,
                description=description,
                updated_at=datetime.now(timezone.utc),
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

    async def _preflight_check(self) -> None:
        """Run preflight checks before starting an update."""
        backup_location = Path(await self._get_config("backup_location"))

        try:
            if not backup_location.exists():
                backup_location.mkdir(parents=True, exist_ok=True)
            if not os.access(backup_location, os.W_OK):
                raise UpdateError(
                    f"Backup directory is not writable: {backup_location}. "
                    "Update the backup_location setting or fix permissions."
                )
        except OSError as e:
            raise UpdateError(
                f"Failed to access backup directory {backup_location}: {str(e)}. "
                "Update the backup_location setting or fix permissions."
            ) from e

        backup_manager = await self._get_backup_manager()
        if not await backup_manager.check_space_for_backup():
            raise UpdateError(
                "Insufficient disk space for backup. "
                "Free up space or adjust min_free_space_mb."
            )

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
                result="error",
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

        job_state = "idle"
        job_progress: Dict[str, Any] = {}

        latest_job = await self._get_latest_job()
        if latest_job:
            if latest_job.state in UPDATE_JOB_ACTIVE_STATES:
                job_state = latest_job.stage or latest_job.state
                job_progress = {
                    "stage": latest_job.stage or latest_job.state,
                    "percent": latest_job.progress_percent or 0,
                    "message": latest_job.message,
                }
            elif latest_job.state in UPDATE_JOB_TERMINAL_STATES:
                job_state = latest_job.state
                job_progress = {
                    "stage": latest_job.stage or latest_job.state,
                    "percent": latest_job.progress_percent or 100,
                    "message": latest_job.message or latest_job.error_message,
                }

        return {
            "current_version": installation.current_version,
            "installed_at": installation.installed_at.isoformat(),
            "install_method": installation.install_method,
            "update_available": update_available,
            "available_version": available_version,
            "release_notes": release_notes,
            "last_check_at": last_check.checked_at.isoformat() if last_check else None,
            "state": job_state,
            "progress": job_progress,
        }

    async def apply_update(
        self,
        target_version: str,
        progress_callback: Optional[callable] = None,
        job_id: Optional[int] = None,
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
            if job_id is not None:
                await self._set_state(
                    "failed",
                    stage="failed",
                    percent=100,
                    message="Update failed",
                    error_message=f"Release {target_version} not found. Run check first.",
                    job_id=job_id,
                )
            raise UpdateError(f"Release {target_version} not found. Run check first.")

        if not release.asset_url:
            if job_id is not None:
                await self._set_state(
                    "failed",
                    stage="failed",
                    percent=100,
                    message="Update failed",
                    error_message=f"Release {target_version} has no downloadable asset.",
                    job_id=job_id,
                )
            raise UpdateError(f"Release {target_version} has no downloadable asset.")

        if release.asset_name and release.asset_name.endswith(".deb") and os.geteuid() != 0:
            if job_id is not None:
                await self._set_state(
                    "failed",
                    stage="failed",
                    percent=100,
                    message="Update failed",
                    error_message=(
                        "Debian package installs require root privileges. "
                        "Publish a tarball release asset or configure a privileged installer."
                    ),
                    job_id=job_id,
                )
            raise UpdateError(
                "Debian package installs require root privileges. "
                "Publish a tarball release asset or configure a privileged installer."
            )

        current_version = await self.get_current_version()
        backup_info: Optional[BackupInfo] = None
        download_path: Optional[Path] = None

        try:
            await self._preflight_check()

            # Step 1: Download asset
            await self._set_state(
                "downloading",
                stage="downloading",
                percent=0,
                message="Downloading update package...",
                job_id=job_id,
            )
            if progress_callback:
                progress_callback("downloading", 0, "Downloading update package...")

            github = await self._get_github_client()
            download_dir = Path(tempfile.gettempdir()) / "tau-updates"
            download_dir.mkdir(parents=True, exist_ok=True)
            download_path = download_dir / (release.asset_name or f"{target_version}.tar.gz")

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
            await self._set_state(
                "verifying",
                stage="verifying",
                percent=100,
                message="Package verified",
                job_id=job_id,
            )
            if progress_callback:
                progress_callback("verifying", 100, "Package verified")

            # Step 3: Create backup
            await self._set_state(
                "backing_up",
                stage="backing_up",
                percent=0,
                message="Creating backup...",
                job_id=job_id,
            )
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

            await self._set_state(
                "backing_up",
                stage="backing_up",
                percent=100,
                message="Backup complete",
                job_id=job_id,
            )

            # Get current schema revision before upgrade
            pre_upgrade_schema = await self._get_current_schema_revision()

            # Record in version history (with schema revision for future downgrades)
            version_history = VersionHistory(
                version=current_version,
                commit_sha=installation.commit_sha,
                installed_at=installation.installed_at,
                uninstalled_at=datetime.now(timezone.utc),
                backup_path=backup_info.backup_path,
                backup_valid=True,
                release_notes=None,
                schema_revision=pre_upgrade_schema,
            )
            self.db_session.add(version_history)
            await self.db_session.commit()

            # Step 4: Skip stopping services
            # Note: We can't stop tau-daemon from within itself
            # The scheduled restart will handle stopping and starting with new code
            await self._set_state(
                "installing",
                stage="installing",
                percent=0,
                message="Preparing installation...",
                job_id=job_id,
            )
            if progress_callback:
                progress_callback("installing", 0, "Preparing installation...")

            logger.info("skipping_service_stop", reason="will_restart_after_install")

            # Step 5: Install package
            await self._set_state(
                "installing",
                stage="installing",
                percent=0,
                message="Installing update...",
                job_id=job_id,
            )
            if progress_callback:
                progress_callback("installing", 0, "Installing update...")

            await self._install_package(download_path)

            is_tarball = download_path.name.endswith(".tar.gz") or download_path.name.endswith(".tgz")

            if is_tarball:
                await self._set_state(
                    "installing",
                    stage="installing",
                    percent=25,
                    message="Updating backend dependencies...",
                    job_id=job_id,
                )
                if progress_callback:
                    progress_callback("installing", 25, "Updating backend dependencies...")

                await self._update_backend_dependencies()

            # Step 6: Build frontend static assets
            await self._set_state(
                "installing",
                stage="installing",
                percent=60,
                message="Building frontend...",
                job_id=job_id,
            )
            if progress_callback:
                progress_callback("installing", 60, "Building frontend...")

            await self._build_frontend()

            await self._set_state(
                "installing",
                stage="installing",
                percent=100,
                message="Install complete",
                job_id=job_id,
            )

            # Step 7: Run migrations
            await self._set_state(
                "migrating",
                stage="migrating",
                percent=0,
                message="Running database migrations...",
                job_id=job_id,
            )
            if progress_callback:
                progress_callback("migrating", 0, "Running database migrations...")

            await self._run_migrations()

            # Step 8: Schedule service restart
            # Note: We can't restart tau-daemon from within itself, so we schedule a delayed restart
            await self._set_state(
                "starting_services",
                stage="starting_services",
                percent=0,
                message="Scheduling service restart...",
                job_id=job_id,
            )
            if progress_callback:
                progress_callback("starting_services", 0, "Scheduling service restart...")

            # Spawn a background process that will restart services after this process exits
            self._schedule_restart()

            # Step 9: Verify installation (skip service checks since we're restarting)
            await self._set_state(
                "verifying_install",
                stage="verifying_install",
                percent=0,
                message="Verifying installation...",
                job_id=job_id,
            )
            if progress_callback:
                progress_callback("verifying_install", 0, "Verifying installation...")

            # Skip verification since services will restart momentarily
            logger.info("skipping_verification", reason="services_restarting")

            # Get current schema revision after migrations
            current_schema_revision = await self._get_current_schema_revision()

            # Step 10: Update installation record
            installation.current_version = target_version
            installation.installed_at = datetime.now(timezone.utc)
            installation.install_method = "update"
            installation.schema_revision = current_schema_revision
            await self.db_session.commit()

            if job_id is not None:
                await self._update_job(job_id, to_version=target_version)

            # Step 11: Prune old backups
            await backup_manager.prune_old_backups()

            # Cleanup download
            if download_path and download_path.exists():
                download_path.unlink()

            await self._set_state(
                "complete",
                stage="complete",
                percent=100,
                message="Update complete!",
                job_id=job_id,
            )
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
                await self._set_state(
                    "rolling_back",
                    stage="rolling_back",
                    percent=0,
                    message=f"Update failed: {str(e)}. Rolling back...",
                    job_id=job_id,
                )
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
                    if job_id is not None:
                        await self._update_job(
                            job_id,
                            state="failed",
                            stage="rolling_back",
                            progress_percent=100,
                            error_message=str(re),
                            completed=True,
                        )
                    raise RollbackError(f"Update and rollback both failed: {str(re)}") from e

            # Cleanup download
            if download_path and download_path.exists():
                download_path.unlink(missing_ok=True)

            await self._set_state(
                "failed",
                stage="failed",
                percent=100,
                message="Update failed",
                error_message=str(e),
                job_id=job_id,
            )
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

        # Look up schema revision for the target version from version history
        target_schema_revision = await self._get_version_schema_revision(backup_info.version)

        logger.info(
            "starting_rollback",
            from_version=current_version,
            to_version=backup_info.version,
            target_schema_revision=target_schema_revision
        )

        self._current_state = "rolling_back"
        self._update_progress = {"stage": "rolling_back", "percent": 0}

        try:
            await self._perform_rollback(
                backup_info.backup_path,
                target_schema_revision=target_schema_revision
            )

            # Update installation record
            installation = await self._get_installation()
            installation.current_version = backup_info.version
            installation.installed_at = datetime.now(timezone.utc)
            installation.install_method = "rollback"
            installation.schema_revision = target_schema_revision
            await self.db_session.commit()

            self._current_state = "idle"
            self._update_progress = {}

            logger.info("rollback_complete", from_version=current_version, to_version=backup_info.version)

            return {
                "success": True,
                "from_version": current_version,
                "to_version": backup_info.version,
                "schema_revision": target_schema_revision,
                "message": f"Successfully rolled back from {current_version} to {backup_info.version}",
            }

        except Exception as e:
            self._current_state = "failed"
            logger.critical("rollback_failed", error=str(e))
            raise RollbackError(f"Rollback failed: {str(e)}. Manual intervention required.") from e

    async def _get_version_schema_revision(self, version: str) -> Optional[str]:
        """
        Look up the schema revision for a specific version from version history.

        Args:
            version: The version to look up

        Returns:
            Schema revision string or None if not found
        """
        try:
            result = await self.db_session.execute(
                select(VersionHistory.schema_revision)
                .where(VersionHistory.version == version)
                .order_by(VersionHistory.installed_at.desc())
                .limit(1)
            )
            row = result.scalar_one_or_none()
            return row
        except Exception as e:
            logger.warning("get_version_schema_revision_error", version=version, error=str(e))
            return None

    async def downgrade(
        self,
        target_version: str,
        progress_callback=None
    ) -> Dict[str, Any]:
        """
        Downgrade to a specific older version.

        This method handles downgrading to any available release, not just
        versions with local backups. It will:
        1. Check for local backup first (use rollback if available)
        2. Otherwise download the release from GitHub
        3. Downgrade database schema BEFORE installing old code
        4. Install the older version
        5. Restart services

        Args:
            target_version: Version to downgrade to
            progress_callback: Optional callback(state, progress, message)

        Returns:
            Dict with downgrade result

        Raises:
            UpdateError: If downgrade fails
        """
        current_version = await self.get_current_version()

        # Validate we're actually downgrading
        try:
            if pkg_version.parse(target_version) >= pkg_version.parse(current_version):
                raise UpdateError(
                    f"Target version {target_version} is not older than current {current_version}. "
                    "Use apply_update for upgrades."
                )
        except Exception as e:
            if "UpdateError" in str(type(e)):
                raise
            # Version parsing failed, continue anyway
            logger.warning("version_comparison_failed", error=str(e))

        logger.info(
            "starting_downgrade",
            from_version=current_version,
            to_version=target_version
        )

        # Check if we have a local backup for this version
        backup_manager = await self._get_backup_manager()
        backup_info = await backup_manager.get_backup_for_version(target_version)

        if backup_info and backup_info.valid:
            # Use existing rollback functionality
            logger.info("downgrade_using_backup", version=target_version)
            return await self.rollback(target_version)

        # No backup - need to download from GitHub
        logger.info("downgrade_downloading_release", version=target_version)

        # Get release info from cache or fetch
        result = await self.db_session.execute(
            select(AvailableRelease).where(AvailableRelease.version == target_version)
        )
        release = result.scalar_one_or_none()

        if not release:
            # Try to fetch releases to find it
            await self.check_for_updates("manual")
            result = await self.db_session.execute(
                select(AvailableRelease).where(AvailableRelease.version == target_version)
            )
            release = result.scalar_one_or_none()

        if not release:
            raise UpdateError(
                f"Release {target_version} not found in GitHub releases. "
                "Cannot downgrade to unavailable versions."
            )

        if not release.asset_url:
            raise UpdateError(f"Release {target_version} has no downloadable asset.")

        if release.asset_name and release.asset_name.endswith(".deb") and os.geteuid() != 0:
            raise UpdateError(
                "Debian package installs require root privileges. "
                "Publish a tarball release asset or configure a privileged installer."
            )

        # Get schema revision for target version (from release or lookup)
        target_schema_revision = release.schema_revision
        if not target_schema_revision:
            # Try to look up from version history
            target_schema_revision = await self._get_version_schema_revision(target_version)

        download_path: Optional[Path] = None
        current_backup: Optional[BackupInfo] = None

        try:
            await self._preflight_check()

            # Step 1: Download the older release
            self._current_state = "downloading"
            self._update_progress = {"stage": "downloading", "percent": 0}
            if progress_callback:
                progress_callback("downloading", 0, "Downloading older version...")

            github = await self._get_github_client()
            download_dir = Path(tempfile.gettempdir()) / "tau-updates"
            download_dir.mkdir(parents=True, exist_ok=True)
            download_path = download_dir / (release.asset_name or f"{target_version}.tar.gz")

            def download_progress(downloaded: int, total: int):
                if total > 0:
                    percent = int(downloaded / total * 100)
                    self._update_progress = {"stage": "downloading", "percent": percent}
                    if progress_callback:
                        progress_callback("downloading", percent, f"Downloaded {downloaded}/{total} bytes")

            await github.download_asset(
                release.asset_url,
                download_path,
                expected_checksum=release.asset_checksum,
                progress_callback=download_progress,
            )

            # Step 2: Verify checksum
            self._current_state = "verifying"
            if progress_callback:
                progress_callback("verifying", 0, "Verifying download...")

            # Step 3: Create backup of current version
            self._current_state = "backing_up"
            if progress_callback:
                progress_callback("backing_up", 0, "Creating backup of current version...")

            current_backup = await backup_manager.create_backup(
                version=current_version,
                progress_callback=lambda p: (
                    progress_callback("backing_up", p, "Creating backup...") if progress_callback else None
                ),
            )

            # Record current version in history before downgrade
            current_schema = await self._get_current_schema_revision()
            history_entry = VersionHistory(
                version=current_version,
                backup_path=current_backup.backup_path if current_backup else None,
                backup_valid=True if current_backup else False,
                schema_revision=current_schema,
            )
            self.db_session.add(history_entry)
            await self.db_session.commit()

            # Step 4: Downgrade database schema BEFORE installing old code
            # This is critical - we need current migration files to downgrade
            if target_schema_revision:
                self._current_state = "migrating"
                if progress_callback:
                    progress_callback("migrating", 0, "Downgrading database schema...")

                success = await self._run_migrations_downgrade(target_schema_revision)
                if not success:
                    raise UpdateError(
                        f"Failed to downgrade database schema to {target_schema_revision}"
                    )

            # Step 5: Install the older version
            self._current_state = "installing"
            if progress_callback:
                progress_callback("installing", 0, "Installing older version...")

            await self._install_package(download_path)

            is_tarball = download_path.name.endswith(".tar.gz") or download_path.name.endswith(".tgz")
            if is_tarball:
                await self._update_backend_dependencies()

            # Step 6: Build frontend
            if progress_callback:
                progress_callback("installing", 50, "Building frontend...")
            await self._build_frontend()

            # Step 7: Update installation record
            installation = await self._get_installation()
            installation.current_version = target_version
            installation.installed_at = datetime.now(timezone.utc)
            installation.install_method = "rollback"  # Downgrade is a type of rollback
            installation.schema_revision = target_schema_revision
            await self.db_session.commit()

            # Step 8: Schedule service restart
            logger.info("scheduling_downgrade_restart")
            self._schedule_restart()

            self._current_state = "idle"
            self._update_progress = {}

            logger.info(
                "downgrade_complete",
                from_version=current_version,
                to_version=target_version
            )

            return {
                "success": True,
                "from_version": current_version,
                "to_version": target_version,
                "schema_revision": target_schema_revision,
                "message": f"Successfully downgraded from {current_version} to {target_version}",
            }

        except Exception as e:
            logger.error("downgrade_failed", error=str(e))
            self._current_state = "failed"

            # Attempt rollback to current version if we have a backup
            if current_backup:
                try:
                    logger.info("attempting_rollback_after_failed_downgrade")
                    await self._perform_rollback(current_backup.backup_path)
                except Exception as rollback_error:
                    logger.critical(
                        "rollback_after_downgrade_failed",
                        error=str(rollback_error)
                    )

            raise UpdateError(f"Downgrade failed: {str(e)}") from e

        finally:
            # Clean up download
            if download_path and download_path.exists():
                try:
                    download_path.unlink()
                except Exception:
                    pass

    async def _perform_rollback(
        self,
        backup_path: str,
        target_schema_revision: Optional[str] = None
    ):
        """
        Perform the actual rollback operation.

        Important: Database downgrade must happen BEFORE file restore,
        while we still have the current migration files available.

        Args:
            backup_path: Path to the backup directory to restore
            target_schema_revision: Alembic revision to downgrade to (if needed)
        """
        logger.info(
            "starting_rollback",
            backup_path=backup_path,
            target_schema_revision=target_schema_revision
        )
        backup_manager = await self._get_backup_manager()

        # Step 1: Downgrade database schema FIRST (while we still have current migrations)
        if target_schema_revision:
            current_revision = await self._get_current_schema_revision()
            if current_revision and current_revision != target_schema_revision:
                logger.info(
                    "downgrading_database_schema",
                    from_revision=current_revision,
                    to_revision=target_schema_revision
                )
                success = await self._run_migrations_downgrade(target_schema_revision)
                if not success:
                    logger.warning(
                        "schema_downgrade_failed_continuing",
                        target_revision=target_schema_revision
                    )
                    # Continue with file restore - schema mismatch may cause issues
                    # but it's better than leaving the system in a broken state

        # Step 2: Restore files from backup
        logger.info("restoring_from_backup", backup_path=backup_path)
        await backup_manager.restore_backup(backup_path)
        logger.info("backup_restored", backup_path=backup_path)

        # Step 3: Schedule service restart to pick up rolled-back code
        logger.info("scheduling_rollback_restart")
        self._schedule_restart()

    async def _stop_services(self):
        """Stop lighting control services"""
        for service in SERVICES:
            try:
                process = await asyncio.create_subprocess_exec(
                    "sudo",
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
                    "sudo",
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
        """Extract and install update package (tar.gz or .deb)"""
        import tarfile

        try:
            # Check if it's a tarball
            if package_path.suffix == ".gz" and package_path.stem.endswith(".tar"):
                logger.info("extracting_tarball", path=str(package_path), dest=str(self.app_root))

                # Extract tarball to a temp directory first
                import tempfile
                with tempfile.TemporaryDirectory() as temp_dir:
                    with tarfile.open(package_path, "r:gz") as tar:
                        # Extract everything to temp
                        tar.extractall(temp_dir)

                    # Find the extracted directory
                    temp_path = Path(temp_dir)
                    extracted_dirs = list(temp_path.iterdir())
                    if not extracted_dirs:
                        raise InstallationError("Tarball extraction produced no files")

                    source_dir = extracted_dirs[0]

                    # Copy files from temp to app_root using shutil
                    # This preserves the current user ownership
                    copied_count = 0
                    failed_files = []

                    for item in source_dir.rglob("*"):
                        if item.is_file():
                            rel_path = item.relative_to(source_dir)
                            dest = self.app_root / rel_path
                            dest.parent.mkdir(parents=True, exist_ok=True)

                            try:
                                # Try to copy - some files may be locked if currently in use
                                shutil.copy2(item, dest)
                                copied_count += 1
                            except (OSError, PermissionError) as e:
                                # Log but continue - the restart will pick up new files
                                failed_files.append((str(rel_path), str(e)))
                                logger.warning("file_copy_failed", path=str(rel_path), error=str(e))

                    logger.info("tarball_copy_complete", copied=copied_count, failed=len(failed_files))

                    if failed_files and len(failed_files) > copied_count * 0.1:
                        # If more than 10% of files failed, that's a problem
                        raise InstallationError(f"Too many files failed to copy: {len(failed_files)}/{copied_count + len(failed_files)}")

                logger.info("tarball_extracted", path=str(package_path))

            else:
                # Fall back to dpkg for .deb packages
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

        except tarfile.TarError as e:
            raise InstallationError(f"Failed to extract tarball: {str(e)}")
        except asyncio.TimeoutError:
            raise InstallationError(f"Package installation timed out after {PACKAGE_INSTALL_TIMEOUT}s")

    async def _update_backend_dependencies(self) -> None:
        """Update backend Python dependencies after a tarball install."""
        requirements_path = self.app_root / "daemon" / "requirements.txt"
        pip_path = self.app_root / "daemon" / ".venv" / "bin" / "pip"

        if not pip_path.exists():
            raise InstallationError("Backend virtual environment not found for dependency update")

        if not requirements_path.exists():
            logger.warning("backend_requirements_missing", path=str(requirements_path))
            return

        process = await asyncio.create_subprocess_exec(
            str(pip_path),
            "install",
            "-r",
            str(requirements_path),
            "--upgrade",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            process.communicate(), timeout=DEPENDENCY_UPDATE_TIMEOUT
        )

        if process.returncode != 0:
            raise InstallationError(
                f"Backend dependency update failed: {stderr.decode().strip()}"
            )

        logger.info("backend_dependencies_updated", output=stdout.decode().strip())

    def _schedule_restart(self) -> None:
        """Schedule a service restart using sudoers-allowed commands."""
        subprocess.Popen(
            [
                "sh",
                "-c",
                "sleep 3 && sudo systemctl restart tau-daemon && sudo systemctl restart tau-frontend",
            ],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    async def _build_frontend(self) -> None:
        """
        Build frontend static assets after update install.

        IMPORTANT: This method does NOT delete out/ before building.
        Next.js handles the out/ directory during its export phase,
        which only takes a few seconds. This ensures:

        1. nginx continues serving the OLD frontend during the entire build
        2. Only a brief (~1-2 second) window during Next.js export phase
        3. If build fails, old out/ may be corrupted but we'll know from the error

        The build is verified by checking for index.html and minimum file count.
        """
        frontend_dir = self.app_root / "frontend"
        package_json = frontend_dir / "package.json"
        out_dir = frontend_dir / "out"

        if not frontend_dir.exists() or not package_json.exists():
            logger.warning("frontend_build_skipped", reason="frontend_missing", path=str(frontend_dir))
            return

        try:
            # Step 1: Clean build cache only (NOT out/ - nginx keeps serving old version)
            for path in (".next", "node_modules/.cache"):
                shutil.rmtree(frontend_dir / path, ignore_errors=True)

            logger.info("frontend_build_prep_complete")

            # Step 2: Install dependencies
            install_cmd = ["npm", "ci"] if (frontend_dir / "package-lock.json").exists() else ["npm", "install"]
            logger.info("frontend_deps_installing", command=" ".join(install_cmd))
            install_proc = await asyncio.create_subprocess_exec(
                *install_cmd,
                cwd=str(frontend_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(
                install_proc.communicate(), timeout=FRONTEND_BUILD_TIMEOUT
            )
            if install_proc.returncode != 0:
                raise InstallationError(
                    f"Frontend dependency install failed: {stderr.decode().strip()}"
                )

            # Step 3: Build frontend
            # IMPORTANT: We do NOT delete out/ here. Next.js will overwrite it
            # during the export phase, which is quick (seconds). This ensures
            # nginx can serve the old frontend during the entire build process.
            env = os.environ.copy()
            env["NODE_ENV"] = "production"
            logger.info("frontend_build_starting")

            build_proc = await asyncio.create_subprocess_exec(
                "npm",
                "run",
                "build",
                cwd=str(frontend_dir),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(
                build_proc.communicate(), timeout=FRONTEND_BUILD_TIMEOUT
            )
            if build_proc.returncode != 0:
                raise InstallationError(f"Frontend build failed: {stderr.decode().strip()}")

            # Step 4: Verify build output exists
            # Next.js creates out/ during build with output:'export'
            if not out_dir.exists():
                raise InstallationError("Frontend build completed but output directory is missing")

            # Verify it has expected files
            index_html = out_dir / "index.html"
            if not index_html.exists():
                raise InstallationError("Frontend build completed but index.html is missing")

            # Count files to ensure it's a real build
            file_count = sum(1 for _ in out_dir.rglob("*") if _.is_file())
            if file_count < 5:
                raise InstallationError(f"Frontend build seems incomplete, only {file_count} files")

            logger.info("frontend_build_verified", file_count=file_count)
            logger.info("frontend_build_complete", path=str(out_dir))

        except asyncio.TimeoutError:
            logger.error("frontend_build_timeout", timeout=FRONTEND_BUILD_TIMEOUT)
            raise InstallationError(f"Frontend build timed out after {FRONTEND_BUILD_TIMEOUT}s")

        except Exception as e:
            logger.error("frontend_build_failed", error=str(e))
            raise

    async def _run_migrations(self):
        """Run database migrations (upgrade to head)"""
        try:
            # Use alembic from the venv
            alembic_path = self.app_root / "daemon" / ".venv" / "bin" / "alembic"
            process = await asyncio.create_subprocess_exec(
                str(alembic_path),
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
                error_output = stderr.decode().strip()
                logger.error("migration_failed", stderr=error_output)
                raise InstallationError(f"Database migration failed: {error_output}")

            logger.info("migrations_complete", output=stdout.decode().strip())

        except asyncio.TimeoutError:
            logger.error("migration_timeout")
            raise InstallationError(f"Database migration timed out after {MIGRATION_TIMEOUT}s")
        except Exception as e:
            logger.error("migration_error", error=str(e))
            raise

    async def _run_migrations_downgrade(self, target_revision: str) -> bool:
        """
        Run database migrations to downgrade to a specific revision.

        Args:
            target_revision: Alembic revision identifier to downgrade to

        Returns:
            True if successful, False otherwise
        """
        try:
            alembic_path = self.app_root / "daemon" / ".venv" / "bin" / "alembic"
            logger.info(
                "running_migration_downgrade",
                target_revision=target_revision
            )

            process = await asyncio.create_subprocess_exec(
                str(alembic_path),
                "downgrade",
                target_revision,
                cwd=str(self.app_root / "daemon"),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=MIGRATION_TIMEOUT
            )

            if process.returncode != 0:
                logger.error(
                    "migration_downgrade_failed",
                    stderr=stderr.decode(),
                    return_code=process.returncode
                )
                return False

            logger.info(
                "migration_downgrade_complete",
                target_revision=target_revision
            )
            return True

        except asyncio.TimeoutError:
            logger.error("migration_downgrade_timeout")
            return False
        except Exception as e:
            logger.error("migration_downgrade_error", error=str(e))
            return False

    async def _get_current_schema_revision(self) -> Optional[str]:
        """Get the current Alembic schema revision from the database"""
        try:
            alembic_path = self.app_root / "daemon" / ".venv" / "bin" / "alembic"
            process = await asyncio.create_subprocess_exec(
                str(alembic_path),
                "current",
                cwd=str(self.app_root / "daemon"),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=10.0
            )

            if process.returncode == 0:
                # Output format: "20260111_2100 (head)" or just "20260111_2100"
                output = stdout.decode().strip()
                if output:
                    # Extract revision ID (first word before space or parenthesis)
                    revision = output.split()[0] if output.split() else None
                    return revision
            return None

        except Exception as e:
            logger.warning("get_schema_revision_error", error=str(e))
            return None

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
                    # Note: During recovery, we're already in the process of starting up
                    # (this recovery code runs in __init__), so we can't "start" ourselves
                    # Just verify that we're healthy by successfully reaching this point
                    logger.info("recovery_verification", note="service_is_starting")

                    # Check if services are running (but don't try to start them)
                    services_healthy = await self._verify_installation("")

                    if not services_healthy:
                        # Don't attempt to start services - we're already starting!
                        # Just log the issue and let normal operations continue
                        logger.warning(
                            "recovery_service_check_failed",
                            note="service_may_still_be_starting",
                            state=interrupted_state
                        )
                        recovery_actions.append("verification_skipped_during_startup")

                        # Check if we should auto-rollback based on config
                        should_rollback = await self._get_config_bool("rollback_on_service_failure")
                        # But skip rollback if we're just starting up - give the service time to fully start
                        if should_rollback and False:  # Disabled during recovery
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
