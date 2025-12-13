"""
Lighting Controller

Main coordination logic for the lighting control system. Orchestrates
circadian calculations, scene management, switch processing, and hardware
output on each control loop iteration.
"""
from typing import Optional, Dict, Set
import structlog

from tau.control.state_manager import StateManager
from tau.hardware import HardwareManager
from tau.logic.circadian import CircadianEngine
from tau.logic.scenes import SceneEngine
from tau.logic.switches import SwitchHandler
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
        state_manager: StateManager,
        hardware_manager: HardwareManager
    ):
        """
        Initialize lighting controller

        Args:
            state_manager: Reference to state manager
            hardware_manager: Reference to hardware manager
        """
        self.state_manager = state_manager
        self.hardware_manager = hardware_manager

        # Initialize sub-engines
        self.circadian = CircadianEngine()
        self.scenes = SceneEngine(state_manager)
        self.switches = SwitchHandler(state_manager, hardware_manager)

        # Group to circadian profile mapping {group_id: profile_id}
        self.group_circadian_profiles: Dict[int, int] = {}

        # Groups with circadian enabled {group_id}
        self.circadian_enabled_groups: Set[int] = set()

        # Statistics
        self.loop_iterations = 0
        self.hardware_updates = 0

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

    async def process_control_loop(self) -> None:
        """
        Main control loop processing (called at 30 Hz from event loop)

        1. Process switch inputs
        2. Apply circadian calculations
        3. Calculate final fixture states
        4. Update hardware outputs
        """
        self.loop_iterations += 1

        # Step 1: Process physical switch inputs
        await self.switches.process_inputs()

        # Step 2: Apply circadian rhythms to enabled groups
        await self._apply_circadian()

        # Step 3: Calculate final fixture states and update hardware
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

    async def _update_hardware(self) -> None:
        """
        Calculate final fixture states and send to hardware

        This is where we merge fixture state + group state + circadian
        and output to physical hardware.
        """
        # For each registered fixture, calculate effective state and output
        for fixture_id in self.state_manager.fixtures.keys():
            # Get effective state (includes group and circadian modifiers)
            effective_state = self.state_manager.get_effective_fixture_state(fixture_id)

            if effective_state is None:
                continue

            # TODO: Get fixture model to determine DMX channel mapping
            # For now, assume simple 2-channel tunable white:
            # - Channel 1: Master brightness
            # - Channel 2: CCT (warm/cool balance)

            # Convert brightness (0.0-1.0) to DMX (0-255)
            dmx_brightness = int(effective_state.brightness * 255)

            # TODO: Convert CCT to DMX channel values based on fixture model
            # For now, use a simple mapping for tunable white fixtures
            dmx_values = [dmx_brightness, dmx_brightness]  # Placeholder

            # Send to hardware
            # TODO: Get fixture's DMX universe and start channel from database
            # For now, assume universe 0, and fixture_id determines channel
            try:
                await self.hardware_manager.set_fixture_dmx(
                    universe=0,
                    start_channel=fixture_id,  # TODO: Use actual DMX channel
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
        }
