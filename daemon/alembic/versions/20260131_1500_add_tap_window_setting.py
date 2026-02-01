"""Add tap_window_ms system setting

Revision ID: 20260131_1500
Revises: 20260131_1400
Create Date: 2026-01-31 15:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260131_1500'
down_revision: Union[str, None] = '20260131_1400'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add tap_window_ms setting for configuring double-tap detection window
    # PRD specifies: Default 500ms, user-configurable range 200-900ms
    op.execute("""
        INSERT INTO system_settings (key, value, description, value_type)
        VALUES (
            'tap_window_ms',
            '500',
            'Time window in milliseconds to detect double-tap on switches (200-900ms). Lower = faster toggle, less time for double-tap.',
            'int'
        )
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM system_settings WHERE key = 'tap_window_ms'
    """)
