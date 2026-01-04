"""add_planckian_locus_to_fixture_models

Revision ID: fa6a88c1509f
Revises: 397c96a23e75
Create Date: 2026-01-04 18:10:35.217210+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "fa6a88c1509f"
down_revision: Union[str, None] = "397c96a23e75"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add Planckian Locus color mixing parameters
    op.add_column("fixture_models", sa.Column("warm_xy_x", sa.Float(), nullable=True))
    op.add_column("fixture_models", sa.Column("warm_xy_y", sa.Float(), nullable=True))
    op.add_column("fixture_models", sa.Column("cool_xy_x", sa.Float(), nullable=True))
    op.add_column("fixture_models", sa.Column("cool_xy_y", sa.Float(), nullable=True))
    op.add_column("fixture_models", sa.Column("warm_lumens", sa.Integer(), nullable=True))
    op.add_column("fixture_models", sa.Column("cool_lumens", sa.Integer(), nullable=True))
    op.add_column(
        "fixture_models",
        sa.Column("gamma", sa.Float(), nullable=True, server_default="2.2"),
    )

    # Remove deprecated mixing_type column
    op.drop_constraint("fixture_models_mixing_type_check", "fixture_models", type_="check")
    op.drop_column("fixture_models", "mixing_type")


def downgrade() -> None:
    # Restore mixing_type column
    op.add_column(
        "fixture_models",
        sa.Column("mixing_type", sa.String(length=20), nullable=False, server_default="linear"),
    )
    op.create_check_constraint(
        "fixture_models_mixing_type_check",
        "fixture_models",
        "mixing_type IN ('linear', 'perceptual', 'logarithmic', 'custom')",
    )

    # Remove Planckian Locus parameters
    op.drop_column("fixture_models", "gamma")
    op.drop_column("fixture_models", "cool_lumens")
    op.drop_column("fixture_models", "warm_lumens")
    op.drop_column("fixture_models", "cool_xy_y")
    op.drop_column("fixture_models", "cool_xy_x")
    op.drop_column("fixture_models", "warm_xy_y")
    op.drop_column("fixture_models", "warm_xy_x")
