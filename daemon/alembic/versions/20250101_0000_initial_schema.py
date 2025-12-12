"""Initial schema

Revision ID: 20250101_0000
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20250101_0000"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial database schema"""

    # Create fixture_models table
    op.create_table(
        "fixture_models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("manufacturer", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "type",
            sa.String(length=20),
            nullable=False,
            server_default="simple_dimmable",
        ),
        sa.Column("dmx_footprint", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("cct_min_kelvin", sa.Integer(), nullable=True, server_default="1800"),
        sa.Column("cct_max_kelvin", sa.Integer(), nullable=True, server_default="4000"),
        sa.Column("mixing_type", sa.String(length=20), nullable=False, server_default="linear"),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "type IN ('simple_dimmable', 'tunable_white', 'dim_to_warm', 'non_dimmable', 'other')",
            name="fixture_models_type_check",
        ),
        sa.CheckConstraint(
            "mixing_type IN ('linear', 'perceptual', 'logarithmic', 'custom')",
            name="fixture_models_mixing_type_check",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("manufacturer", "model", name="fixture_models_manufacturer_model_key"),
    )

    # Create fixtures table
    op.create_table(
        "fixtures",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("fixture_model_id", sa.Integer(), nullable=False),
        sa.Column("dmx_channel_start", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(
            ["fixture_model_id"],
            ["fixture_models.id"],
            name="fixtures_fixture_model_id_fkey",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dmx_channel_start", name="fixtures_dmx_channel_start_key"),
    )

    # Create switch_models table
    op.create_table(
        "switch_models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("manufacturer", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("input_type", sa.String(length=50), nullable=False),
        sa.Column("debounce_ms", sa.Integer(), nullable=True, server_default="500"),
        sa.Column("dimming_curve", sa.String(length=20), nullable=True, server_default="logarithmic"),
        sa.Column("requires_digital_pin", sa.Boolean(), nullable=True, server_default="true"),
        sa.Column("requires_analog_pin", sa.Boolean(), nullable=True, server_default="false"),
        sa.CheckConstraint(
            "input_type IN ('retractive', 'rotary_abs', 'paddle_composite', 'switch_simple')",
            name="switch_models_input_type_check",
        ),
        sa.CheckConstraint(
            "dimming_curve IN ('linear', 'logarithmic')",
            name="switch_models_dimming_curve_check",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("manufacturer", "model", name="switch_models_manufacturer_model_key"),
    )

    # Create circadian_profiles table (must be before groups for FK)
    op.create_table(
        "circadian_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("curve_points", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "interpolation_type",
            sa.String(length=20),
            nullable=True,
            server_default="linear",
        ),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "interpolation_type IN ('linear', 'cosine', 'step')",
            name="circadian_profiles_interpolation_type_check",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="circadian_profiles_name_key"),
    )

    # Create groups table
    op.create_table(
        "groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("circadian_enabled", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("circadian_profile_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(
            ["circadian_profile_id"],
            ["circadian_profiles.id"],
            name="fk_groups_circadian_profile",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create switches table
    op.create_table(
        "switches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("switch_model_id", sa.Integer(), nullable=False),
        sa.Column("labjack_digital_pin", sa.Integer(), nullable=True),
        sa.Column("labjack_analog_pin", sa.Integer(), nullable=True),
        sa.Column("target_group_id", sa.Integer(), nullable=True),
        sa.Column("target_fixture_id", sa.Integer(), nullable=True),
        sa.Column("photo_url", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "(target_group_id IS NOT NULL AND target_fixture_id IS NULL) OR "
            "(target_group_id IS NULL AND target_fixture_id IS NOT NULL)",
            name="one_target_only",
        ),
        sa.ForeignKeyConstraint(
            ["switch_model_id"],
            ["switch_models.id"],
            name="switches_switch_model_id_fkey",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["target_group_id"],
            ["groups.id"],
            name="switches_target_group_id_fkey",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["target_fixture_id"],
            ["fixtures.id"],
            name="switches_target_fixture_id_fkey",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create group_fixtures table (many-to-many)
    op.create_table(
        "group_fixtures",
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("fixture_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["group_id"], ["groups.id"], name="group_fixtures_group_id_fkey", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["fixture_id"],
            ["fixtures.id"],
            name="group_fixtures_fixture_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("group_id", "fixture_id"),
    )

    # Create group_hierarchy table
    op.create_table(
        "group_hierarchy",
        sa.Column("parent_group_id", sa.Integer(), nullable=False),
        sa.Column("child_group_id", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "parent_group_id != child_group_id",
            name="group_hierarchy_parent_child_check",
        ),
        sa.ForeignKeyConstraint(
            ["parent_group_id"],
            ["groups.id"],
            name="group_hierarchy_parent_group_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["child_group_id"],
            ["groups.id"],
            name="group_hierarchy_child_group_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("parent_group_id", "child_group_id"),
    )

    # Create scenes table
    op.create_table(
        "scenes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("scope_group_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["scope_group_id"],
            ["groups.id"],
            name="scenes_scope_group_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create scene_values table
    op.create_table(
        "scene_values",
        sa.Column("scene_id", sa.Integer(), nullable=False),
        sa.Column("fixture_id", sa.Integer(), nullable=False),
        sa.Column("target_brightness", sa.Integer(), nullable=True),
        sa.Column("target_cct_kelvin", sa.Integer(), nullable=True),
        sa.CheckConstraint(
            "target_brightness BETWEEN 0 AND 1000",
            name="scene_values_target_brightness_check",
        ),
        sa.ForeignKeyConstraint(
            ["scene_id"], ["scenes.id"], name="scene_values_scene_id_fkey", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["fixture_id"],
            ["fixtures.id"],
            name="scene_values_fixture_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("scene_id", "fixture_id"),
    )

    # Create fixture_state table
    op.create_table(
        "fixture_state",
        sa.Column("fixture_id", sa.Integer(), nullable=False),
        sa.Column(
            "current_brightness",
            sa.Integer(),
            nullable=True,
            server_default="0",
        ),
        sa.Column("current_cct", sa.Integer(), nullable=True, server_default="2700"),
        sa.Column("is_on", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("last_updated", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint(
            "current_brightness BETWEEN 0 AND 1000",
            name="fixture_state_current_brightness_check",
        ),
        sa.ForeignKeyConstraint(
            ["fixture_id"],
            ["fixtures.id"],
            name="fixture_state_fixture_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("fixture_id"),
    )

    # Create group_state table
    op.create_table(
        "group_state",
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("circadian_suspended", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("circadian_suspended_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("last_active_scene_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["group_id"], ["groups.id"], name="group_state_group_id_fkey", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["last_active_scene_id"],
            ["scenes.id"],
            name="group_state_last_active_scene_id_fkey",
        ),
        sa.PrimaryKeyConstraint("group_id"),
    )

    # Create indexes
    op.create_index("idx_fixtures_model_id", "fixtures", ["fixture_model_id"])
    op.create_index("idx_fixtures_dmx_channel", "fixtures", ["dmx_channel_start"])
    op.create_index("idx_switches_model_id", "switches", ["switch_model_id"])
    op.create_index("idx_switches_digital_pin", "switches", ["labjack_digital_pin"])
    op.create_index("idx_switches_analog_pin", "switches", ["labjack_analog_pin"])
    op.create_index("idx_switches_target_group", "switches", ["target_group_id"])
    op.create_index("idx_switches_target_fixture", "switches", ["target_fixture_id"])
    op.create_index("idx_group_fixtures_group", "group_fixtures", ["group_id"])
    op.create_index("idx_group_fixtures_fixture", "group_fixtures", ["fixture_id"])
    op.create_index("idx_group_hierarchy_parent", "group_hierarchy", ["parent_group_id"])
    op.create_index("idx_group_hierarchy_child", "group_hierarchy", ["child_group_id"])
    op.create_index("idx_groups_circadian_profile", "groups", ["circadian_profile_id"])
    op.create_index(
        "idx_groups_circadian_enabled",
        "groups",
        ["circadian_enabled"],
        postgresql_where=sa.text("circadian_enabled = true"),
    )
    op.create_index("idx_scenes_scope_group", "scenes", ["scope_group_id"])
    op.create_index("idx_scene_values_scene", "scene_values", ["scene_id"])
    op.create_index("idx_scene_values_fixture", "scene_values", ["fixture_id"])
    op.create_index(
        "idx_fixture_state_is_on",
        "fixture_state",
        ["is_on"],
        postgresql_where=sa.text("is_on = true"),
    )
    op.create_index("idx_fixture_state_last_updated", "fixture_state", ["last_updated"])
    op.create_index(
        "idx_group_state_circadian_suspended",
        "group_state",
        ["circadian_suspended"],
        postgresql_where=sa.text("circadian_suspended = true"),
    )

    # Insert default circadian profiles
    op.execute(
        """
        INSERT INTO circadian_profiles (name, description, curve_points) VALUES
        (
            'Standard Day',
            'Bright day, warm evening. Good for Living Rooms.',
            '[
                {"time": "06:00", "brightness": 0, "cct": 2700},
                {"time": "08:00", "brightness": 900, "cct": 4000},
                {"time": "18:00", "brightness": 900, "cct": 3000},
                {"time": "20:00", "brightness": 400, "cct": 2700},
                {"time": "23:00", "brightness": 0, "cct": 2200}
            ]'::jsonb
        ),
        (
            'Bedroom',
            'Lower intensity, aggressive warm shift in evening.',
            '[
                {"time": "07:00", "brightness": 0, "cct": 2700},
                {"time": "09:00", "brightness": 700, "cct": 4000},
                {"time": "19:00", "brightness": 500, "cct": 2700},
                {"time": "21:00", "brightness": 100, "cct": 2200}
            ]'::jsonb
        )
        """
    )


def downgrade() -> None:
    """Drop all tables"""
    op.drop_index("idx_group_state_circadian_suspended", table_name="group_state")
    op.drop_index("idx_fixture_state_last_updated", table_name="fixture_state")
    op.drop_index("idx_fixture_state_is_on", table_name="fixture_state")
    op.drop_index("idx_scene_values_fixture", table_name="scene_values")
    op.drop_index("idx_scene_values_scene", table_name="scene_values")
    op.drop_index("idx_scenes_scope_group", table_name="scenes")
    op.drop_index("idx_groups_circadian_enabled", table_name="groups")
    op.drop_index("idx_groups_circadian_profile", table_name="groups")
    op.drop_index("idx_group_hierarchy_child", table_name="group_hierarchy")
    op.drop_index("idx_group_hierarchy_parent", table_name="group_hierarchy")
    op.drop_index("idx_group_fixtures_fixture", table_name="group_fixtures")
    op.drop_index("idx_group_fixtures_group", table_name="group_fixtures")
    op.drop_index("idx_switches_target_fixture", table_name="switches")
    op.drop_index("idx_switches_target_group", table_name="switches")
    op.drop_index("idx_switches_analog_pin", table_name="switches")
    op.drop_index("idx_switches_digital_pin", table_name="switches")
    op.drop_index("idx_switches_model_id", table_name="switches")
    op.drop_index("idx_fixtures_dmx_channel", table_name="fixtures")
    op.drop_index("idx_fixtures_model_id", table_name="fixtures")

    op.drop_table("group_state")
    op.drop_table("fixture_state")
    op.drop_table("scene_values")
    op.drop_table("scenes")
    op.drop_table("group_hierarchy")
    op.drop_table("group_fixtures")
    op.drop_table("switches")
    op.drop_table("groups")
    op.drop_table("circadian_profiles")
    op.drop_table("switch_models")
    op.drop_table("fixtures")
    op.drop_table("fixture_models")
