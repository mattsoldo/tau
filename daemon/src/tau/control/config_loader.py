"""
Configuration Loader - Initialize runtime state from database

Loads all fixtures, groups, and their last known states from the database
on daemon startup to populate the StateManager.
"""
import structlog
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from tau.control.state_manager import StateManager
from tau.database import get_session
from tau.models import (
    Fixture,
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
            async with get_session() as session:
                # Load fixtures
                fixture_count = await self._load_fixtures(session)

                # Load groups
                group_count = await self._load_groups(session)

                # Load group memberships
                membership_count = await self._load_group_memberships(session)

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
        # Query all fixtures
        result = await session.execute(select(Fixture))
        fixtures = result.scalars().all()

        count = 0
        for fixture in fixtures:
            # Register fixture
            self.state_manager.register_fixture(fixture.id)

            # Load saved state if it exists
            state = await session.get(FixtureState, fixture.id)
            if state:
                fixture_state = self.state_manager.fixtures[fixture.id]
                fixture_state.brightness = state.brightness
                fixture_state.color_temp = state.color_temp
                fixture_state.hue = state.hue
                fixture_state.saturation = state.saturation
                if state.last_updated:
                    fixture_state.last_updated = state.last_updated.timestamp()

                logger.debug(
                    "fixture_state_loaded",
                    fixture_id=fixture.id,
                    brightness=state.brightness,
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

            # Load saved state if it exists
            state = await session.get(GroupState, group.id)
            if state:
                group_state.brightness = state.brightness
                group_state.color_temp = state.color_temp
                group_state.hue = state.hue
                group_state.saturation = state.saturation
                group_state.circadian_brightness = state.circadian_brightness
                group_state.circadian_color_temp = state.circadian_color_temp
                if state.last_updated:
                    group_state.last_updated = state.last_updated.timestamp()

                logger.debug(
                    "group_state_loaded",
                    group_id=group.id,
                    brightness=state.brightness,
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
