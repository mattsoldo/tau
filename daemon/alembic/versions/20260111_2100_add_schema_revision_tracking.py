"""Add schema_revision tracking for downgrade support

Revision ID: 20260111_2100
Revises: 20260106_0200
Create Date: 2026-01-11 21:00:00.000000

Adds schema_revision column to track which Alembic revision each version requires.
This enables proper database schema downgrades when rolling back to previous versions.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260111_2100"
down_revision: Union[str, None] = "20260106_0200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add schema_revision columns for downgrade support"""

    # Add schema_revision to installation table
    op.add_column(
        "installation",
        sa.Column("schema_revision", sa.String(length=50), nullable=True)
    )

    # Add schema_revision to version_history table
    op.add_column(
        "version_history",
        sa.Column("schema_revision", sa.String(length=50), nullable=True)
    )

    # Add schema_revision to available_releases table (for future releases)
    op.add_column(
        "available_releases",
        sa.Column("schema_revision", sa.String(length=50), nullable=True)
    )

    # Update current installation with this migration's revision
    op.execute(
        """
        UPDATE installation
        SET schema_revision = '20260111_2100'
        WHERE id = 1
        """
    )


def downgrade() -> None:
    """Remove schema_revision columns"""
    op.drop_column("available_releases", "schema_revision")
    op.drop_column("version_history", "schema_revision")
    op.drop_column("installation", "schema_revision")
