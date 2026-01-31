"""Add software update job tracking

Revision ID: 20260131_1200
Revises: 20260130_1200
Create Date: 2026-01-31 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260131_1200"
down_revision: Union[str, None] = "20260130_1200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add software update job tracking table"""
    op.create_table(
        "software_update_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=20), nullable=False),
        sa.Column("target_version", sa.String(length=50), nullable=True),
        sa.Column("from_version", sa.String(length=50), nullable=True),
        sa.Column("to_version", sa.String(length=50), nullable=True),
        sa.Column("state", sa.String(length=50), nullable=False),
        sa.Column("stage", sa.String(length=50), nullable=True),
        sa.Column("progress_percent", sa.Integer(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "idx_software_update_jobs_created_at",
        "software_update_jobs",
        ["created_at"],
    )
    op.create_index(
        "idx_software_update_jobs_state",
        "software_update_jobs",
        ["state"],
    )


def downgrade() -> None:
    """Remove software update job tracking table"""
    op.drop_index("idx_software_update_jobs_state", table_name="software_update_jobs")
    op.drop_index("idx_software_update_jobs_created_at", table_name="software_update_jobs")
    op.drop_table("software_update_jobs")
