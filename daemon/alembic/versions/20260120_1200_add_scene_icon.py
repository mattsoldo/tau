"""Add icon field to scenes

Revision ID: 20260120_1200
Revises: 20260119_0100
Create Date: 2026-01-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260120_1200'
down_revision: Union[str, None] = '20260119_0100'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add icon column to scenes table
    op.add_column('scenes', sa.Column('icon', sa.String(50), nullable=True))


def downgrade() -> None:
    # Remove icon column from scenes table
    op.drop_column('scenes', 'icon')
