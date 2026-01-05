"""Add default brightness and CCT to groups

Revision ID: 20260104_2115
Revises: 20260104_2000
Create Date: 2026-01-04 21:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260104_2115'
down_revision: Union[str, None] = '20260104_2000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add default_max_brightness column (0-1000, defaults to 1000 = 100%)
    op.add_column('groups', sa.Column('default_max_brightness', sa.Integer(), nullable=True))

    # Add default_cct_kelvin column (Kelvin, defaults to None = use fixture default)
    op.add_column('groups', sa.Column('default_cct_kelvin', sa.Integer(), nullable=True))

    # Set default values for existing groups (1000 = 100% brightness, None for CCT)
    op.execute("UPDATE groups SET default_max_brightness = 1000 WHERE default_max_brightness IS NULL")

    # Add check constraints
    op.create_check_constraint(
        'groups_default_max_brightness_range',
        'groups',
        'default_max_brightness >= 0 AND default_max_brightness <= 1000'
    )
    op.create_check_constraint(
        'groups_default_cct_kelvin_range',
        'groups',
        'default_cct_kelvin IS NULL OR (default_cct_kelvin >= 1000 AND default_cct_kelvin <= 10000)'
    )


def downgrade() -> None:
    op.drop_constraint('groups_default_cct_kelvin_range', 'groups', type_='check')
    op.drop_constraint('groups_default_max_brightness_range', 'groups', type_='check')
    op.drop_column('groups', 'default_cct_kelvin')
    op.drop_column('groups', 'default_max_brightness')
