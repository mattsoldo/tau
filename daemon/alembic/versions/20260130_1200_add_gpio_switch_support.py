"""Add GPIO switch support fields

Revision ID: 20260130_1200
Revises: 20260120_1200
Create Date: 2026-01-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260130_1200'
down_revision: Union[str, None] = '20260120_1200'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add GPIO-specific fields to switches table"""
    # Add input_source column to specify whether switch uses LabJack or GPIO
    op.add_column(
        'switches',
        sa.Column('input_source', sa.String(20), nullable=False, server_default='labjack')
    )

    # Add gpio_bcm_pin for GPIO pin number (BCM numbering)
    op.add_column(
        'switches',
        sa.Column('gpio_bcm_pin', sa.Integer(), nullable=True)
    )

    # Add gpio_pull for pull resistor configuration
    op.add_column(
        'switches',
        sa.Column('gpio_pull', sa.String(10), nullable=True, server_default='up')
    )

    # Add check constraint for input_source values
    op.create_check_constraint(
        'switches_input_source_check',
        'switches',
        "input_source IN ('labjack', 'gpio')"
    )

    # Add check constraint for gpio_pull values
    op.create_check_constraint(
        'switches_gpio_pull_check',
        'switches',
        "gpio_pull IN ('up', 'down') OR gpio_pull IS NULL"
    )

    # Add check constraint: gpio_bcm_pin required when input_source is 'gpio'
    # and must be in valid range (GPIO pins available on Pi)
    op.create_check_constraint(
        'switches_gpio_pin_valid',
        'switches',
        "(input_source = 'labjack') OR "
        "(input_source = 'gpio' AND gpio_bcm_pin IS NOT NULL AND "
        "gpio_bcm_pin IN (4, 5, 6, 12, 13, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27))"
    )

    # Add partial unique index for GPIO pins - prevents duplicate GPIO assignments at DB level
    # This catches race conditions that API-level validation might miss
    op.execute("""
        CREATE UNIQUE INDEX switches_gpio_bcm_pin_unique
        ON switches (gpio_bcm_pin)
        WHERE input_source = 'gpio' AND gpio_bcm_pin IS NOT NULL
    """)


def downgrade() -> None:
    """Remove GPIO-specific fields from switches table"""
    # Drop unique index first
    op.execute("DROP INDEX IF EXISTS switches_gpio_bcm_pin_unique")

    # Drop constraints
    op.drop_constraint('switches_gpio_pin_valid', 'switches', type_='check')
    op.drop_constraint('switches_gpio_pull_check', 'switches', type_='check')
    op.drop_constraint('switches_input_source_check', 'switches', type_='check')

    # Drop columns
    op.drop_column('switches', 'gpio_pull')
    op.drop_column('switches', 'gpio_bcm_pin')
    op.drop_column('switches', 'input_source')
