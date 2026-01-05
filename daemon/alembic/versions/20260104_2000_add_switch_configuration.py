"""add switch configuration

Revision ID: 20260104_2000
Revises: 20260104_1810_fa6a88c1509f
Create Date: 2026-01-04 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_switch_config_20260104'
down_revision: Union[str, None] = 'fa6a88c1509f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add switch hardware configuration fields to switches table"""
    # Add switch_type column (normally-open or normally-closed)
    op.add_column(
        'switches',
        sa.Column('switch_type', sa.String(20), nullable=True)
    )

    # Add invert_reading column for software logic inversion
    op.add_column(
        'switches',
        sa.Column('invert_reading', sa.Boolean(), nullable=False, server_default='false')
    )

    # Set default switch_type for existing switches to 'normally-closed'
    # (matches current behavior)
    op.execute("UPDATE switches SET switch_type = 'normally-closed' WHERE switch_type IS NULL")

    # Make switch_type non-nullable after setting defaults
    op.alter_column('switches', 'switch_type', nullable=False)


def downgrade() -> None:
    """Remove switch hardware configuration fields"""
    op.drop_column('switches', 'invert_reading')
    op.drop_column('switches', 'switch_type')
