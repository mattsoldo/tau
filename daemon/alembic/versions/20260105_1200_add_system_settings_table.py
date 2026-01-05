"""Add system_settings table

Revision ID: 20260105_1200
Revises: 20260104_2115
Create Date: 2026-01-05 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260105_1200'
down_revision: Union[str, None] = '20260104_2115'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create system_settings table
    op.create_table(
        'system_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('value_type', sa.String(length=20), nullable=False, server_default='str'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key')
    )

    # Insert default settings
    op.execute("""
        INSERT INTO system_settings (key, value, description, value_type)
        VALUES (
            'dim_speed_ms',
            '2000',
            'Time in milliseconds for a full 0-100% brightness transition when dimming',
            'int'
        )
    """)


def downgrade() -> None:
    op.drop_table('system_settings')
