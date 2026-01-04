"""add_override_state_to_fixture_state

Revision ID: 06633210d83e
Revises: fa6a88c1509f
Create Date: 2026-01-04 18:10:57.107027+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "06633210d83e"
down_revision: Union[str, None] = "fa6a88c1509f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add override state columns to fixture_state
    op.add_column(
        "fixture_state",
        sa.Column("override_active", sa.Boolean(), nullable=True, server_default="false"),
    )
    op.add_column(
        "fixture_state",
        sa.Column("override_expires_at", sa.TIMESTAMP(), nullable=True),
    )
    op.add_column(
        "fixture_state",
        sa.Column("override_source", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    # Remove override state columns
    op.drop_column("fixture_state", "override_source")
    op.drop_column("fixture_state", "override_expires_at")
    op.drop_column("fixture_state", "override_active")
