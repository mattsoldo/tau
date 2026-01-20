"""Add display_order to groups/scenes and scene_type to scenes

Revision ID: 20260119_0100
Revises: 20260111_2100
Create Date: 2026-01-19
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20260119_0100'
down_revision = '20260105_1300'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add display_order to groups table
    op.add_column('groups', sa.Column('display_order', sa.Integer(), nullable=True))

    # Add display_order and scene_type to scenes table
    op.add_column('scenes', sa.Column('display_order', sa.Integer(), nullable=True))
    op.add_column('scenes', sa.Column('scene_type', sa.String(length=20), nullable=False, server_default='idempotent'))

    # Initialize display_order based on existing id order
    op.execute("UPDATE groups SET display_order = id WHERE display_order IS NULL")
    op.execute("UPDATE scenes SET display_order = id WHERE display_order IS NULL")

    # Add street_address system setting
    op.execute("""
        INSERT INTO system_settings (key, value, description, value_type)
        VALUES ('street_address', '', 'Street address for home location display', 'str')
        ON CONFLICT (key) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_column('scenes', 'scene_type')
    op.drop_column('scenes', 'display_order')
    op.drop_column('groups', 'display_order')

    op.execute("DELETE FROM system_settings WHERE key = 'street_address'")
