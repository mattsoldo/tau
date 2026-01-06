"""
Backup Manager - Handles backup creation and restoration for updates

Manages version backups for safe rollback capability, including:
- Creating backups before updates
- Restoring from backups during rollback
- Pruning old backups based on retention policy
- Verifying backup integrity
"""
import asyncio
import json
import hashlib
import shutil
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict

import structlog

logger = structlog.get_logger(__name__)

# Default backup configuration
DEFAULT_BACKUP_LOCATION = "/var/lib/tau-lighting/backup"
DEFAULT_MAX_BACKUPS = 3
DEFAULT_MIN_FREE_SPACE_MB = 500

# Application paths (relative to repo root)
APP_DIRECTORIES = [
    "daemon/src",
    "frontend/src",
    "frontend/public",
]

CONFIG_DIRECTORIES = [
    "daemon/config",
    "frontend/.env.local",
]

# Files to always include
ESSENTIAL_FILES = [
    "daemon/requirements.txt",
    "daemon/pyproject.toml",
    "frontend/package.json",
    "frontend/package-lock.json",
]

# Patterns to exclude from backups
EXCLUDE_PATTERNS = [
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".next",
    ".git",
]


@dataclass
class BackupManifest:
    """Manifest describing a backup"""

    version: str
    created_at: str
    commit_sha: Optional[str]
    files: List[Dict[str, str]]  # {"path": str, "checksum": str}
    database_backed_up: bool
    services: List[str]
    backup_size_bytes: int
    app_root: str


@dataclass
class BackupInfo:
    """Information about a backup"""

    version: str
    backup_path: str
    created_at: datetime
    size_bytes: int
    valid: bool
    manifest: Optional[BackupManifest] = None


class BackupError(Exception):
    """Base exception for backup operations"""

    pass


class InsufficientSpaceError(BackupError):
    """Raised when there's not enough disk space for backup"""

    pass


class BackupNotFoundError(BackupError):
    """Raised when a backup cannot be found"""

    pass


class RestoreError(BackupError):
    """Raised when restoration fails"""

    pass


