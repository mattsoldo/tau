"""Add dim-to-warm settings and override system

Revision ID: 20260105_1300
Revises: 20260105_1200
Create Date: 2026-01-05 13:00:00.000000

This migration adds:
1. DTW system settings to system_settings table
2. DTW fields to fixtures table (dtw_ignore, dtw_min_cct_override, dtw_max_cct_override)
3. DTW fields to groups table (same fields)
4. Override table for managing temporary CCT overrides
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260105_1300'
down_revision: Union[str, None] = '20260105_1200'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add DTW settings to system_settings
    op.execute("""
        INSERT INTO system_settings (key, value, description, value_type)
        VALUES
            ('dtw_enabled', 'true', 'Enable dim-to-warm automatic CCT adjustment globally', 'bool'),
            ('dtw_min_cct', '1800', 'Color temperature at minimum brightness (Kelvin)', 'int'),
            ('dtw_max_cct', '4000', 'Color temperature at maximum brightness (Kelvin)', 'int'),
            ('dtw_min_brightness', '0.001', 'Brightness floor for DTW curve (0.0-1.0)', 'float'),
            ('dtw_curve', 'log', 'DTW interpolation curve type (linear, log, square, incandescent)', 'str'),
            ('dtw_override_timeout', '28800', 'Override expiration time in seconds (default: 8 hours)', 'int')
    """)

    # 2. Add DTW columns to fixtures table
    op.add_column('fixtures', sa.Column('dtw_ignore', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('fixtures', sa.Column('dtw_min_cct_override', sa.Integer(), nullable=True))
    op.add_column('fixtures', sa.Column('dtw_max_cct_override', sa.Integer(), nullable=True))

    # Add check constraints for fixture DTW CCT values
    op.create_check_constraint(
        'fixtures_dtw_min_cct_override_check',
        'fixtures',
        'dtw_min_cct_override IS NULL OR (dtw_min_cct_override >= 1000 AND dtw_min_cct_override <= 10000)'
    )
    op.create_check_constraint(
        'fixtures_dtw_max_cct_override_check',
        'fixtures',
        'dtw_max_cct_override IS NULL OR (dtw_max_cct_override >= 1000 AND dtw_max_cct_override <= 10000)'
    )

    # 3. Add DTW columns to groups table
    op.add_column('groups', sa.Column('dtw_ignore', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('groups', sa.Column('dtw_min_cct_override', sa.Integer(), nullable=True))
    op.add_column('groups', sa.Column('dtw_max_cct_override', sa.Integer(), nullable=True))

    # Add check constraints for group DTW CCT values
    op.create_check_constraint(
        'groups_dtw_min_cct_override_check',
        'groups',
        'dtw_min_cct_override IS NULL OR (dtw_min_cct_override >= 1000 AND dtw_min_cct_override <= 10000)'
    )
    op.create_check_constraint(
        'groups_dtw_max_cct_override_check',
        'groups',
        'dtw_max_cct_override IS NULL OR (dtw_max_cct_override >= 1000 AND dtw_max_cct_override <= 10000)'
    )

    # 4. Create overrides table
    op.create_table(
        'overrides',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('target_type', sa.String(20), nullable=False),  # 'fixture' or 'group'
        sa.Column('target_id', sa.Integer(), nullable=False),
        sa.Column('override_type', sa.String(20), nullable=False),  # 'dtw_cct', 'fixture_group', 'scene'
        sa.Column('property', sa.String(50), nullable=False),  # 'cct', 'brightness', etc.
        sa.Column('value', sa.Text(), nullable=False),  # Stored as string, converted by application
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column('expires_at', sa.TIMESTAMP(), nullable=False),
        sa.Column('source', sa.String(20), nullable=False),  # 'user', 'api', 'scene', 'schedule'
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint(
            "target_type IN ('fixture', 'group')",
            name='overrides_target_type_check'
        ),
        sa.CheckConstraint(
            "override_type IN ('dtw_cct', 'fixture_group', 'scene')",
            name='overrides_override_type_check'
        ),
        sa.CheckConstraint(
            "source IN ('user', 'api', 'scene', 'schedule')",
            name='overrides_source_check'
        )
    )

    # Create indexes for common queries
    op.create_index('ix_overrides_target', 'overrides', ['target_type', 'target_id'])
    op.create_index('ix_overrides_expires_at', 'overrides', ['expires_at'])

    # Create unique constraint to prevent duplicate overrides for same target+property
    # This prevents race conditions when creating overrides
    op.create_unique_constraint(
        'uq_overrides_target_property',
        'overrides',
        ['target_type', 'target_id', 'property']
    )


def downgrade() -> None:
    # Drop overrides table indexes and constraints
    op.drop_constraint('uq_overrides_target_property', 'overrides', type_='unique')
    op.drop_index('ix_overrides_expires_at', table_name='overrides')
    op.drop_index('ix_overrides_target', table_name='overrides')
    op.drop_table('overrides')

    # Remove DTW columns from groups
    op.drop_constraint('groups_dtw_max_cct_override_check', 'groups', type_='check')
    op.drop_constraint('groups_dtw_min_cct_override_check', 'groups', type_='check')
    op.drop_column('groups', 'dtw_max_cct_override')
    op.drop_column('groups', 'dtw_min_cct_override')
    op.drop_column('groups', 'dtw_ignore')

    # Remove DTW columns from fixtures
    op.drop_constraint('fixtures_dtw_max_cct_override_check', 'fixtures', type_='check')
    op.drop_constraint('fixtures_dtw_min_cct_override_check', 'fixtures', type_='check')
    op.drop_column('fixtures', 'dtw_max_cct_override')
    op.drop_column('fixtures', 'dtw_min_cct_override')
    op.drop_column('fixtures', 'dtw_ignore')

    # Remove DTW settings from system_settings
    op.execute("""
        DELETE FROM system_settings
        WHERE key IN (
            'dtw_enabled',
            'dtw_min_cct',
            'dtw_max_cct',
            'dtw_min_brightness',
            'dtw_curve',
            'dtw_override_timeout'
        )
    """)
