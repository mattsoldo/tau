"""
Software Update Models - GitHub Releases-based OTA update system

Models for tracking installation state, version history, available releases,
and update configuration for the lighting control system.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Integer,
    String,
    Text,
    Boolean,
    CheckConstraint,
    TIMESTAMP,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from tau.database import Base


class Installation(Base):
    """
    Installation - Current installation state (singleton table)

    Tracks the currently installed version, when it was installed,
    and how it was installed (fresh install, update, or rollback).
    """

    __tablename__ = "installation"

    # Primary Key (always 1 - singleton)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Version Information
    current_version: Mapped[str] = mapped_column(String(50), nullable=False)
    commit_sha: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Installation Details
    installed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        server_default=func.current_timestamp(),
    )
    install_method: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Constraints
    __table_args__ = (
        CheckConstraint("id = 1", name="installation_single_row_check"),
        CheckConstraint(
            "install_method IN ('fresh', 'update', 'rollback') OR install_method IS NULL",
            name="installation_method_check",
        ),
    )

    def __repr__(self) -> str:
        return f"<Installation(version={self.current_version}, method={self.install_method})>"


class VersionHistory(Base):
    """
    Version History - Historical record of installed versions

    Tracks each version that has been installed, when it was installed/uninstalled,
    and maintains backup information for rollback support.
    """

    __tablename__ = "version_history"

    # Primary Key
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Version Information
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    commit_sha: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Timestamps
    installed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        server_default=func.current_timestamp(),
    )
    uninstalled_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)

    # Backup Information
    backup_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    backup_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    # Release Information
    release_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Indexes
    __table_args__ = (
        Index("idx_version_history_version", "version"),
        Index("idx_version_history_installed_at", "installed_at"),
        Index("idx_version_history_backup_valid", "backup_valid"),
    )

    def __repr__(self) -> str:
        return f"<VersionHistory(id={self.id}, version={self.version}, backup_valid={self.backup_valid})>"


class AvailableRelease(Base):
    """
    Available Release - Cache of releases from GitHub

    Stores information about available releases fetched from the GitHub API,
    including version, release notes, asset URLs, and checksums.
    """

    __tablename__ = "available_releases"

    # Primary Key (version string)
    version: Mapped[str] = mapped_column(String(50), primary_key=True)

    # GitHub Release Information
    tag_name: Mapped[str] = mapped_column(String(100), nullable=False)
    published_at: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    release_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Asset Information
    asset_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    asset_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    asset_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    asset_checksum: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Release Type
    prerelease: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    draft: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    # Cache Metadata
    checked_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        server_default=func.current_timestamp(),
    )

    # Indexes
    __table_args__ = (
        Index("idx_available_releases_published_at", "published_at"),
        Index("idx_available_releases_prerelease", "prerelease"),
        Index("idx_available_releases_checked_at", "checked_at"),
    )

    def __repr__(self) -> str:
        return f"<AvailableRelease(version={self.version}, prerelease={self.prerelease})>"


class UpdateCheck(Base):
    """
    Update Check - Log of update check operations

    Records each time the system checks for updates, including the source
    (manual or scheduled), result, and any errors encountered.
    """

    __tablename__ = "update_checks"

    # Primary Key
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Check Details
    checked_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        server_default=func.current_timestamp(),
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    result: Mapped[str] = mapped_column(String(30), nullable=False)

    # Version Information
    current_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    latest_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Error Information
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "source IN ('manual', 'scheduled', 'startup')",
            name="update_checks_source_check",
        ),
        CheckConstraint(
            "result IN ('up_to_date', 'update_available', 'error')",
            name="update_checks_result_check",
        ),
        Index("idx_update_checks_checked_at", "checked_at"),
        Index("idx_update_checks_result", "result"),
    )

    def __repr__(self) -> str:
        return f"<UpdateCheck(id={self.id}, source={self.source}, result={self.result})>"


class UpdateConfig(Base):
    """
    Update Configuration - System update settings

    Stores configuration for the update system including auto-check settings,
    GitHub repository information, and backup retention policies.
    """

    __tablename__ = "update_config"

    # Primary Key
    key: Mapped[str] = mapped_column(String(100), primary_key=True)

    # Value
    value: Mapped[str] = mapped_column(Text, nullable=False)

    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        server_default=func.current_timestamp(),
    )

    def __repr__(self) -> str:
        return f"<UpdateConfig(key={self.key}, value={self.value})>"


# Default configuration values
DEFAULT_UPDATE_CONFIG = {
    "auto_check_enabled": ("true", "Enable automatic update checks"),
    "check_interval_hours": ("24", "Hours between automatic update checks"),
    "include_prereleases": ("false", "Include pre-release versions in update checks"),
    "max_backups": ("3", "Maximum number of version backups to retain"),
    "github_repo": ("", "GitHub repository in owner/repo format"),
    "github_token": ("", "GitHub API token for private repos or higher rate limits"),
    "backup_location": ("/var/lib/tau-lighting/backup", "Directory for version backups"),
    "min_free_space_mb": ("500", "Minimum free disk space required for updates (MB)"),
    "download_timeout_seconds": ("300", "Timeout for downloading update assets"),
    "verify_after_install": ("true", "Verify installation after applying updates"),
    "rollback_on_service_failure": ("true", "Automatically rollback if services fail to start"),
}
