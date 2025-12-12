"""
State Manager - In-memory state for all fixtures and groups

Maintains the current runtime state of all lighting fixtures and groups
in memory for fast access during the 30 Hz control loop. State is
periodically persisted to the database.
"""
from typing import Dict, Optional, Set
from dataclasses import dataclass
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class FixtureStateData:
    """Runtime state for a single fixture"""
    fixture_id: int
    brightness: float = 0.0
    color_temp: Optional[int] = None
    hue: Optional[int] = None
    saturation: Optional[int] = None
    last_updated: Optional[float] = None  # Unix timestamp


@dataclass
class GroupStateData:
    """Runtime state for a group"""
    group_id: int
    brightness: float = 0.0
    color_temp: Optional[int] = None
    hue: Optional[int] = None
    saturation: Optional[int] = None
    circadian_enabled: bool = False
    circadian_brightness: float = 1.0  # 0.0 to 1.0 multiplier
    circadian_color_temp: Optional[int] = None
    last_updated: Optional[float] = None  # Unix timestamp


class StateManager:
    """
    Central state manager for all lighting control

    Maintains in-memory state for fast access during real-time operations.
    All state modifications should go through this manager to ensure
    consistency and proper event handling.
    """

    def __init__(self):
        """Initialize the state manager"""
        # Fixture state indexed by fixture_id
        self.fixtures: Dict[int, FixtureStateData] = {}

        # Group state indexed by group_id
        self.groups: Dict[int, GroupStateData] = {}

        # Mapping of fixture_id to set of group_ids it belongs to
        self.fixture_group_memberships: Dict[int, Set[int]] = {}

        # Flag to track if state has been modified since last persistence
        self.dirty = False

        logger.info("state_manager_initialized")

    def register_fixture(self, fixture_id: int) -> None:
        """
        Register a new fixture with default state

        Args:
            fixture_id: Fixture ID from database
        """
        if fixture_id not in self.fixtures:
            self.fixtures[fixture_id] = FixtureStateData(fixture_id=fixture_id)
            self.fixture_group_memberships[fixture_id] = set()
            logger.debug("fixture_registered", fixture_id=fixture_id)

    def register_group(self, group_id: int) -> None:
        """
        Register a new group with default state

        Args:
            group_id: Group ID from database
        """
        if group_id not in self.groups:
            self.groups[group_id] = GroupStateData(group_id=group_id)
            logger.debug("group_registered", group_id=group_id)

    def add_fixture_to_group(self, fixture_id: int, group_id: int) -> None:
        """
        Register that a fixture belongs to a group

        Args:
            fixture_id: Fixture ID
            group_id: Group ID
        """
        if fixture_id not in self.fixture_group_memberships:
            self.fixture_group_memberships[fixture_id] = set()

        self.fixture_group_memberships[fixture_id].add(group_id)
        logger.debug("fixture_added_to_group", fixture_id=fixture_id, group_id=group_id)

    def get_fixture_state(self, fixture_id: int) -> Optional[FixtureStateData]:
        """
        Get current state for a fixture

        Args:
            fixture_id: Fixture ID

        Returns:
            FixtureStateData or None if not found
        """
        return self.fixtures.get(fixture_id)

    def get_group_state(self, group_id: int) -> Optional[GroupStateData]:
        """
        Get current state for a group

        Args:
            group_id: Group ID

        Returns:
            GroupStateData or None if not found
        """
        return self.groups.get(group_id)

    def set_fixture_brightness(
        self, fixture_id: int, brightness: float, timestamp: Optional[float] = None
    ) -> bool:
        """
        Set brightness for a fixture

        Args:
            fixture_id: Fixture ID
            brightness: Brightness value (0.0 to 1.0)
            timestamp: Optional timestamp (defaults to None)

        Returns:
            True if successful, False if fixture not found
        """
        if fixture_id not in self.fixtures:
            logger.warning("fixture_not_found", fixture_id=fixture_id)
            return False

        # Clamp brightness to valid range
        brightness = max(0.0, min(1.0, brightness))

        self.fixtures[fixture_id].brightness = brightness
        self.fixtures[fixture_id].last_updated = timestamp
        self.dirty = True

        logger.debug(
            "fixture_brightness_updated",
            fixture_id=fixture_id,
            brightness=brightness,
        )
        return True

    def set_fixture_color_temp(
        self, fixture_id: int, color_temp: int, timestamp: Optional[float] = None
    ) -> bool:
        """
        Set color temperature for a fixture

        Args:
            fixture_id: Fixture ID
            color_temp: Color temperature in Kelvin (2000-6500)
            timestamp: Optional timestamp

        Returns:
            True if successful, False if fixture not found
        """
        if fixture_id not in self.fixtures:
            logger.warning("fixture_not_found", fixture_id=fixture_id)
            return False

        # Clamp color temp to valid range
        color_temp = max(2000, min(6500, color_temp))

        self.fixtures[fixture_id].color_temp = color_temp
        self.fixtures[fixture_id].last_updated = timestamp
        self.dirty = True

        logger.debug(
            "fixture_color_temp_updated",
            fixture_id=fixture_id,
            color_temp=color_temp,
        )
        return True

    def set_group_brightness(
        self, group_id: int, brightness: float, timestamp: Optional[float] = None
    ) -> bool:
        """
        Set brightness for a group

        Args:
            group_id: Group ID
            brightness: Brightness value (0.0 to 1.0)
            timestamp: Optional timestamp

        Returns:
            True if successful, False if group not found
        """
        if group_id not in self.groups:
            logger.warning("group_not_found", group_id=group_id)
            return False

        # Clamp brightness to valid range
        brightness = max(0.0, min(1.0, brightness))

        self.groups[group_id].brightness = brightness
        self.groups[group_id].last_updated = timestamp
        self.dirty = True

        logger.debug(
            "group_brightness_updated",
            group_id=group_id,
            brightness=brightness,
        )
        return True

    def set_group_circadian(
        self,
        group_id: int,
        brightness_multiplier: float,
        color_temp: Optional[int],
        timestamp: Optional[float] = None,
    ) -> bool:
        """
        Update circadian values for a group

        Args:
            group_id: Group ID
            brightness_multiplier: Circadian brightness multiplier (0.0 to 1.0)
            color_temp: Circadian color temperature in Kelvin
            timestamp: Optional timestamp

        Returns:
            True if successful, False if group not found
        """
        if group_id not in self.groups:
            logger.warning("group_not_found", group_id=group_id)
            return False

        brightness_multiplier = max(0.0, min(1.0, brightness_multiplier))

        self.groups[group_id].circadian_brightness = brightness_multiplier
        self.groups[group_id].circadian_color_temp = color_temp
        self.groups[group_id].last_updated = timestamp
        self.dirty = True

        logger.debug(
            "group_circadian_updated",
            group_id=group_id,
            brightness=brightness_multiplier,
            color_temp=color_temp,
        )
        return True

    def get_effective_fixture_state(
        self, fixture_id: int
    ) -> Optional[FixtureStateData]:
        """
        Get effective state for a fixture, considering group memberships
        and circadian rhythms

        This calculates the final output state by applying group settings
        and circadian multipliers to the fixture's base state.

        Args:
            fixture_id: Fixture ID

        Returns:
            FixtureStateData with effective values, or None if not found
        """
        if fixture_id not in self.fixtures:
            return None

        # Start with fixture's own state
        state = FixtureStateData(
            fixture_id=fixture_id,
            brightness=self.fixtures[fixture_id].brightness,
            color_temp=self.fixtures[fixture_id].color_temp,
            hue=self.fixtures[fixture_id].hue,
            saturation=self.fixtures[fixture_id].saturation,
            last_updated=self.fixtures[fixture_id].last_updated,
        )

        # Apply group settings (if fixture belongs to any groups)
        groups = self.fixture_group_memberships.get(fixture_id, set())
        for group_id in groups:
            if group_id not in self.groups:
                continue

            group_state = self.groups[group_id]

            # Apply group brightness (multiply)
            state.brightness *= group_state.brightness

            # Apply circadian if enabled
            if group_state.circadian_enabled:
                state.brightness *= group_state.circadian_brightness

                # Override color temp with circadian value if set
                if group_state.circadian_color_temp is not None:
                    state.color_temp = group_state.circadian_color_temp

        return state

    def get_statistics(self) -> dict:
        """
        Get state manager statistics

        Returns:
            Dictionary with statistics
        """
        return {
            "fixture_count": len(self.fixtures),
            "group_count": len(self.groups),
            "dirty": self.dirty,
        }

    def mark_clean(self) -> None:
        """Mark state as clean (called after persistence)"""
        self.dirty = False

    def clear(self) -> None:
        """Clear all state (for testing)"""
        self.fixtures.clear()
        self.groups.clear()
        self.fixture_group_memberships.clear()
        self.dirty = False
        logger.info("state_manager_cleared")
