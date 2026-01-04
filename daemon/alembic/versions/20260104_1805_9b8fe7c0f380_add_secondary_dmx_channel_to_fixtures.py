"""add_secondary_dmx_channel_to_fixtures

Revision ID: 9b8fe7c0f380
Revises: 20260103_1400
Create Date: 2026-01-04 18:05:36.548403+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9b8fe7c0f380"
down_revision: Union[str, None] = "20260103_1400"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add secondary_dmx_channel column to fixtures table
    op.add_column(
        "fixtures",
        sa.Column("secondary_dmx_channel", sa.Integer(), nullable=True),
    )
    # Add unique constraint
    op.create_unique_constraint(
        "fixtures_secondary_dmx_channel_key",
        "fixtures",
        ["secondary_dmx_channel"],
    )


def downgrade() -> None:
    # Remove unique constraint first
    op.drop_constraint(
        "fixtures_secondary_dmx_channel_key", "fixtures", type_="unique"
    )
    # Remove column
    op.drop_column("fixtures", "secondary_dmx_channel")
