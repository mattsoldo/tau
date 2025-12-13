#!/usr/bin/env python3
"""
Load Example Configuration

Loads the example configuration YAML file into the database.
This script demonstrates how to populate a Tau system with fixtures,
groups, scenes, and circadian profiles.

Usage:
    python scripts/load_example_config.py [config_file]

If no config file is specified, uses examples/example_config.yaml
"""
import asyncio
import sys
import yaml
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tau.database import init_database, get_db_session
from tau.config import get_settings
from tau.models.fixtures import FixtureModel, Fixture
from tau.models.groups import Group, GroupFixture
from tau.models.circadian import CircadianProfile
from tau.models.scenes import Scene, SceneValue
from tau.models.switches import SwitchModel, Switch
from tau.models.state import FixtureState, GroupState


async def load_configuration(config_file: str):
    """Load configuration from YAML file"""
    print(f"Loading configuration from: {config_file}")

    # Read YAML
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)

    # Initialize database
    settings = get_settings()
    await init_database(settings.database_url)

    async with get_db_session() as session:
        # Track created objects for reference lookups
        fixture_models_map = {}
        fixtures_map = {}
        groups_map = {}
        circadian_profiles_map = {}
        switch_models_map = {}

        # 1. Create Fixture Models
        print("\n1. Creating Fixture Models...")
        for model_data in config.get('fixture_models', []):
            model = FixtureModel(**model_data)
            session.add(model)
            await session.flush()
            fixture_models_map[f"{model.manufacturer} {model.model}"] = model
            print(f"   ✓ {model.manufacturer} {model.model}")

        # 2. Create Fixtures
        print("\n2. Creating Fixtures...")
        for fixture_data in config.get('fixtures', []):
            model_name = fixture_data.pop('model')
            model = fixture_models_map.get(model_name)

            if not model:
                print(f"   ✗ Fixture model not found: {model_name}")
                continue

            fixture = Fixture(
                name=fixture_data['name'],
                fixture_model_id=model.id,
                dmx_channel_start=fixture_data['dmx_channel_start']
            )
            session.add(fixture)
            await session.flush()

            # Create initial state
            state = FixtureState(
                fixture_id=fixture.id,
                current_brightness=0,
                current_cct=2700,
                is_on=False
            )
            session.add(state)

            fixtures_map[fixture.name] = fixture
            print(f"   ✓ {fixture.name} (DMX channel {fixture.dmx_channel_start})")

        # 3. Create Circadian Profiles
        print("\n3. Creating Circadian Profiles...")
        for profile_data in config.get('circadian_profiles', []):
            profile = CircadianProfile(
                name=profile_data['name'],
                description=profile_data.get('description'),
                curve_points=profile_data['keyframes']  # Note: YAML uses 'keyframes', DB uses 'curve_points'
            )
            session.add(profile)
            await session.flush()
            circadian_profiles_map[profile.name] = profile
            print(f"   ✓ {profile.name} ({len(profile.curve_points)} keyframes)")

        # 4. Create Groups
        print("\n4. Creating Groups...")
        for group_data in config.get('groups', []):
            fixture_names = group_data.pop('fixtures', [])
            circadian_profile_name = group_data.pop('circadian_profile', None)

            # Find circadian profile if specified
            circadian_profile_id = None
            if circadian_profile_name:
                profile = circadian_profiles_map.get(circadian_profile_name)
                if profile:
                    circadian_profile_id = profile.id

            group = Group(
                name=group_data['name'],
                description=group_data.get('description'),
                circadian_enabled=group_data.get('circadian_enabled', False),
                circadian_profile_id=circadian_profile_id
            )
            session.add(group)
            await session.flush()

            # Create initial state
            state = GroupState(
                group_id=group.id,
                circadian_suspended=not group.circadian_enabled
            )
            session.add(state)

            # Add fixture memberships
            for fixture_name in fixture_names:
                fixture = fixtures_map.get(fixture_name)
                if fixture:
                    membership = GroupFixture(
                        group_id=group.id,
                        fixture_id=fixture.id
                    )
                    session.add(membership)

            groups_map[group.name] = group
            print(f"   ✓ {group.name} ({len(fixture_names)} fixtures)")

        # 5. Create Scenes
        print("\n5. Creating Scenes...")
        for scene_data in config.get('scenes', []):
            values_data = scene_data.pop('values', [])
            scope_group_name = scene_data.pop('scope_group', None)

            # Find scope group if specified
            scope_group_id = None
            if scope_group_name:
                group = groups_map.get(scope_group_name)
                if group:
                    scope_group_id = group.id

            scene = Scene(
                name=scene_data['name'],
                scope_group_id=scope_group_id
            )
            session.add(scene)
            await session.flush()

            # Create scene values
            for value_data in values_data:
                fixture_name = value_data['fixture']
                fixture = fixtures_map.get(fixture_name)

                if fixture:
                    scene_value = SceneValue(
                        scene_id=scene.id,
                        fixture_id=fixture.id,
                        target_brightness=value_data.get('brightness'),
                        target_cct_kelvin=value_data.get('cct')
                    )
                    session.add(scene_value)

            print(f"   ✓ {scene.name} ({len(values_data)} fixtures)")

        # 6. Create Switch Models
        print("\n6. Creating Switch Models...")
        for model_data in config.get('switch_models', []):
            model = SwitchModel(**model_data)
            session.add(model)
            await session.flush()
            switch_models_map[f"{model.manufacturer} {model.model}"] = model
            print(f"   ✓ {model.manufacturer} {model.model}")

        # 7. Create Switches
        print("\n7. Creating Switches...")
        for switch_data in config.get('switches', []):
            model_name = switch_data.pop('model')
            target_group_name = switch_data.pop('target_group', None)
            target_fixture_name = switch_data.pop('target_fixture', None)

            model = switch_models_map.get(model_name)
            if not model:
                print(f"   ✗ Switch model not found: {model_name}")
                continue

            # Find target
            target_group_id = None
            target_fixture_id = None

            if target_group_name:
                group = groups_map.get(target_group_name)
                if group:
                    target_group_id = group.id

            if target_fixture_name:
                fixture = fixtures_map.get(target_fixture_name)
                if fixture:
                    target_fixture_id = fixture.id

            switch = Switch(
                name=switch_data.get('name'),
                switch_model_id=model.id,
                labjack_digital_pin=switch_data.get('labjack_digital_pin'),
                labjack_analog_pin=switch_data.get('labjack_analog_pin'),
                target_group_id=target_group_id,
                target_fixture_id=target_fixture_id
            )
            session.add(switch)
            print(f"   ✓ {switch.name or 'Unnamed switch'}")

        # Commit all changes
        await session.commit()

    print("\n" + "=" * 60)
    print("✅ Configuration loaded successfully!")
    print("=" * 60)
    print(f"\nSummary:")
    print(f"  - {len(fixture_models_map)} fixture models")
    print(f"  - {len(fixtures_map)} fixtures")
    print(f"  - {len(circadian_profiles_map)} circadian profiles")
    print(f"  - {len(groups_map)} groups")
    print(f"  - {len(config.get('scenes', []))} scenes")
    print(f"  - {len(switch_models_map)} switch models")
    print(f"  - {len(config.get('switches', []))} switches")
    print()


def main():
    """Main entry point"""
    # Determine config file
    if len(sys.argv) > 1:
        config_file = sys.argv[1]
    else:
        # Use default example config
        script_dir = Path(__file__).parent.parent
        config_file = script_dir / "examples" / "example_config.yaml"

    if not Path(config_file).exists():
        print(f"Error: Config file not found: {config_file}")
        sys.exit(1)

    # Load configuration
    asyncio.run(load_configuration(str(config_file)))


if __name__ == "__main__":
    main()
