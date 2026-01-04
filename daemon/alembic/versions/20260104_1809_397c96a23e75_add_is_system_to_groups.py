"""add_is_system_to_groups

Revision ID: 397c96a23e75
Revises: 9b8fe7c0f380
Create Date: 2026-01-04 18:09:07.807060+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "397c96a23e75"
down_revision: Union[str, None] = "9b8fe7c0f380"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add is_system column to groups table
    op.add_column(
        "groups",
        sa.Column("is_system", sa.Boolean(), nullable=True, server_default="false"),
    )


def downgrade() -> None:
    # Remove is_system column
    op.drop_column("groups", "is_system")
