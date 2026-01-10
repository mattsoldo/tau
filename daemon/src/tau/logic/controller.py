"""
Lighting Controller

Main coordination logic for the lighting control system. Orchestrates
circadian calculations, scene management, switch processing, and hardware
output on each control loop iteration.
"""
from typing import Optional, Dict, Set, TYPE_CHECKING
import structlog

if TYPE_CHECKING:
    from tau.control.state_manager import StateManager

from tau.hardware import HardwareManager
from tau.logic.circadian import CircadianEngine
from tau.logic.scenes import SceneEngine
from tau.logic.switches import SwitchHandler
from tau.logic.dtw_engine import DTWEngine
from tau.logic.color_mixing import (
    calculate_led_mix,
    calculate_led_mix_simple,
    calculate_led_mix_lumens_only,
    ColorMixParams,
    get_default_chromaticity,
)
from tau.database import get_db_session

logger = structlog.get_logger(__name__)


class LightingController:
    """
    Central lighting control coordinator

    Orchestrates all lighting control logic on each event loop iteration:
    1. Process physical switch inputs
    2. Apply circadian rhythm calculations to enabled groups
    3. Calculate final fixture output values
    4. Send updates to hardware (DMX fixtures, LED drivers)
    """

    def __init__(
        self,
        state_manager: "StateManager",
        hardware_manager: HardwareManager,
        dim_speed_ms: int = 700
    ):
        """
        Initialize lighting controller

        Args:
            state_manager: Reference to state manager
            hardware_manager: Reference to hardware manager
            dim_speed_ms: Time in ms for retractive switch dimming (0-100%)
        """
        self.state_manager = state_manager
        self.hardware_manager = hardware_manager

        # Initialize sub-engines
        self.circadian = CircadianEngine()
        self.scenes = SceneEngine(state_manager)
        self.switches = SwitchHandler(
            state_manager,
            hardware_manager,
            dim_speed_ms=dim_speed_ms
        )
        self.dtw = DTWEngine()

        # Group to circadian profile mapping {group_id: profile_id}
        self.group_circadian_profiles: Dict[int, int] = {}

        # Groups with circadian enabled {group_id}
        self.circadian_enabled_groups: Set[int] = set()

        # Statistics
        self.loop_iterations = 0
        self.hardware_updates = 0

        # Override expiry check counter (check every ~30 seconds at 30 Hz)
        self._expiry_check_counter = 0
        self._expiry_check_interval = 900  # 30 Hz × 30 seconds

        logger.info("lighting_controller_initialized")

    async def initialize(self) -> bool:
        """
        Initialize controller and load configuration

        Returns:
            True if initialization successful
        """
        try:
            # Load switches
            switch_count = await self.switches.load_switches()
            logger.info("switches_loaded", count=switch_count)

            # Load group-to-circadian-profile mappings
            await self._load_circadian_mappings()

            # Initialize DTW engine
            await self.dtw.initialize()
            await self._load_dtw_fixture_configs()
            logger.info("dtw_engine_initialized", enabled=self.dtw.is_enabled)

            logger.info("lighting_controller_ready")
            return True

        except Exception as e:
            logger.error(
                "controller_initialization_failed",
                error=str(e),
                exc_info=True,
            )
            return False

    async def _load_circadian_mappings(self) -> None:
        """Load which groups have circadian profiles enabled"""
        try:
            async with get_db_session() as session:
                from sqlalchemy import select
                from sqlalchemy.orm import selectinload
                from tau.models.groups import Group

                # Load all groups with circadian profiles
                # Eagerly load the 'state' relationship to avoid lazy-loading issues
                query = select(Group).where(Group.circadian_profile_id.isnot(None)).options(
                    selectinload(Group.state)
                )
                result = await session.execute(query)
                groups = result.scalars().all()

                for group in groups:
                    self.group_circadian_profiles[group.id] = group.circadian_profile_id

                    # Check if circadian is enabled for this group
                    # (from group_state.circadian_suspended)
                    if group.state and not group.state.circadian_suspended:
                        self.circadian_enabled_groups.add(group.id)

                        # Ensure profile is loaded
                        await self.circadian.load_profile(group.circadian_profile_id)

                logger.info(
                    "circadian_mappings_loaded",
                    groups_with_circadian=len(self.group_circadian_profiles),
                    groups_enabled=len(self.circadian_enabled_groups),
                )

        except Exception as e:
            logger.error(
                "circadian_mappings_load_failed",
                error=str(e),
                exc_info=True,
            )

    async def _load_dtw_fixture_configs(self) -> None:
        """Load DTW configuration for all fixtures"""
        try:
            async with get_db_session() as session:
                from sqlalchemy import select
                from sqlalchemy.orm import selectinload
                from tau.models.fixtures import Fixture
                from tau.models.groups import GroupFixture

                # Load all fixtures with their models and group memberships in 3 queries:
                # 1. Fixtures with fixture_model
                # 2. Group memberships (via selectinload)
                # 3. Groups (via nested selectinload)
                query = select(Fixture).options(
                    selectinload(Fixture.fixture_model),
                    selectinload(Fixture.group_memberships).selectinload(GroupFixture.group)
                )
                result = await session.execute(query)
                fixtures = result.scalars().all()

                for fixture in fixtures:
                    # Get primary group info (first group the fixture belongs to)
                    group_id = None
                    group_dtw_ignore = False
                    group_dtw_min_cct = None
                    group_dtw_max_cct = None

                    if fixture.group_memberships:
                        # Use first group membership
                        first_membership = fixture.group_memberships[0]
                        group = first_membership.group
                        if group:
                            group_id = group.id
                            group_dtw_ignore = group.dtw_ignore or False
                            group_dtw_min_cct = group.dtw_min_cct_override
                            group_dtw_max_cct = group.dtw_max_cct_override

                    # Get default CCT from fixture model
                    default_cct = None
                    if fixture.fixture_model:
                        default_cct = fixture.fixture_model.cct_max_kelvin

                    # Register fixture with DTW engine
                    self.dtw.register_fixture(
                        fixture_id=fixture.id,
                        dtw_ignore=fixture.dtw_ignore or False,
                        dtw_min_cct_override=fixture.dtw_min_cct_override,
                        dtw_max_cct_override=fixture.dtw_max_cct_override,
                        default_cct=default_cct,
                        group_id=group_id,
                        group_dtw_ignore=group_dtw_ignore,
                        group_dtw_min_cct_override=group_dtw_min_cct,
                        group_dtw_max_cct_override=group_dtw_max_cct
                    )

                logger.info(
                    "dtw_fixture_configs_loaded",
                    fixture_count=len(fixtures)
                )

        except Exception as e:
            logger.error(
                "dtw_fixture_configs_load_failed",
                error=str(e),
                exc_info=True,
            )

    async def process_control_loop(self) -> None:
        """
        Main control loop processing (called at 30 Hz from event loop)

        1. Process switch inputs
        2. Apply circadian calculations
        3. Check for expired overrides (every ~30 seconds)
        4. Update fixture transitions (interpolate current toward goal)
        5. Calculate final fixture states
        6. Update hardware outputs
        """
        self.loop_iterations += 1

        # Step 1: Process physical switch inputs
        await self.switches.process_inputs()

        # Step 2: Apply circadian rhythms to enabled groups
        await self._apply_circadian()

        # Step 3: Check for expired overrides (every ~30 seconds)
        self._expiry_check_counter += 1
        if self._expiry_check_counter >= self._expiry_check_interval:
            # Check in-memory state manager overrides
            expired = self.state_manager.check_override_expiry()
            if expired > 0:
                logger.debug("control_loop_overrides_expired", count=expired)

            # Cleanup expired database overrides and refresh DTW settings
            await self._cleanup_expired_overrides()
            self._expiry_check_counter = 0

        # Step 4: Update fixture transitions (interpolate current toward goal)
        self.state_manager.update_fixture_transitions()

        # Step 5: Calculate final fixture states and update hardware
        await self._update_hardware()

    async def _apply_circadian(self) -> None:
        """Apply circadian calculations to enabled groups"""
        for group_id in self.circadian_enabled_groups:
            profile_id = self.group_circadian_profiles.get(group_id)
            if profile_id is None:
                continue

            # Calculate circadian values for current time
            result = self.circadian.calculate(profile_id)
            if result is None:
                continue

            brightness, cct = result

            # Update group's circadian state
            self.state_manager.set_group_circadian(
                group_id,
                brightness_multiplier=brightness,
                color_temp=cct
            )

    async def _cleanup_expired_overrides(self) -> None:
        """
        Cleanup expired database overrides and refresh DTW settings.

        Called periodically (~every 30 seconds) from the control loop.
        """
        try:
            from tau.models.dtw_helper import cleanup_expired_overrides

            count = await cleanup_expired_overrides()
            if count > 0:
                logger.debug("dtw_db_overrides_cleaned", count=count)

            # Refresh DTW settings periodically
            await self.dtw.refresh_settings()

        except Exception as e:
            logger.error(
                "override_cleanup_failed",
                error=str(e),
                exc_info=True,
            )

    async def _update_hardware(self) -> None:
        """
        Calculate final fixture states and send to hardware

        This is where we merge fixture state + group state + circadian + DTW
        and output to physical hardware.

        CCT priority (highest to lowest):
        1. Active CCT override
        2. Circadian CCT (if circadian is active for fixture's group)
        3. DTW automatic CCT (if DTW is enabled)
        4. Fixture default CCT

        Uses the Planckian locus color mixing algorithm for tunable white
        fixtures when chromaticity parameters are available. Falls back to
        simple linear mixing otherwise.
        """
        # For each registered fixture, calculate effective state and output
        for fixture_id, fixture_state in self.state_manager.fixtures.items():
            # Get effective state (includes group and circadian modifiers)
            effective_state = self.state_manager.get_effective_fixture_state(fixture_id)

            if effective_state is None:
                continue

            # Get DMX configuration from fixture state
            universe = fixture_state.dmx_universe
            start_channel = fixture_state.dmx_channel_start
            secondary_channel = fixture_state.secondary_dmx_channel
            dmx_footprint = fixture_state.dmx_footprint or 1
            fixture_type = fixture_state.fixture_type
            brightness = effective_state.brightness

            supports_cct = (
                dmx_footprint >= 2
                and (fixture_type in (None, "tunable_white", "dim_to_warm"))
            ) or secondary_channel is not None

            # Determine CCT for tunable white fixtures
            # Priority: circadian -> manual CCT -> DTW -> fallback/default
            cct = None
            if supports_cct:
                circadian_cct = None
                if not fixture_state.override_active:
                    for group_id in self.state_manager.fixture_group_memberships.get(fixture_id, set()):
                        group_state = self.state_manager.groups.get(group_id)
                        if group_state and group_state.circadian_enabled and group_state.circadian_color_temp is not None:
                            circadian_cct = group_state.circadian_color_temp
                            break

                if circadian_cct is not None:
                    cct = circadian_cct
                elif fixture_state.manual_cct_active and effective_state.color_temp is not None:
                    cct = effective_state.color_temp
                elif self.dtw.is_enabled:
                    dtw_result = self.dtw.calculate_cct(fixture_id, brightness)
                    cct = dtw_result.cct
                else:
                    cct = effective_state.color_temp

                if cct is None:
                    cct = fixture_state.cct_max or 4000

            # For tunable white fixtures, calculate warm/cool channel values
            if supports_cct and cct is not None:
                cool_channel = secondary_channel if secondary_channel is not None else start_channel + 1

                # Get CCT range from fixture model (with defaults)
                cct_min = fixture_state.cct_min or 2700
                cct_max = fixture_state.cct_max or 6500
                gamma = fixture_state.gamma or 2.2

                # Check calibration level:
                # 1. Full chromaticity (xy + lumens) = best accuracy
                # 2. Lumens only (no xy) = derived xy from CCT, good accuracy
                # 3. Nothing = basic linear mixing
                has_full_chromaticity = (
                    fixture_state.warm_xy_x is not None and
                    fixture_state.warm_xy_y is not None and
                    fixture_state.cool_xy_x is not None and
                    fixture_state.cool_xy_y is not None and
                    fixture_state.warm_lumens is not None and
                    fixture_state.cool_lumens is not None
                )
                has_lumens_only = (
                    not has_full_chromaticity and
                    fixture_state.warm_lumens is not None and
                    fixture_state.cool_lumens is not None
                )

                if has_full_chromaticity:
                    # Use full Planckian locus algorithm with measured chromaticity
                    params = ColorMixParams(
                        warm_cct=cct_min,
                        cool_cct=cct_max,
                        warm_xy=(fixture_state.warm_xy_x, fixture_state.warm_xy_y),
                        cool_xy=(fixture_state.cool_xy_x, fixture_state.cool_xy_y),
                        warm_lumens=fixture_state.warm_lumens,
                        cool_lumens=fixture_state.cool_lumens,
                        pwm_resolution=255,
                        min_duty=0,
                        gamma=gamma,
                    )
                    result = calculate_led_mix(cct, brightness, params)
                    warm_level = result.warm_duty
                    cool_level = result.cool_duty
                elif has_lumens_only:
                    # Use Planckian locus with derived xy from CCT
                    # Less accurate but still has flux compensation
                    result = calculate_led_mix_lumens_only(
                        target_cct=cct,
                        target_brightness=brightness,
                        warm_cct=cct_min,
                        cool_cct=cct_max,
                        warm_lumens=fixture_state.warm_lumens,
                        cool_lumens=fixture_state.cool_lumens,
                        pwm_resolution=255,
                        min_duty=0,
                        gamma=gamma,
                    )
                    warm_level = result.warm_duty
                    cool_level = result.cool_duty
                else:
                    # Fallback to simple mixing with gamma correction
                    warm_level, cool_level = calculate_led_mix_simple(
                        target_cct=cct,
                        target_brightness=brightness,
                        cct_min=cct_min,
                        cct_max=cct_max,
                        pwm_resolution=255,
                        gamma=gamma,
                    )

                if cool_channel == start_channel + 1:
                    dmx_values = [warm_level, cool_level]
                    channel_map = None
                else:
                    dmx_values = [warm_level, cool_level]
                    channel_map = {start_channel: warm_level, cool_channel: cool_level}
            else:
                # Single channel fixture or no CCT info - just use brightness
                dmx_brightness = int(effective_state.brightness * 255)
                dmx_values = [dmx_brightness]
                channel_map = None
                if secondary_channel is not None:
                    dmx_values.append(dmx_brightness)

            # Send to hardware
            try:
                if channel_map:
                    await self.hardware_manager.set_dmx_output(
                        universe=universe,
                        channels=channel_map
                    )
                else:
                    await self.hardware_manager.set_fixture_dmx(
                        universe=universe,
                        start_channel=start_channel,
                        values=dmx_values
                    )
                self.hardware_updates += 1
            except Exception as e:
                logger.error(
                    "hardware_update_failed",
                    fixture_id=fixture_id,
                    error=str(e),
                )

    async def enable_circadian(self, group_id: int) -> bool:
        """
        Enable circadian rhythm for a group

        Args:
            group_id: Group ID

        Returns:
            True if enabled successfully
        """
        if group_id not in self.group_circadian_profiles:
            logger.warning(
                "circadian_enable_failed",
                group_id=group_id,
                reason="No circadian profile assigned to group"
            )
            return False

        profile_id = self.group_circadian_profiles[group_id]

        # Load profile if not already loaded
        if profile_id not in self.circadian.profiles:
            success = await self.circadian.load_profile(profile_id)
            if not success:
                return False

        # Enable circadian for this group
        self.circadian_enabled_groups.add(group_id)

        # Update group state in state manager
        group_state = self.state_manager.get_group_state(group_id)
        if group_state:
            group_state.circadian_enabled = True

        logger.info("circadian_enabled", group_id=group_id, profile_id=profile_id)
        return True

    async def disable_circadian(self, group_id: int) -> bool:
        """
        Disable circadian rhythm for a group

        Args:
            group_id: Group ID

        Returns:
            True if disabled successfully
        """
        if group_id not in self.circadian_enabled_groups:
            return True  # Already disabled

        self.circadian_enabled_groups.remove(group_id)

        # Update group state in state manager
        group_state = self.state_manager.get_group_state(group_id)
        if group_state:
            group_state.circadian_enabled = False

        logger.info("circadian_disabled", group_id=group_id)
        return True

    def set_dim_speed_ms(self, dim_speed_ms: int) -> None:
        """
        Update the dimming speed at runtime (hot-reload)

        Args:
            dim_speed_ms: Time in ms for full brightness range (0-100%)
        """
        self.switches.set_dim_speed_ms(dim_speed_ms)

    def get_statistics(self) -> dict:
        """
        Get controller statistics

        Returns:
            Dictionary with statistics
        """
        return {
            "loop_iterations": self.loop_iterations,
            "hardware_updates": self.hardware_updates,
            "circadian_enabled_groups": len(self.circadian_enabled_groups),
            "circadian": self.circadian.get_statistics(),
            "scenes": self.scenes.get_statistics(),
            "switches": self.switches.get_statistics(),
            "dtw": self.dtw.get_statistics(),
        }