class BackupManager:
    """
    Manages version backups for the update system

    Handles creating, restoring, verifying, and pruning backups
    to support safe rollback functionality.
    """

    def __init__(
        self,
        backup_location: str = DEFAULT_BACKUP_LOCATION,
        app_root: str = "/opt/tau-daemon",
        max_backups: int = DEFAULT_MAX_BACKUPS,
        min_free_space_mb: int = DEFAULT_MIN_FREE_SPACE_MB,
    ):
        """
        Initialize BackupManager

        Args:
            backup_location: Directory to store backups
            app_root: Root directory of the application
            max_backups: Maximum number of backups to retain
            min_free_space_mb: Minimum free disk space required for backup
        """
        self.backup_location = Path(backup_location)
        self.app_root = Path(app_root)
        self.max_backups = max_backups
        self.min_free_space_mb = min_free_space_mb

    def _get_backup_dir(self, version: str) -> Path:
        """Get the backup directory path for a version"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_version = version.replace("/", "_").replace("\\", "_")
        return self.backup_location / f"{safe_version}_{timestamp}"

    def _should_exclude(self, path: Path) -> bool:
        """Check if a path matches any exclude pattern"""
        path_str = str(path)
        for pattern in EXCLUDE_PATTERNS:
            if pattern in path_str or path.name == pattern:
                return True
            # Handle wildcard patterns
            if "*" in pattern:
                import fnmatch
                if fnmatch.fnmatch(path.name, pattern):
                    return True
        return False

    def _ignore_patterns(self, directory: str, contents: list) -> set:
        """Ignore function for shutil.copytree to exclude unwanted files"""
        ignored = set()
        for item in contents:
            item_path = Path(directory) / item
            if self._should_exclude(item_path):
                ignored.add(item)
        return ignored

    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of a file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    async def _get_free_space_mb(self, path: Path) -> int:
        """Get free disk space in MB at the given path"""
        try:
            stat = os.statvfs(path)
            free_bytes = stat.f_bavail * stat.f_frsize
            return free_bytes // (1024 * 1024)
        except OSError:
            # Fallback for systems where statvfs isn't available
            return 0

    async def _estimate_backup_size(self) -> int:
        """Estimate the size of a backup in bytes"""
        total_size = 0

        for dir_path in APP_DIRECTORIES + CONFIG_DIRECTORIES:
            full_path = self.app_root / dir_path
            if full_path.exists():
                if full_path.is_file():
                    total_size += full_path.stat().st_size
                else:
                    for item in full_path.rglob("*"):
                        if item.is_file():
                            total_size += item.stat().st_size

        for file_path in ESSENTIAL_FILES:
            full_path = self.app_root / file_path
            if full_path.exists() and full_path.is_file():
                total_size += full_path.stat().st_size

        # Add 20% overhead for manifest and compression
        return int(total_size * 1.2)

    async def check_space_for_backup(self) -> bool:
        """
        Check if there's enough space for a backup

        Returns:
            True if there's enough space, False otherwise
        """
        # Ensure backup location exists
        self.backup_location.mkdir(parents=True, exist_ok=True)

        free_space = await self._get_free_space_mb(self.backup_location)
        estimated_size_mb = (await self._estimate_backup_size()) // (1024 * 1024)

        required_space = max(estimated_size_mb + 50, self.min_free_space_mb)
        return free_space >= required_space

    async def create_backup(
        self,
        version: str,
        commit_sha: Optional[str] = None,
        progress_callback: Optional[callable] = None,
    ) -> BackupInfo:
        """
        Create a backup of the current installation

        Args:
            version: Version string being backed up
            commit_sha: Git commit SHA of the version
            progress_callback: Optional callback(stage, progress)

        Returns:
            BackupInfo with details of the created backup

        Raises:
            InsufficientSpaceError: If there's not enough disk space
            BackupError: If backup creation fails
        """
        logger.info("creating_backup", version=version, commit_sha=commit_sha)

        # Check disk space
        if not await self.check_space_for_backup():
            raise InsufficientSpaceError(
                f"Insufficient disk space for backup. Need at least {self.min_free_space_mb}MB free."
            )

        backup_dir = self._get_backup_dir(version)
        logger.info(
            "creating_backup_directory",
            backup_dir=str(backup_dir),
            backup_location=str(self.backup_location),
            exists=backup_dir.exists(),
            parent_exists=backup_dir.parent.exists(),
        )

        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            logger.info("backup_directory_created", backup_dir=str(backup_dir))
        except OSError as e:
            logger.error(
                "failed_to_create_backup_directory",
                backup_dir=str(backup_dir),
                error=str(e),
                errno=e.errno,
                strerror=e.strerror,
            )
            raise BackupError(f"Failed to create backup directory {backup_dir}: {e}") from e

        files_manifest: List[Dict[str, str]] = []
        total_size = 0

        try:
            if progress_callback:
                progress_callback("starting", 0)

            # Copy application directories
            for i, dir_path in enumerate(APP_DIRECTORIES):
                source = self.app_root / dir_path
                if source.exists():
                    dest = backup_dir / dir_path
                    if source.is_file():
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, dest)
                        checksum = self._calculate_checksum(source)
                        files_manifest.append({"path": dir_path, "checksum": checksum})
                        total_size += source.stat().st_size
                    else:
                        shutil.copytree(source, dest, dirs_exist_ok=True, ignore=self._ignore_patterns)
                        for item in source.rglob("*"):
                            if item.is_file() and not self._should_exclude(item):
                                rel_path = str(item.relative_to(self.app_root))
                                checksum = self._calculate_checksum(item)
                                files_manifest.append({"path": rel_path, "checksum": checksum})
                                total_size += item.stat().st_size

                if progress_callback:
                    progress = int((i + 1) / len(APP_DIRECTORIES) * 50)
                    progress_callback("copying_app", progress)

            # Copy config directories
            for dir_path in CONFIG_DIRECTORIES:
                source = self.app_root / dir_path
                if source.exists():
                    dest = backup_dir / dir_path
                    if source.is_file():
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, dest)
                        checksum = self._calculate_checksum(source)
                        files_manifest.append({"path": dir_path, "checksum": checksum})
                        total_size += source.stat().st_size
                    else:
                        shutil.copytree(source, dest, dirs_exist_ok=True, ignore=self._ignore_patterns)
                        for item in source.rglob("*"):
                            if item.is_file() and not self._should_exclude(item):
                                rel_path = str(item.relative_to(self.app_root))
                                checksum = self._calculate_checksum(item)
                                files_manifest.append({"path": rel_path, "checksum": checksum})
                                total_size += item.stat().st_size

            if progress_callback:
                progress_callback("copying_config", 75)

            # Copy essential files
            for file_path in ESSENTIAL_FILES:
                source = self.app_root / file_path
                if source.exists() and source.is_file():
                    dest = backup_dir / file_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)
                    checksum = self._calculate_checksum(source)
                    files_manifest.append({"path": file_path, "checksum": checksum})
                    total_size += source.stat().st_size

            if progress_callback:
                progress_callback("copying_essential", 90)

            # Create manifest
            manifest = BackupManifest(
                version=version,
                created_at=datetime.now(timezone.utc).isoformat(),
                commit_sha=commit_sha,
                files=files_manifest,
                database_backed_up=False,  # Database backup handled separately
                services=["tau-daemon"],
                backup_size_bytes=total_size,
                app_root=str(self.app_root),
            )

            # Write manifest
            manifest_path = backup_dir / "manifest.json"
            with open(manifest_path, "w") as f:
                json.dump(asdict(manifest), f, indent=2)

            if progress_callback:
                progress_callback("complete", 100)

            logger.info(
                "backup_created",
                version=version,
                path=str(backup_dir),
                size_bytes=total_size,
                file_count=len(files_manifest),
            )

            return BackupInfo(
                version=version,
                backup_path=str(backup_dir),
                created_at=datetime.now(timezone.utc),
                size_bytes=total_size,
                valid=True,
                manifest=manifest,
            )

        except Exception as e:
            # Clean up partial backup
            if backup_dir.exists():
                shutil.rmtree(backup_dir, ignore_errors=True)
            logger.error("backup_failed", version=version, error=str(e))
            raise BackupError(f"Failed to create backup: {str(e)}") from e

    async def restore_backup(
        self,
        backup_path: str,
        progress_callback: Optional[callable] = None,
    ) -> bool:
        """
        Restore from a backup

        Args:
            backup_path: Path to the backup directory
            progress_callback: Optional callback(stage, progress)

        Returns:
            True if restoration was successful

        Raises:
            BackupNotFoundError: If backup doesn't exist
            RestoreError: If restoration fails
        """
        backup_dir = Path(backup_path)

        if not backup_dir.exists():
            raise BackupNotFoundError(f"Backup not found: {backup_path}")

        manifest_path = backup_dir / "manifest.json"
        if not manifest_path.exists():
            raise BackupNotFoundError(f"Backup manifest not found: {manifest_path}")

        logger.info("restoring_backup", backup_path=backup_path)

        try:
            # Load manifest
            with open(manifest_path) as f:
                manifest_data = json.load(f)
            manifest = BackupManifest(**manifest_data)

            if progress_callback:
                progress_callback("loading_manifest", 10)

            # Verify backup integrity
            if not await self.verify_backup(backup_path):
                raise RestoreError("Backup integrity check failed")

            if progress_callback:
                progress_callback("verified", 20)

            # Restore files
            for i, file_info in enumerate(manifest.files):
                source = backup_dir / file_info["path"]
                dest = self.app_root / file_info["path"]

                if source.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if dest.exists():
                        dest.unlink()
                    shutil.copy2(source, dest)

                if progress_callback:
                    progress = 20 + int((i + 1) / len(manifest.files) * 70)
                    progress_callback("restoring_files", progress)

            if progress_callback:
                progress_callback("complete", 100)

            logger.info("restore_complete", version=manifest.version, file_count=len(manifest.files))
            return True

        except (json.JSONDecodeError, KeyError) as e:
            raise RestoreError(f"Invalid backup manifest: {str(e)}") from e
        except Exception as e:
            logger.error("restore_failed", backup_path=backup_path, error=str(e))
            raise RestoreError(f"Restoration failed: {str(e)}") from e

    async def verify_backup(self, backup_path: str) -> bool:
        """
        Verify backup integrity by checking file checksums

        Args:
            backup_path: Path to the backup directory

        Returns:
            True if backup is valid, False otherwise
        """
        backup_dir = Path(backup_path)
        manifest_path = backup_dir / "manifest.json"

        if not manifest_path.exists():
            return False

        try:
            with open(manifest_path) as f:
                manifest_data = json.load(f)

            for file_info in manifest_data.get("files", []):
                file_path = backup_dir / file_info["path"]
                if not file_path.exists():
                    logger.warning("backup_file_missing", path=str(file_path))
                    return False

                actual_checksum = self._calculate_checksum(file_path)
                if actual_checksum != file_info["checksum"]:
                    logger.warning(
                        "backup_checksum_mismatch",
                        path=str(file_path),
                        expected=file_info["checksum"][:16],
                        actual=actual_checksum[:16],
                    )
                    return False

            return True

        except Exception as e:
            logger.error("backup_verification_failed", error=str(e))
            return False

    async def list_backups(self) -> List[BackupInfo]:
        """
        List all available backups

        Returns:
            List of BackupInfo sorted by creation date (newest first)
        """
        backups = []

        if not self.backup_location.exists():
            return backups

        for item in self.backup_location.iterdir():
            if item.is_dir():
                manifest_path = item / "manifest.json"
                if manifest_path.exists():
                    try:
                        with open(manifest_path) as f:
                            manifest_data = json.load(f)

                        manifest = BackupManifest(**manifest_data)
                        created_at = datetime.fromisoformat(manifest.created_at)

                        # Calculate actual size
                        total_size = sum(f.stat().st_size for f in item.rglob("*") if f.is_file())

                        # Verify backup is valid
                        is_valid = await self.verify_backup(str(item))

                        backups.append(
                            BackupInfo(
                                version=manifest.version,
                                backup_path=str(item),
                                created_at=created_at,
                                size_bytes=total_size,
                                valid=is_valid,
                                manifest=manifest,
                            )
                        )
                    except (json.JSONDecodeError, KeyError, ValueError) as e:
                        logger.warning("invalid_backup", path=str(item), error=str(e))

        # Sort by creation date, newest first
        backups.sort(key=lambda b: b.created_at, reverse=True)
        return backups

    async def get_backup_for_version(self, version: str) -> Optional[BackupInfo]:
        """
        Get the most recent valid backup for a specific version

        Args:
            version: Version string to find backup for

        Returns:
            BackupInfo or None if no valid backup exists
        """
        backups = await self.list_backups()

        for backup in backups:
            if backup.version == version and backup.valid:
                return backup

        return None

    async def prune_old_backups(self) -> int:
        """
        Remove old backups exceeding the retention limit

        Returns:
            Number of backups removed
        """
        backups = await self.list_backups()

        if len(backups) <= self.max_backups:
            return 0

        # Keep the newest backups, remove the rest
        to_remove = backups[self.max_backups :]
        removed_count = 0

        for backup in to_remove:
            try:
                backup_dir = Path(backup.backup_path)
                if backup_dir.exists():
                    shutil.rmtree(backup_dir)
                    logger.info("backup_pruned", version=backup.version, path=backup.backup_path)
                    removed_count += 1
            except Exception as e:
                logger.error("failed_to_prune_backup", path=backup.backup_path, error=str(e))

        return removed_count

    async def delete_backup(self, backup_path: str) -> bool:
        """
        Delete a specific backup

        Args:
            backup_path: Path to the backup directory

        Returns:
            True if deletion was successful
        """
        backup_dir = Path(backup_path)

        if not backup_dir.exists():
            return False

        try:
            shutil.rmtree(backup_dir)
            logger.info("backup_deleted", path=backup_path)
            return True
        except Exception as e:
            logger.error("backup_deletion_failed", path=backup_path, error=str(e))
            return False

    async def get_total_backup_size(self) -> int:
        """
        Get total size of all backups in bytes

        Returns:
            Total size in bytes
        """
        total = 0
        backups = await self.list_backups()
        for backup in backups:
            total += backup.size_bytes
        return total
