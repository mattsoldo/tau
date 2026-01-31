"""Add software update system tables

Revision ID: 20260105_1400
Revises: 20260105_1200
Create Date: 2026-01-05 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260105_1400"
down_revision: Union[str, None] = "20260105_1200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add software update system tables for GitHub Releases-based OTA updates"""

    # Create installation table (singleton for current state)
    op.create_table(
        "installation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("current_version", sa.String(length=50), nullable=False),
        sa.Column("commit_sha", sa.String(length=100), nullable=True),
        sa.Column(
            "installed_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("install_method", sa.String(length=20), nullable=True),
        sa.CheckConstraint("id = 1", name="installation_single_row_check"),
        sa.CheckConstraint(
            "install_method IN ('fresh', 'update', 'rollback') OR install_method IS NULL",
            name="installation_method_check",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Insert initial installation record with placeholder version
    # Use ON CONFLICT to handle re-runs gracefully
    op.execute(
        """
        INSERT INTO installation (id, current_version, install_method)
        VALUES (1, '0.0.0', 'fresh')
        ON CONFLICT (id) DO NOTHING
        """
    )

    # Create version_history table for rollback support
    op.create_table(
        "version_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("commit_sha", sa.String(length=100), nullable=True),
        sa.Column(
            "installed_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("uninstalled_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("backup_path", sa.String(length=500), nullable=True),
        sa.Column("backup_valid", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("release_notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_version_history_version", "version_history", ["version"])
    op.create_index("idx_version_history_installed_at", "version_history", ["installed_at"])
    op.create_index("idx_version_history_backup_valid", "version_history", ["backup_valid"])

    # Create available_releases table (cache from GitHub)
    op.create_table(
        "available_releases",
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("tag_name", sa.String(length=100), nullable=False),
        sa.Column("published_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("release_notes", sa.Text(), nullable=True),
        sa.Column("asset_url", sa.String(length=1000), nullable=True),
        sa.Column("asset_name", sa.String(length=255), nullable=True),
        sa.Column("asset_size", sa.Integer(), nullable=True),
        sa.Column("asset_checksum", sa.String(length=128), nullable=True),
        sa.Column("prerelease", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("draft", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "checked_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("version"),
    )
    op.create_index("idx_available_releases_published_at", "available_releases", ["published_at"])
    op.create_index("idx_available_releases_prerelease", "available_releases", ["prerelease"])
    op.create_index("idx_available_releases_checked_at", "available_releases", ["checked_at"])

    # Create update_checks table for logging check operations
    op.create_table(
        "update_checks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "checked_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("result", sa.String(length=30), nullable=False),
        sa.Column("current_version", sa.String(length=50), nullable=True),
        sa.Column("latest_version", sa.String(length=50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "source IN ('manual', 'scheduled', 'startup')",
            name="update_checks_source_check",
        ),
        sa.CheckConstraint(
            "result IN ('up_to_date', 'update_available', 'error')",
            name="update_checks_result_check",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_update_checks_checked_at", "update_checks", ["checked_at"])
    op.create_index("idx_update_checks_result", "update_checks", ["result"])

    # Create update_config table for update settings
    op.create_table(
        "update_config",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("key"),
    )

    # Insert default configuration values
    # Use parameterized queries to prevent SQL injection
    # ON CONFLICT handles re-runs gracefully and preserves existing config
    default_configs = [
        ("auto_check_enabled", "true", "Enable automatic update checks"),
        ("check_interval_hours", "24", "Hours between automatic update checks"),
        ("include_prereleases", "false", "Include pre-release versions in update checks"),
        ("max_backups", "3", "Maximum number of version backups to retain"),
        ("github_repo", "", "GitHub repository in owner/repo format"),
        ("github_token", "", "GitHub API token for private repos or higher rate limits"),
        ("backup_location", "/opt/tau-backups", "Directory for version backups"),
        ("min_free_space_mb", "500", "Minimum free disk space required for updates (MB)"),
        ("download_timeout_seconds", "300", "Timeout for downloading update assets"),
        ("verify_after_install", "true", "Verify installation after applying updates"),
        ("rollback_on_service_failure", "true", "Automatically rollback if services fail to start"),
    ]

    # Use SQLAlchemy text with bound parameters for safe SQL execution
    insert_stmt = sa.text(
        """
        INSERT INTO update_config (key, value, description)
        VALUES (:key, :value, :description)
        ON CONFLICT (key) DO NOTHING
        """
    )

    for key, value, description in default_configs:
        op.execute(insert_stmt.bindparams(key=key, value=value, description=description))


def downgrade() -> None:
    """Remove software update system tables"""
    op.drop_table("update_config")
    op.drop_index("idx_update_checks_result", table_name="update_checks")
    op.drop_index("idx_update_checks_checked_at", table_name="update_checks")
    op.drop_table("update_checks")
    op.drop_index("idx_available_releases_checked_at", table_name="available_releases")
    op.drop_index("idx_available_releases_prerelease", table_name="available_releases")
    op.drop_index("idx_available_releases_published_at", table_name="available_releases")
    op.drop_table("available_releases")
    op.drop_index("idx_version_history_backup_valid", table_name="version_history")
    op.drop_index("idx_version_history_installed_at", table_name="version_history")
    op.drop_index("idx_version_history_version", table_name="version_history")
    op.drop_table("version_history")
    op.drop_table("installation")
