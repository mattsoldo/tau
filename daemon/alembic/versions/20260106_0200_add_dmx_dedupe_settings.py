"""Add DMX dedupe system settings

Revision ID: 20260106_0200
Revises: 20260106_0100
Create Date: 2026-01-06 02:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260106_0200"
down_revision: Union[str, None] = "20260106_0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO system_settings (key, value, description, value_type)
        VALUES
            (
                'dmx_dedupe_enabled',
                'true',
                'Skip redundant DMX writes when output is unchanged',
                'bool'
            ),
            (
                'dmx_dedupe_ttl_seconds',
                '1.0',
                'Minimum seconds between identical DMX writes when dedupe is enabled',
                'float'
            )
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM system_settings
        WHERE key IN ('dmx_dedupe_enabled', 'dmx_dedupe_ttl_seconds')
        """
    )
