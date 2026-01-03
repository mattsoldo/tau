"""
State Manager - In-memory state for all fixtures and groups

Maintains the current runtime state of all lighting fixtures and groups
in memory for fast access during the 30 Hz control loop. State is
periodically persisted to the database.

Supports gradual transitions: API calls set "goal" state, and the control
loop interpolates "current" state toward the goal over a configurable duration.
"""
from typing import Dict, Optional, Set
from dataclasses import dataclass
import time
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class FixtureStateData:
    """Runtime state for a single fixture.

    Supports gradual transitions between states. The control loop interpolates
    from start_* values toward goal_* values over transition_duration seconds.

    Attributes:
        goal_brightness: Target brightness (what user/scene requested)
        goal_color_temp: Target CCT (what user/scene requested)
        current_brightness: Actual brightness (interpolating toward goal)
        current_color_temp: Actual CCT (interpolating toward goal)
        start_brightness: Brightness when transition began
        start_color_temp: CCT when transition began
        transition_start: Unix timestamp when transition began
        transition_duration: Seconds to complete transition (0 = instant)
    """
    fixture_id: int
    # Goal state (user intent)
    goal_brightness: float = 0.0
    goal_color_temp: Optional[int] = None
    # Current state (actual output, interpolating toward goal)
    current_brightness: float = 0.0
    current_color_temp: Optional[int] = None
    # Transition start values (where we're interpolating from)
    start_brightness: float = 0.0
    start_color_temp: Optional[int] = None
    # Transition timing
    transition_start: Optional[float] = None  # Unix timestamp
    transition_duration: float = 0.0  # Seconds (0 = instant)
    # Legacy fields for compatibility
    hue: Optional[int] = None
    saturation: Optional[int] = None
    last_updated: Optional[float] = None  # Unix timestamp
    # DMX configuration (loaded from fixture record)
    dmx_universe: int = 0
    dmx_channel_start: int = 1
    secondary_dmx_channel: Optional[int] = None
    fixture_model_id: Optional[int] = None
    # CCT range from fixture model
    cct_min: Optional[int] = None
    cct_max: Optional[int] = None
    # Planckian locus color mixing parameters (from fixture model)
    warm_xy_x: Optional[float] = None
    warm_xy_y: Optional[float] = None
    cool_xy_x: Optional[float] = None
    cool_xy_y: Optional[float] = None
    warm_lumens: Optional[int] = None
    cool_lumens: Optional[int] = None
    gamma: Optional[float] = None

    @property
    def brightness(self) -> float:
        """Alias for current_brightness (backwards compatibility)"""
        return self.current_brightness

    @property
    def color_temp(self) -> Optional[int]:
        """Alias for current_color_temp (backwards compatibility)"""
        return self.current_color_temp


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
        self,
        fixture_id: int,
        brightness: float,
        transition_duration: float = 0.0,
        timestamp: Optional[float] = None
    ) -> bool:
        """
        Set goal brightness for a fixture with optional transition.

        Args:
            fixture_id: Fixture ID
            brightness: Target brightness value (0.0 to 1.0)
            transition_duration: Seconds to transition (0 = instant)
            timestamp: Optional timestamp (defaults to current time)

        Returns:
            True if successful, False if fixture not found
        """
        if fixture_id not in self.fixtures:
            logger.warning("fixture_not_found", fixture_id=fixture_id)
            return False

        # Clamp brightness to valid range
        brightness = max(0.0, min(1.0, brightness))
        now = timestamp or time.time()

        fixture = self.fixtures[fixture_id]
        fixture.goal_brightness = brightness
        fixture.last_updated = now

        if transition_duration > 0:
            # Start a transition from current to goal
            fixture.start_brightness = fixture.current_brightness
            fixture.transition_start = now
            fixture.transition_duration = transition_duration
        else:
            # Instant change - set current to goal immediately
            fixture.current_brightness = brightness
            fixture.start_brightness = brightness
            fixture.transition_start = None
            fixture.transition_duration = 0.0

        self.dirty = True

        logger.debug(
            "fixture_brightness_updated",
            fixture_id=fixture_id,
            goal_brightness=brightness,
            transition_duration=transition_duration,
        )
        return True

    def set_fixture_color_temp(
        self,
        fixture_id: int,
        color_temp: int,
        transition_duration: float = 0.0,
        timestamp: Optional[float] = None
    ) -> bool:
        """
        Set goal color temperature for a fixture with optional transition.

        Args:
            fixture_id: Fixture ID
            color_temp: Target color temperature in Kelvin (2000-6500)
            transition_duration: Seconds to transition (0 = instant)
            timestamp: Optional timestamp (defaults to current time)

        Returns:
            True if successful, False if fixture not found
        """
        if fixture_id not in self.fixtures:
            logger.warning("fixture_not_found", fixture_id=fixture_id)
            return False

        # Clamp color temp to valid range
        color_temp = max(2000, min(6500, color_temp))
        now = timestamp or time.time()

        fixture = self.fixtures[fixture_id]
        fixture.goal_color_temp = color_temp
        fixture.last_updated = now

        if transition_duration > 0:
            # Start a transition from current to goal
            fixture.start_color_temp = fixture.current_color_temp
            fixture.transition_start = now
            fixture.transition_duration = transition_duration
        else:
            # Instant change - set current to goal immediately
            fixture.current_color_temp = color_temp
            fixture.start_color_temp = color_temp
            fixture.transition_start = None
            fixture.transition_duration = 0.0

        self.dirty = True

        logger.debug(
            "fixture_color_temp_updated",
            fixture_id=fixture_id,
            goal_color_temp=color_temp,
            transition_duration=transition_duration,
        )
        return True

    def update_fixture_transitions(self, timestamp: Optional[float] = None) -> int:
        """
        Update all fixture current states based on transition progress.

        Called each control loop iteration (30 Hz) to interpolate current
        values toward goal values for fixtures with active transitions.

        Args:
            timestamp: Current time (defaults to time.time())

        Returns:
            Number of fixtures still transitioning
        """
        now = timestamp or time.time()
        transitioning_count = 0

        for fixture in self.fixtures.values():
            if fixture.transition_start is None or fixture.transition_duration <= 0:
                # No active transition - ensure current matches goal
                if fixture.current_brightness != fixture.goal_brightness:
                    fixture.current_brightness = fixture.goal_brightness
                if fixture.current_color_temp != fixture.goal_color_temp:
                    fixture.current_color_temp = fixture.goal_color_temp
                continue

            # Calculate transition progress (0.0 to 1.0)
            elapsed = now - fixture.transition_start
            progress = min(1.0, elapsed / fixture.transition_duration)

            # Interpolate brightness from start to goal
            fixture.current_brightness = self._lerp(
                fixture.start_brightness, fixture.goal_brightness, progress
            )

            # Interpolate color temp from start to goal
            if fixture.goal_color_temp is not None and fixture.start_color_temp is not None:
                fixture.current_color_temp = round(self._lerp(
                    float(fixture.start_color_temp),
                    float(fixture.goal_color_temp),
                    progress
                ))

            # Check if transition complete
            if progress >= 1.0:
                fixture.current_brightness = fixture.goal_brightness
                fixture.current_color_temp = fixture.goal_color_temp
                fixture.transition_start = None
                fixture.transition_duration = 0.0
                self.dirty = True
            else:
                transitioning_count += 1

        return transitioning_count

    @staticmethod
    def _lerp(start: float, end: float, t: float) -> float:
        """Linear interpolation between start and end."""
        return start + (end - start) * t

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

        fixture = self.fixtures[fixture_id]

        # Start with fixture's current state (what's actually being output)
        effective_brightness = fixture.current_brightness
        effective_color_temp = fixture.current_color_temp

        # Apply group settings (if fixture belongs to any groups)
        groups = self.fixture_group_memberships.get(fixture_id, set())
        for group_id in groups:
            if group_id not in self.groups:
                continue

            group_state = self.groups[group_id]

            # Apply group brightness (multiply)
            effective_brightness *= group_state.brightness

            # Apply circadian if enabled
            if group_state.circadian_enabled:
                effective_brightness *= group_state.circadian_brightness

                # Override color temp with circadian value if set
                if group_state.circadian_color_temp is not None:
                    effective_color_temp = group_state.circadian_color_temp

        # Create a new state object with effective values
        state = FixtureStateData(
            fixture_id=fixture_id,
            goal_brightness=fixture.goal_brightness,
            goal_color_temp=fixture.goal_color_temp,
            current_brightness=effective_brightness,
            current_color_temp=effective_color_temp,
            hue=fixture.hue,
            saturation=fixture.saturation,
            last_updated=fixture.last_updated,
        )

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
