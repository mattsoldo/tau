"""
Configuration Loader - Initialize runtime state from database

Loads all fixtures, groups, and their last known states from the database
on daemon startup to populate the StateManager.
"""
import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from tau.control.state_manager import StateManager
from tau.database import get_db_session
from tau.models import (
    Fixture,
    FixtureModel,
    Group,
    GroupFixture,
    FixtureState,
    GroupState,
)

logger = structlog.get_logger(__name__)


class ConfigLoader:
    """
    Loads configuration and state from database into StateManager

    Runs once on daemon startup to initialize the runtime state with
    all configured fixtures, groups, and their last known states.
    """

    def __init__(self, state_manager: StateManager):
        """
        Initialize config loader

        Args:
            state_manager: StateManager to populate
        """
        self.state_manager = state_manager
        logger.info("config_loader_initialized")

    async def load_configuration(self) -> None:
        """
        Load all configuration from database into state manager

        This loads:
        - All fixtures with their last known states
        - All groups with their last known states
        - Group membership relationships
        """
        logger.info("loading_configuration")

        try:
            async with get_db_session() as session:
                # Ensure "All Fixtures" system group exists
                await self._ensure_all_fixtures_group(session)

                # Load fixtures
                fixture_count = await self._load_fixtures(session)

                # Load groups
                group_count = await self._load_groups(session)

                # Load group memberships
                membership_count = await self._load_group_memberships(session)

                # Add all fixtures to "All Fixtures" group (in-memory only)
                await self._populate_all_fixtures_group(session)

            logger.info(
                "configuration_loaded",
                fixtures=fixture_count,
                groups=group_count,
                memberships=membership_count,
            )

        except Exception as e:
            logger.error(
                "configuration_load_failed",
                error=str(e),
                exc_info=True,
            )
            raise

    async def _load_fixtures(self, session) -> int:
        """
        Load all fixtures and their states

        Args:
            session: Async database session

        Returns:
            Number of fixtures loaded
        """
        # Query all fixtures with their fixture models eagerly loaded
        result = await session.execute(
            select(Fixture).options(selectinload(Fixture.fixture_model))
        )
        fixtures = result.scalars().all()

        count = 0
        for fixture in fixtures:
            # Register fixture
            self.state_manager.register_fixture(fixture.id)

            # Get the fixture state object
            fixture_state = self.state_manager.fixtures[fixture.id]

            # Load DMX configuration from fixture record
            fixture_state.dmx_channel_start = fixture.dmx_channel_start or 1
            fixture_state.secondary_dmx_channel = fixture.secondary_dmx_channel
            fixture_state.fixture_model_id = fixture.fixture_model_id
            # Universe defaults to 0 (TODO: add dmx_universe column to fixtures table)
            fixture_state.dmx_universe = getattr(fixture, 'dmx_universe', 0) or 0

            # Load color mixing parameters from fixture model
            model = fixture.fixture_model
            if model:
                fixture_state.cct_min = model.cct_min_kelvin
                fixture_state.cct_max = model.cct_max_kelvin
                fixture_state.warm_xy_x = model.warm_xy_x
                fixture_state.warm_xy_y = model.warm_xy_y
                fixture_state.cool_xy_x = model.cool_xy_x
                fixture_state.cool_xy_y = model.cool_xy_y
                fixture_state.warm_lumens = model.warm_lumens
                fixture_state.cool_lumens = model.cool_lumens
                fixture_state.gamma = model.gamma

            # Load saved state if it exists
            state = await session.get(FixtureState, fixture.id)
            if state:
                # Convert int (0-1000) to float (0-1)
                brightness = (state.current_brightness or 0) / 1000.0
                color_temp = state.current_cct

                # Set both goal and current to the persisted value
                # (no transition - they should match on startup)
                fixture_state.goal_brightness = brightness
                fixture_state.current_brightness = brightness
                fixture_state.start_brightness = brightness
                fixture_state.goal_color_temp = color_temp
                fixture_state.current_color_temp = color_temp
                fixture_state.start_color_temp = color_temp

                if state.last_updated:
                    fixture_state.last_updated = state.last_updated.timestamp()

                logger.debug(
                    "fixture_state_loaded",
                    fixture_id=fixture.id,
                    brightness=brightness,
                    dmx_channel=fixture_state.dmx_channel_start,
                )

            count += 1

        return count

    async def _load_groups(self, session) -> int:
        """
        Load all groups and their states

        Args:
            session: Async database session

        Returns:
            Number of groups loaded
        """
        # Query all groups
        result = await session.execute(select(Group))
        groups = result.scalars().all()

        count = 0
        for group in groups:
            # Register group
            self.state_manager.register_group(group.id)

            # Set circadian enabled flag
            group_state = self.state_manager.groups[group.id]
            group_state.circadian_enabled = group.circadian_enabled or False

            # Note: GroupState in database only tracks circadian suspension and last scene
            # For Phase 2, we just load the circadian enabled flag from the group itself
            logger.debug(
                "group_loaded",
                group_id=group.id,
                circadian_enabled=group_state.circadian_enabled,
            )

            count += 1

        return count

    async def _load_group_memberships(self, session) -> int:
        """
        Load group membership relationships

        Args:
            session: Async database session

        Returns:
            Number of memberships loaded
        """
        # Query all group memberships
        result = await session.execute(select(GroupFixture))
        memberships = result.scalars().all()

        count = 0
        for membership in memberships:
            self.state_manager.add_fixture_to_group(
                fixture_id=membership.fixture_id,
                group_id=membership.group_id,
            )
            count += 1

        return count

    async def _ensure_all_fixtures_group(self, session) -> None:
        """
        Ensure the "All Fixtures" system group exists in the database.

        This is a special group that automatically contains all fixtures.
        It cannot be deleted or edited by users.

        Args:
            session: Async database session
        """
        # Check if system group already exists
        result = await session.execute(
            select(Group).where(Group.is_system == True)  # noqa: E712
        )
        system_group = result.scalar_one_or_none()

        if system_group is None:
            # Create the "All Fixtures" system group
            system_group = Group(
                name="All Fixtures",
                description="System group containing all fixtures",
                is_system=True,
                circadian_enabled=False,
            )
            session.add(system_group)
            await session.commit()
            await session.refresh(system_group)
            logger.info(
                "all_fixtures_group_created",
                group_id=system_group.id,
            )
        else:
            logger.debug(
                "all_fixtures_group_exists",
                group_id=system_group.id,
            )

    async def _populate_all_fixtures_group(self, session) -> None:
        """
        Add all fixtures to the "All Fixtures" group in the state manager.

        This is done in-memory only - the group membership is automatic
        and doesn't need to be persisted to the database.

        Args:
            session: Async database session
        """
        # Get the system group
        result = await session.execute(
            select(Group).where(Group.is_system == True)  # noqa: E712
        )
        system_group = result.scalar_one_or_none()

        if system_group is None:
            logger.warning("all_fixtures_group_not_found")
            return

        # Add all fixtures to this group in state manager
        all_fixtures_group_id = system_group.id
        fixture_count = 0

        for fixture_id in self.state_manager.fixtures.keys():
            self.state_manager.add_fixture_to_group(fixture_id, all_fixtures_group_id)
            fixture_count += 1

        logger.info(
            "all_fixtures_group_populated",
            group_id=all_fixtures_group_id,
            fixture_count=fixture_count,
        )
