"""
Tau Lighting Control - Service Layer

This package contains business logic and service classes.
"""

from tau.services.update_service import UpdateService
from tau.services.github_client import GitHubClient, GitHubRelease, GitHubAPIError
from tau.services.backup_manager import BackupManager, BackupInfo, BackupError
from tau.services.software_update_service import SoftwareUpdateService, UpdateError

__all__ = [
    "UpdateService",
    "GitHubClient",
    "GitHubRelease",
    "GitHubAPIError",
    "BackupManager",
    "BackupInfo",
    "BackupError",
    "SoftwareUpdateService",
    "UpdateError",
]
