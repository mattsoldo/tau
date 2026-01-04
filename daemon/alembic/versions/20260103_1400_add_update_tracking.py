"""Add update tracking tables

Revision ID: 20260103_1400
Revises: 20250101_0000
Create Date: 2026-01-03 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260103_1400"
down_revision: Union[str, None] = "20250101_0000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add update tracking tables"""

    # Create update_log table for update history
    op.create_table(
        "update_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version_before", sa.String(length=100), nullable=True),
        sa.Column("version_after", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("changelog", sa.Text(), nullable=True),
        sa.Column("update_type", sa.String(length=50), nullable=True),
        sa.CheckConstraint(
            "status IN ('checking', 'available', 'in_progress', 'completed', 'failed')",
            name="update_log_status_check",
        ),
        sa.CheckConstraint(
            "update_type IN ('manual', 'automatic') OR update_type IS NULL",
            name="update_log_update_type_check",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create index on status for faster queries
    op.create_index("idx_update_log_status", "update_log", ["status"])
    op.create_index("idx_update_log_started_at", "update_log", ["started_at"])

    # Create update_status table for current update state (single row)
    op.create_table(
        "update_status",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("is_updating", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("current_version", sa.String(length=100), nullable=True),
        sa.Column("available_version", sa.String(length=100), nullable=True),
        sa.Column("last_check_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("update_available", sa.Boolean(), nullable=False, server_default="false"),
        sa.CheckConstraint("id = 1", name="update_status_single_row_check"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Insert initial row in update_status table
    op.execute(
        """
        INSERT INTO update_status (id, is_updating, update_available)
        VALUES (1, false, false)
        """
    )


def downgrade() -> None:
    """Remove update tracking tables"""
    op.drop_table("update_status")
    op.drop_index("idx_update_log_started_at", table_name="update_log")
    op.drop_index("idx_update_log_status", table_name="update_log")
    op.drop_table("update_log")
