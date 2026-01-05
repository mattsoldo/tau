"""
Update Service - Software update management

Handles checking for updates, executing updates, and tracking update history.
"""
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import BackgroundTasks
from sqlalchemy import select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from tau.models.update_log import UpdateLog, UpdateStatus

logger = logging.getLogger(__name__)


class UpdateService:
    """
    Service for managing software updates

    Coordinates git operations, database migrations, dependency updates,
    and service restarts for both backend and frontend.
    """

    def __init__(self, repo_path: str = "/opt/tau-daemon", db_session: Optional[AsyncSession] = None):
        """
        Initialize UpdateService

        Args:
            repo_path: Path to git repository (default: /opt/tau-daemon)
            db_session: Database session for update tracking
        """
        self.repo_path = Path(repo_path)
        self.update_script = self.repo_path / "daemon" / "scripts" / "perform_update.sh"
        self.db_session = db_session

        # Validate repo path for security
        if not str(self.repo_path).startswith("/opt/tau-daemon"):
            raise ValueError(f"Invalid repo path: {repo_path}. Must be under /opt/tau-daemon")

    async def get_current_version(self) -> str:
        """
        Get current git commit hash

        Returns:
            Current git commit hash (short form)
        """
        try:
            process = await asyncio.create_subprocess_exec(
                "git",
                "rev-parse",
                "--short",
                "HEAD",
                cwd=str(self.repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"Failed to get current version: {stderr.decode()}")
                return "unknown"

            return stdout.decode().strip()
        except Exception as e:
            logger.error(f"Error getting current version: {e}")
            return "unknown"

    async def check_for_updates(self) -> Dict[str, Any]:
        """
        Check if updates are available from git remote

        Returns:
            Dictionary with update information:
            {
                "update_available": bool,
                "current_version": str,
                "latest_version": str,
                "commits_behind": int,
                "changelog": str
            }
        """
        try:
            # Fetch latest from remote
            logger.info("Fetching latest updates from git remote...")
            fetch_process = await asyncio.create_subprocess_exec(
                "git",
                "fetch",
                "origin",
                "main",
                cwd=str(self.repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(fetch_process.communicate(), timeout=30.0)

            if fetch_process.returncode != 0:
                raise RuntimeError("Git fetch failed")

            # Get current version
            current_version = await self.get_current_version()

            # Get latest remote version
            latest_process = await asyncio.create_subprocess_exec(
                "git",
                "rev-parse",
                "--short",
                "origin/main",
                cwd=str(self.repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            latest_stdout, _ = await latest_process.communicate()
            latest_version = latest_stdout.decode().strip()

            # Count commits behind
            count_process = await asyncio.create_subprocess_exec(
                "git",
                "rev-list",
                "--count",
                f"HEAD..origin/main",
                cwd=str(self.repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            count_stdout, _ = await count_process.communicate()
            commits_behind = int(count_stdout.decode().strip())

            # Get changelog if updates available
            changelog = ""
            if commits_behind > 0:
                changelog = await self.get_changelog(current_version, "origin/main")

            # Update database status
            if self.db_session:
                await self._update_status(
                    update_available=commits_behind > 0,
                    current_version=current_version,
                    available_version=latest_version if commits_behind > 0 else None,
                    last_check_at=datetime.now(timezone.utc),
                )

            result = {
                "update_available": commits_behind > 0,
                "current_version": current_version,
                "latest_version": latest_version,
                "commits_behind": commits_behind,
                "changelog": changelog,
            }

            logger.info(f"Update check complete: {result}")
            return result

        except asyncio.TimeoutError:
            logger.error("Git fetch timed out after 30 seconds")
            raise RuntimeError("Update check timed out. Please check network connection.")
        except Exception as e:
            logger.error(f"Error checking for updates: {e}")
            raise RuntimeError(f"Failed to check for updates: {str(e)}")

    async def get_changelog(self, from_commit: str, to_commit: str = "origin/main") -> str:
        """
        Get formatted git log between commits

        Args:
            from_commit: Starting commit hash
            to_commit: Ending commit hash (default: origin/main)

        Returns:
            Formatted changelog string
        """
        try:
            process = await asyncio.create_subprocess_exec(
                "git",
                "log",
                f"{from_commit}..{to_commit}",
                "--oneline",
                "--no-decorate",
                "--no-merges",
                cwd=str(self.repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"Failed to get changelog: {stderr.decode()}")
                return ""

            return stdout.decode().strip()
        except Exception as e:
            logger.error(f"Error getting changelog: {e}")
            return ""

    async def start_update(self, background_tasks: BackgroundTasks) -> Dict[str, Any]:
        """
        Start the update process in background

        Args:
            background_tasks: FastAPI background tasks

        Returns:
            Dictionary with update_id and status message
        """
        if not self.db_session:
            raise RuntimeError("Database session required for updates")

        # Check if update already in progress
        status = await self._get_status()
        if status and status.is_updating:
            raise RuntimeError("Update already in progress")

        # Check for uncommitted changes
        if await self._has_uncommitted_changes():
            raise RuntimeError(
                "Repository has uncommitted changes. Cannot update. "
                "Please commit or stash changes manually."
            )

        # Get current and target versions
        current_version = await self.get_current_version()
        check_result = await self.check_for_updates()

        if not check_result["update_available"]:
            raise RuntimeError("No updates available")

        # Create update log entry
        update_log = UpdateLog(
            version_before=current_version,
            version_after=check_result["latest_version"],
            status="in_progress",
            changelog=check_result["changelog"],
            update_type="manual",
            started_at=datetime.now(timezone.utc),
        )
        self.db_session.add(update_log)

        # Mark system as updating
        await self._update_status(is_updating=True)

        await self.db_session.commit()
        update_id = update_log.id

        # Add background task to perform update
        background_tasks.add_task(self._perform_update_background, update_id)

        logger.info(f"Update {update_id} started in background")

        return {
            "message": "Update started. System will restart when complete.",
            "update_id": update_id,
        }

    async def _perform_update_background(self, update_id: int):
        """
        Execute the update script in background

        This runs the perform_update.sh script which handles:
        - Git pull
        - Dependency installation
        - Database migrations
        - Frontend build
        - Service restarts

        Args:
            update_id: ID of UpdateLog entry tracking this update
        """
        logger.info(f"Performing update {update_id}...")

        try:
            # Validate script exists and is executable
            if not self.update_script.exists():
                raise RuntimeError(f"Update script not found: {self.update_script}")

            if not self.update_script.stat().st_mode & 0o111:
                raise RuntimeError(f"Update script not executable: {self.update_script}")

            # Execute update script
            process = await asyncio.create_subprocess_exec(
                str(self.update_script),
                cwd=str(self.repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=300.0)

            if process.returncode != 0:
                error_msg = stderr.decode()
                logger.error(f"Update script failed: {error_msg}")

                # Note: We may not be able to update the database if daemon restarts
                # The daemon startup will detect the failed update and mark it as failed
                raise RuntimeError(f"Update script failed: {error_msg}")

            logger.info(f"Update {update_id} script completed successfully")

            # Note: Daemon will restart after this, so we may not reach here
            # The startup code will mark the update as completed

        except asyncio.TimeoutError:
            logger.error(f"Update {update_id} timed out after 5 minutes")
            # Startup code will detect and mark as failed
        except Exception as e:
            logger.error(f"Error during update {update_id}: {e}")
            # Startup code will detect and mark as failed

    async def _has_uncommitted_changes(self) -> bool:
        """
        Check if git repository has uncommitted changes

        Returns:
            True if there are uncommitted changes
        """
        try:
            process = await asyncio.create_subprocess_exec(
                "git",
                "status",
                "--porcelain",
                cwd=str(self.repo_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await process.communicate()
            return len(stdout.decode().strip()) > 0
        except Exception as e:
            logger.error(f"Error checking git status: {e}")
            return False

    async def get_update_status(self) -> Dict[str, Any]:
        """
        Get current update status

        Returns:
            Dictionary with current update state
        """
        if not self.db_session:
            return {
                "current_version": await self.get_current_version(),
                "update_available": False,
                "is_updating": False,
            }

        status = await self._get_status()
        if not status:
            # Initialize status if it doesn't exist
            current_version = await self.get_current_version()
            status = UpdateStatus(
                id=1,
                is_updating=False,
                update_available=False,
                current_version=current_version,
            )
            self.db_session.add(status)
            await self.db_session.commit()

        return {
            "current_version": status.current_version or await self.get_current_version(),
            "available_version": status.available_version,
            "update_available": status.update_available,
            "is_updating": status.is_updating,
            "last_check_at": status.last_check_at.isoformat() if status.last_check_at else None,
        }

    async def get_update_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent update history

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of update log entries
        """
        if not self.db_session:
            return []

        result = await self.db_session.execute(
            select(UpdateLog).order_by(UpdateLog.started_at.desc()).limit(limit)
        )
        logs = result.scalars().all()

        return [
            {
                "id": log.id,
                "version_before": log.version_before,
                "version_after": log.version_after,
                "status": log.status,
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "completed_at": log.completed_at.isoformat() if log.completed_at else None,
                "error_message": log.error_message,
                "changelog": log.changelog,
                "update_type": log.update_type,
            }
            for log in logs
        ]

    async def check_incomplete_updates(self):
        """
        Check for incomplete updates on daemon startup

        If an update was in progress when daemon restarted, mark it as
        completed or failed based on current git version.
        """
        if not self.db_session:
            return

        # Find in-progress updates
        result = await self.db_session.execute(
            select(UpdateLog).where(UpdateLog.status == "in_progress").order_by(UpdateLog.started_at.desc())
        )
        in_progress = result.scalars().first()

        if not in_progress:
            # Reset is_updating flag if no in-progress updates
            await self._update_status(is_updating=False)
            return

        # Check if update completed successfully
        current_version = await self.get_current_version()

        if current_version == in_progress.version_after:
            # Update succeeded
            in_progress.status = "completed"
            in_progress.completed_at = datetime.now(timezone.utc)
            logger.info(f"Update {in_progress.id} completed successfully")
        else:
            # Update failed
            in_progress.status = "failed"
            in_progress.completed_at = datetime.now(timezone.utc)
            in_progress.error_message = (
                f"Update failed to reach target version. "
                f"Expected {in_progress.version_after}, got {current_version}"
            )
            logger.error(f"Update {in_progress.id} failed")

        # Reset is_updating flag
        await self._update_status(is_updating=False)
        await self.db_session.commit()

    async def _get_status(self) -> Optional[UpdateStatus]:
        """Get current UpdateStatus from database"""
        if not self.db_session:
            return None

        result = await self.db_session.execute(select(UpdateStatus).where(UpdateStatus.id == 1))
        return result.scalar_one_or_none()

    async def _update_status(self, **kwargs):
        """Update UpdateStatus fields"""
        if not self.db_session:
            return

        await self.db_session.execute(sql_update(UpdateStatus).where(UpdateStatus.id == 1).values(**kwargs))
        await self.db_session.commit()
