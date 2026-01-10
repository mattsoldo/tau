"""Add double-tap scene mapping to switches

Revision ID: 20260106_0300
Revises: 20260106_0200
Create Date: 2026-01-06 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260106_0300"
down_revision: Union[str, None] = "20260106_0200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "switches",
        sa.Column("double_tap_scene_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_switches_double_tap_scene",
        "switches",
        "scenes",
        ["double_tap_scene_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_switches_double_tap_scene", "switches", type_="foreignkey")
    op.drop_column("switches", "double_tap_scene_id")
