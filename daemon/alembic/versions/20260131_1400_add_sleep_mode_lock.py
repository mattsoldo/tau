"""Add sleep mode lock settings to groups

Revision ID: 20260131_1400
Revises: 20260131_1200
Create Date: 2026-01-31 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260131_1400'
down_revision: Union[str, None] = '20260131_1200'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add sleep_lock_enabled column
    op.add_column('groups', sa.Column('sleep_lock_enabled', sa.Boolean(), nullable=True, server_default='false'))

    # Add sleep_lock_start_time column (HH:MM format)
    op.add_column('groups', sa.Column('sleep_lock_start_time', sa.String(5), nullable=True))

    # Add sleep_lock_end_time column (HH:MM format)
    op.add_column('groups', sa.Column('sleep_lock_end_time', sa.String(5), nullable=True))

    # Add sleep_lock_unlock_duration_minutes column (how long unlock lasts)
    op.add_column('groups', sa.Column('sleep_lock_unlock_duration_minutes', sa.Integer(), nullable=True, server_default='5'))

    # Set default values for existing groups
    op.execute("UPDATE groups SET sleep_lock_enabled = false WHERE sleep_lock_enabled IS NULL")
    op.execute("UPDATE groups SET sleep_lock_unlock_duration_minutes = 5 WHERE sleep_lock_unlock_duration_minutes IS NULL")

    # Add check constraints for time format validation (HH:MM)
    op.create_check_constraint(
        'groups_sleep_lock_start_time_format',
        'groups',
        "sleep_lock_start_time IS NULL OR sleep_lock_start_time ~ '^([0-1][0-9]|2[0-3]):[0-5][0-9]$'"
    )
    op.create_check_constraint(
        'groups_sleep_lock_end_time_format',
        'groups',
        "sleep_lock_end_time IS NULL OR sleep_lock_end_time ~ '^([0-1][0-9]|2[0-3]):[0-5][0-9]$'"
    )
    op.create_check_constraint(
        'groups_sleep_lock_unlock_duration_range',
        'groups',
        'sleep_lock_unlock_duration_minutes IS NULL OR (sleep_lock_unlock_duration_minutes >= 0 AND sleep_lock_unlock_duration_minutes <= 60)'
    )


def downgrade() -> None:
    op.drop_constraint('groups_sleep_lock_unlock_duration_range', 'groups', type_='check')
    op.drop_constraint('groups_sleep_lock_end_time_format', 'groups', type_='check')
    op.drop_constraint('groups_sleep_lock_start_time_format', 'groups', type_='check')
    op.drop_column('groups', 'sleep_lock_unlock_duration_minutes')
    op.drop_column('groups', 'sleep_lock_end_time')
    op.drop_column('groups', 'sleep_lock_start_time')
    op.drop_column('groups', 'sleep_lock_enabled')
