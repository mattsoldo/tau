"""Fix timestamp columns to use timezone-aware timestamps

Revision ID: 20260106_0100
Revises: 20260105_1400
Create Date: 2026-01-06 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260106_0100"
down_revision: Union[str, None] = "20260105_1400"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert timestamp columns to TIMESTAMP WITH TIME ZONE"""

    # Update installation table
    op.execute("ALTER TABLE installation ALTER COLUMN installed_at TYPE TIMESTAMP WITH TIME ZONE")

    # Update version_history table
    op.execute("ALTER TABLE version_history ALTER COLUMN installed_at TYPE TIMESTAMP WITH TIME ZONE")
    op.execute("ALTER TABLE version_history ALTER COLUMN uninstalled_at TYPE TIMESTAMP WITH TIME ZONE")

    # Update available_releases table
    op.execute("ALTER TABLE available_releases ALTER COLUMN published_at TYPE TIMESTAMP WITH TIME ZONE")
    op.execute("ALTER TABLE available_releases ALTER COLUMN checked_at TYPE TIMESTAMP WITH TIME ZONE")

    # Update update_checks table
    op.execute("ALTER TABLE update_checks ALTER COLUMN checked_at TYPE TIMESTAMP WITH TIME ZONE")

    # Update update_config table
    op.execute("ALTER TABLE update_config ALTER COLUMN updated_at TYPE TIMESTAMP WITH TIME ZONE")


def downgrade() -> None:
    """Revert timestamp columns to TIMESTAMP WITHOUT TIME ZONE"""

    # Revert installation table
    op.execute("ALTER TABLE installation ALTER COLUMN installed_at TYPE TIMESTAMP WITHOUT TIME ZONE")

    # Revert version_history table
    op.execute("ALTER TABLE version_history ALTER COLUMN installed_at TYPE TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE version_history ALTER COLUMN uninstalled_at TYPE TIMESTAMP WITHOUT TIME ZONE")

    # Revert available_releases table
    op.execute("ALTER TABLE available_releases ALTER COLUMN published_at TYPE TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE available_releases ALTER COLUMN checked_at TYPE TIMESTAMP WITHOUT TIME ZONE")

    # Revert update_checks table
    op.execute("ALTER TABLE update_checks ALTER COLUMN checked_at TYPE TIMESTAMP WITHOUT TIME ZONE")

    # Revert update_config table
    op.execute("ALTER TABLE update_config ALTER COLUMN updated_at TYPE TIMESTAMP WITHOUT TIME ZONE")
