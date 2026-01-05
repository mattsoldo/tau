"""
Switch Handler

Processes physical switch inputs (buttons, dimmers, rotary encoders) and
translates them into lighting control actions. Handles debouncing, state
tracking, and dimming curves.
"""
from typing import Dict, Optional, Tuple, TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum
import time
import asyncio
import structlog

from tau.database import get_db_session
from tau.models.switches import Switch, SwitchModel
from tau.hardware import HardwareManager
from tau.api.websocket import broadcast_fixture_state_change, broadcast_group_state_change

if TYPE_CHECKING:
    from tau.control.state_manager import StateManager

logger = structlog.get_logger(__name__)


class SwitchEvent(Enum):
    """Switch event types"""
    PRESS = "press"
    RELEASE = "release"
    HOLD = "hold"
    ROTATE_CW = "rotate_cw"  # Clockwise
    ROTATE_CCW = "rotate_ccw"  # Counter-clockwise
    VALUE_CHANGE = "value_change"  # Analog value changed


@dataclass
class SwitchState:
    """Runtime state for a switch"""
    switch_id: int
    last_digital_value: Optional[bool] = None
    last_analog_value: Optional[float] = None
    last_change_time: float = 0.0
    press_start_time: Optional[float] = None
    is_pressed: bool = False
    # Dimming state for retractive switches
    is_dimming: bool = False  # True while actively dimming
    dim_direction: int = 1  # 1 = up (brighten), -1 = down (dim)
    dim_start_brightness: float = 0.0  # Brightness when dimming started
    was_on_at_press: bool = False  # State of target when switch was pressed


class SwitchHandler:
    """
    Switch input processing engine

    Monitors physical switch inputs, applies debouncing and filtering,
    and translates raw inputs into lighting control actions based on
    switch configuration.
    """

    def __init__(
        self,
        state_manager: "StateManager",
        hardware_manager: HardwareManager,
        hold_threshold: float = 1.0,
        dim_speed_ms: int = 700
    ):
        """
        Initialize switch handler

        Args:
            state_manager: Reference to state manager for updating lights
            hardware_manager: Reference to hardware for reading inputs
            hold_threshold: Duration in seconds to consider a press as "hold"
            dim_speed_ms: Time in ms for full brightness range (0-100%) when dimming
        """
        self.state_manager = state_manager
        self.hardware_manager = hardware_manager
        self.hold_threshold = hold_threshold
        self.dim_speed_ms = dim_speed_ms

        # Switch configurations {switch_id: (Switch, SwitchModel)}
        self.switches: Dict[int, Tuple[Switch, SwitchModel]] = {}

        # Runtime state tracking {switch_id: SwitchState}
        self.switch_states: Dict[int, SwitchState] = {}

        # Broadcast throttling for hold events (max once per 100ms per target)
        # Keys are "fixture:{id}" or "group:{id}", values are last broadcast timestamp
        self.last_broadcast_time: Dict[str, float] = {}
        self.broadcast_throttle_ms = 100  # Minimum time between broadcasts

        # Statistics
        self.events_processed = 0
        self.switches_loaded = 0

        logger.info(
            "switch_handler_initialized",
            hold_threshold=hold_threshold,
            dim_speed_ms=dim_speed_ms
        )

    async def load_switches(self) -> int:
        """
        Load all switch configurations from database

        Returns:
            Number of switches loaded
        """
        try:
            async with get_db_session() as session:
                from sqlalchemy import select
                from sqlalchemy.orm import selectinload

                # Load all switches with their models
                query = select(Switch).options(selectinload(Switch.switch_model))
                result = await session.execute(query)
                switches = result.scalars().all()

                for switch in switches:
                    self.switches[switch.id] = (switch, switch.switch_model)
                    self.switch_states[switch.id] = SwitchState(switch_id=switch.id)

                self.switches_loaded = len(switches)

                # Configure LabJack channels based on switch requirements
                await self._configure_hardware_channels()

                logger.info("switches_loaded", count=self.switches_loaded)
                return self.switches_loaded

        except Exception as e:
            logger.error(
                "switches_load_failed",
                error=str(e),
                exc_info=True,
            )
            return 0

    async def _configure_hardware_channels(self) -> None:
        """
        Configure LabJack channels based on switch requirements

        This ensures pins are in the correct mode (digital/analog) for each switch.
        """
        if not hasattr(self.hardware_manager.labjack, 'configure_channel'):
            # Hardware doesn't support dynamic channel configuration (e.g., mock mode)
            return

        try:
            for switch_id, (switch, model) in self.switches.items():
                # Configure digital pin if required
                if model.requires_digital_pin and switch.labjack_digital_pin is not None:
                    await self.hardware_manager.labjack.configure_channel(
                        switch.labjack_digital_pin,
                        'digital-in'
                    )
                    logger.debug(
                        "switch_channel_configured",
                        switch_id=switch_id,
                        channel=switch.labjack_digital_pin,
                        mode="digital-in"
                    )

                # Configure analog pin if required
                if model.requires_analog_pin and switch.labjack_analog_pin is not None:
                    await self.hardware_manager.labjack.configure_channel(
                        switch.labjack_analog_pin,
                        'analog'
                    )
                    logger.debug(
                        "switch_channel_configured",
                        switch_id=switch_id,
                        channel=switch.labjack_analog_pin,
                        mode="analog"
                    )

            logger.info("switch_channels_configured", count=len(self.switches))

        except Exception as e:
            logger.error(
                "switch_channel_configuration_failed",
                error=str(e),
                exc_info=True
            )

    async def process_inputs(self) -> None:
        """
        Process all switch inputs (called from event loop)

        Reads hardware inputs, applies debouncing, detects events,
        and triggers appropriate actions.
        """
        current_time = time.time()

        for switch_id, (switch, model) in self.switches.items():
            state = self.switch_states[switch_id]

            # Read hardware inputs based on switch type
            digital_value = None
            analog_value = None

            if model.requires_digital_pin and switch.labjack_digital_pin is not None:
                # Read digital pin (for simple switches, retractive)
                # Digital reading returns voltage - convert to boolean
                voltage = await self.hardware_manager.read_switch_inputs(
                    [switch.labjack_digital_pin]
                )
                if voltage:
                    # Consider > 1.5V as pressed (TTL logic)
                    # voltage is a dict mapping channel to value
                    digital_value = voltage.get(switch.labjack_digital_pin, 0.0) > 1.5

            if model.requires_analog_pin and switch.labjack_analog_pin is not None:
                # Read analog pin (for rotary encoders, analog dimmers)
                voltage = await self.hardware_manager.read_switch_inputs(
                    [switch.labjack_analog_pin]
                )
                if voltage:
                    # Normalize 0-2.4V to 0.0-1.0
                    # voltage is a dict mapping channel to value
                    analog_value = min(1.0, voltage.get(switch.labjack_analog_pin, 0.0) / 2.4)

            # Process based on input type
            if model.input_type == "switch_simple":
                await self._process_simple_switch(
                    switch, model, state, digital_value, current_time
                )
            elif model.input_type == "retractive":
                await self._process_retractive_switch(
                    switch, model, state, digital_value, current_time
                )
            elif model.input_type == "rotary_abs":
                await self._process_rotary_absolute(
                    switch, model, state, analog_value, current_time
                )
            elif model.input_type == "paddle_composite":
                # TODO: Implement paddle composite (multi-button)
                pass

    async def _get_group_defaults(self, group_id: int) -> Tuple[float, Optional[int]]:
        """
        Get group's default brightness and CCT settings

        Returns:
            Tuple of (brightness 0.0-1.0, cct_kelvin or None)
        """
        try:
            async with get_db_session() as session:
                from sqlalchemy import select
                from tau.models.groups import Group

                result = await session.execute(
                    select(Group).where(Group.id == group_id)
                )
                group = result.scalar_one_or_none()

                if group:
                    # Convert 0-1000 to 0.0-1.0
                    brightness = (group.default_max_brightness or 1000) / 1000.0
                    cct = group.default_cct_kelvin
                    return (brightness, cct)

        except Exception as e:
            logger.warning(
                "failed_to_get_group_defaults",
                group_id=group_id,
                error=str(e)
            )

        # Fallback to 100% brightness, no CCT change
        return (1.0, None)

    async def _process_simple_switch(
        self,
        switch: Switch,
        model: SwitchModel,
        state: SwitchState,
        digital_value: Optional[bool],
        current_time: float
    ) -> None:
        """Process a simple on/off switch"""
        if digital_value is None:
            return

        # Check if value changed
        if digital_value == state.last_digital_value:
            return

        # Apply debouncing
        time_since_change = (current_time - state.last_change_time) * 1000  # ms
        if time_since_change < (model.debounce_ms or 500):
            # Too soon, ignore (bounce)
            return

        # Update state
        state.last_digital_value = digital_value
        state.last_change_time = current_time

        # Toggle target (on if pressed, off if released)
        brightness = 1.0 if digital_value else 0.0

        if switch.target_fixture_id:
            self.state_manager.set_fixture_brightness(
                switch.target_fixture_id,
                brightness,
                current_time
            )
            logger.debug(
                "switch_toggled_fixture",
                switch_id=switch.id,
                fixture_id=switch.target_fixture_id,
                state="on" if digital_value else "off"
            )
            # Broadcast state change via WebSocket
            await self._broadcast_fixture_state(switch.target_fixture_id)
        elif switch.target_group_id:
            # When turning on, use group's default settings
            if digital_value:  # Turning on
                brightness, cct = await self._get_group_defaults(switch.target_group_id)

                self.state_manager.set_group_brightness(
                    switch.target_group_id,
                    brightness,
                    transition_duration=0.5,
                    timestamp=current_time
                )

                # Also set CCT if group has a default
                if cct is not None:
                    self.state_manager.set_group_color_temp(
                        switch.target_group_id,
                        cct,
                        transition_duration=0.5,
                        timestamp=current_time
                    )

                logger.debug(
                    "switch_turned_on_group",
                    switch_id=switch.id,
                    group_id=switch.target_group_id,
                    brightness=brightness,
                    cct=cct
                )
            else:  # Turning off
                self.state_manager.set_group_brightness(
                    switch.target_group_id,
                    0.0,
                    transition_duration=0.5,
                    timestamp=current_time
                )
                logger.debug(
                    "switch_turned_off_group",
                    switch_id=switch.id,
                    group_id=switch.target_group_id
                )
            # Broadcast group state change via WebSocket
            await self._broadcast_group_state(switch.target_group_id)

        self.events_processed += 1

    async def _process_retractive_switch(
        self,
        switch: Switch,
        model: SwitchModel,
        state: SwitchState,
        digital_value: Optional[bool],
        current_time: float
    ) -> None:
        """
        Process a momentary (retractive) switch with dim-on-hold behavior.

        Behavior:
        - Press and hold when OFF: gradually brightens (dim up)
        - Press and hold when ON: gradually dims down
        - Quick press and release: toggles on/off
        - Dimming stops when switch is released
        """
        if digital_value is None:
            return

        # Initialize last_digital_value on first read
        if state.last_digital_value is None:
            state.last_digital_value = digital_value
            logger.debug(
                "retractive_initialized",
                switch_id=switch.id,
                initial_value=digital_value
            )
            return

        # Check if value changed
        if digital_value == state.last_digital_value:
            # No state change - check for hold/dimming while pressed
            if state.is_pressed and state.press_start_time:
                hold_duration = current_time - state.press_start_time
                if hold_duration >= self.hold_threshold:
                    # Start or continue dimming
                    await self._handle_hold_event(switch, state, current_time)
            return

        # Apply debouncing
        time_since_change = (current_time - state.last_change_time) * 1000  # ms
        if time_since_change < (model.debounce_ms or 500):
            return

        # Update state
        state.last_digital_value = digital_value
        state.last_change_time = current_time

        if digital_value:
            # Pressed - record initial state but don't toggle yet
            state.is_pressed = True
            state.press_start_time = current_time
            state.is_dimming = False  # Reset dimming state
            await self._handle_press_event(switch, state, current_time)
        else:
            # Released - stop dimming and potentially toggle
            state.is_pressed = False
            await self._handle_release_event(switch, state, current_time)
            # Reset dimming state after release handling
            state.is_dimming = False
            state.press_start_time = None

        self.events_processed += 1

    async def _process_rotary_absolute(
        self,
        switch: Switch,
        model: SwitchModel,
        state: SwitchState,
        analog_value: Optional[float],
        current_time: float
    ) -> None:
        """Process an absolute rotary encoder (potentiometer)"""
        if analog_value is None:
            return

        # Check if value changed significantly (> 1% change)
        if state.last_analog_value is not None:
            change = abs(analog_value - state.last_analog_value)
            if change < 0.01:
                return

        # Update state
        state.last_analog_value = analog_value
        state.last_change_time = current_time

        # Apply dimming curve
        if model.dimming_curve == "logarithmic":
            # Logarithmic curve feels more natural for dimming
            brightness = analog_value ** 2
        else:
            # Linear
            brightness = analog_value

        # Set target brightness
        if switch.target_fixture_id:
            self.state_manager.set_fixture_brightness(
                switch.target_fixture_id,
                brightness,
                current_time
            )
            logger.debug(
                "rotary_adjusted_fixture",
                switch_id=switch.id,
                fixture_id=switch.target_fixture_id,
                brightness=brightness
            )
            # Broadcast state change via WebSocket
            await self._broadcast_fixture_state(switch.target_fixture_id)
        elif switch.target_group_id:
            self.state_manager.set_group_brightness(
                switch.target_group_id,
                brightness,
                transition_duration=0.1,
                timestamp=current_time
            )
            logger.debug(
                "rotary_adjusted_group",
                switch_id=switch.id,
                group_id=switch.target_group_id,
                brightness=brightness
            )
            # Broadcast group state change via WebSocket
            await self._broadcast_group_state(switch.target_group_id)

        self.events_processed += 1

    async def _handle_press_event(
        self,
        switch: Switch,
        state: SwitchState,
        current_time: float
    ) -> None:
        """
        Handle press event for retractive switch.

        Records the current on/off state for determining dim direction.
        Does NOT toggle - toggling only happens on release if no dimming occurred.
        """
        # Get current brightness to determine dim direction
        current_brightness = 0.0
        if switch.target_fixture_id:
            current = self.state_manager.get_fixture_state(switch.target_fixture_id)
            if current:
                current_brightness = current.brightness
        elif switch.target_group_id:
            # Check fixture states to determine current group brightness
            # (since groups no longer have multiplier state)
            for fixture_id, group_ids in self.state_manager.fixture_group_memberships.items():
                if switch.target_group_id in group_ids:
                    fixture_state = self.state_manager.get_fixture_state(fixture_id)
                    if fixture_state and fixture_state.current_brightness > 0.01:
                        current_brightness = fixture_state.current_brightness
                        break

        # Record whether target was on at press time (for dimming direction)
        state.was_on_at_press = current_brightness > 0
        state.dim_start_brightness = current_brightness

        # Set dim direction: dim down if on, dim up if off
        if state.was_on_at_press:
            state.dim_direction = -1  # Dim down
        else:
            state.dim_direction = 1  # Dim up

        logger.debug(
            "retractive_pressed",
            switch_id=switch.id,
            was_on=state.was_on_at_press,
            dim_direction="down" if state.dim_direction < 0 else "up",
            current_brightness=current_brightness
        )

    async def _handle_release_event(
        self,
        switch: Switch,
        state: SwitchState,
        current_time: float
    ) -> None:
        """
        Handle release event for retractive switch.

        If dimming occurred, just stop dimming (brightness stays where it is).
        If no dimming occurred (quick press), toggle on/off.
        """
        if state.is_dimming:
            # Dimming occurred - stop dimming, keep current brightness
            logger.debug(
                "retractive_dim_stopped",
                switch_id=switch.id,
                final_brightness=state.dim_start_brightness
            )
            # Brightness is already set by hold events, broadcast final state
            if switch.target_fixture_id:
                await self._broadcast_fixture_state(switch.target_fixture_id)
            elif switch.target_group_id:
                await self._broadcast_group_state(switch.target_group_id)
        else:
            # No dimming - this was a quick press, so toggle
            if switch.target_fixture_id:
                current = self.state_manager.get_fixture_state(switch.target_fixture_id)
                new_brightness = 0.0 if (current and current.brightness > 0) else 1.0

                self.state_manager.set_fixture_brightness(
                    switch.target_fixture_id,
                    new_brightness,
                    transition_duration=0.0,  # Instant toggle
                    timestamp=current_time
                )
                logger.debug(
                    "retractive_toggled_fixture",
                    switch_id=switch.id,
                    fixture_id=switch.target_fixture_id,
                    brightness=new_brightness
                )
                # Broadcast state change via WebSocket
                await self._broadcast_fixture_state(switch.target_fixture_id)
            elif switch.target_group_id:
                current = self.state_manager.get_group_state(switch.target_group_id)
                is_currently_on = current and current.brightness > 0

                if is_currently_on:
                    # Turning off
                    self.state_manager.set_group_brightness(
                        switch.target_group_id,
                        0.0,
                        timestamp=current_time
                    )
                    logger.debug(
                        "retractive_toggled_group_off",
                        switch_id=switch.id,
                        group_id=switch.target_group_id
                    )
                else:
                    # Turning on - use group defaults
                    brightness, cct = await self._get_group_defaults(switch.target_group_id)

                    self.state_manager.set_group_brightness(
                        switch.target_group_id,
                        brightness,
                        timestamp=current_time
                    )

                    # Also set CCT if group has a default
                    if cct is not None:
                        self.state_manager.set_group_color_temp(
                            switch.target_group_id,
                            cct,
                            timestamp=current_time
                        )

                    logger.debug(
                        "retractive_toggled_group_on",
                        switch_id=switch.id,
                        group_id=switch.target_group_id,
                        brightness=brightness,
                        cct=cct
                    )
                # Broadcast group state change via WebSocket
                await self._broadcast_group_state(switch.target_group_id)

    async def _handle_hold_event(
        self,
        switch: Switch,
        state: SwitchState,
        current_time: float
    ) -> None:
        """
        Handle hold event for retractive switch (held for > threshold).

        Calculates and applies brightness based on hold duration and dim direction:
        - If target was OFF at press: dims UP from 0% toward 100%
        - If target was ON at press: dims DOWN toward 0%

        Dimming rate is controlled by dim_speed_ms (time for 0-100% change).
        """
        if not state.is_dimming:
            # First hold event - mark as dimming
            state.is_dimming = True
            # Reset dim start brightness to current value at start of dimming
            if switch.target_fixture_id:
                current = self.state_manager.get_fixture_state(switch.target_fixture_id)
                if current:
                    state.dim_start_brightness = current.brightness
            elif switch.target_group_id:
                current = self.state_manager.get_group_state(switch.target_group_id)
                if current:
                    state.dim_start_brightness = current.brightness

            logger.debug(
                "retractive_dim_started",
                switch_id=switch.id,
                direction="up" if state.dim_direction > 0 else "down",
                start_brightness=state.dim_start_brightness
            )

        # Calculate new brightness based on time held
        # Time since dimming started (subtract hold_threshold since that's when dimming begins)
        hold_duration = current_time - state.press_start_time - self.hold_threshold
        hold_duration = max(0.0, hold_duration)

        # Calculate brightness change: full range (0 to 1) in dim_speed_ms
        dim_speed_seconds = self.dim_speed_ms / 1000.0
        if dim_speed_seconds <= 0:
            brightness_change = 1.0  # Instant
        else:
            brightness_change = hold_duration / dim_speed_seconds

        # Apply direction and calculate new brightness
        if state.dim_direction > 0:
            # Dimming up from 0
            new_brightness = min(1.0, brightness_change)
        else:
            # Dimming down from start brightness
            new_brightness = max(0.0, state.dim_start_brightness - brightness_change)

        # Clamp to valid range
        new_brightness = max(0.0, min(1.0, new_brightness))

        # Apply brightness (instant, no transition - continuous updates)
        if switch.target_fixture_id:
            self.state_manager.set_fixture_brightness(
                switch.target_fixture_id,
                new_brightness,
                transition_duration=0.0,
                timestamp=current_time
            )
        elif switch.target_group_id:
            self.state_manager.set_group_brightness(
                switch.target_group_id,
                new_brightness,
                timestamp=current_time
            )

        logger.debug(
            "retractive_dimming",
            switch_id=switch.id,
            brightness=round(new_brightness, 3),
            hold_duration=round(hold_duration, 3)
        )

        # Broadcast state change with throttling for real-time updates
        # (prevents overwhelming WebSocket clients during continuous dimming)
        if switch.target_fixture_id:
            await self._broadcast_fixture_state_throttled(switch.target_fixture_id, current_time)
        elif switch.target_group_id:
            await self._broadcast_group_state_throttled(switch.target_group_id, current_time)

    async def _broadcast_fixture_state(self, fixture_id: int) -> None:
        """
        Broadcast fixture state change via WebSocket.

        Args:
            fixture_id: ID of the fixture that changed
        """
        try:
            state = self.state_manager.get_fixture_state(fixture_id)
            if state:
                await broadcast_fixture_state_change(
                    fixture_id=fixture_id,
                    brightness=state.goal_brightness,
                    color_temp=state.goal_color_temp
                )
        except Exception as e:
            # Log error but don't crash the switch handler
            logger.error(f"Failed to broadcast fixture {fixture_id} state: {e}")

    async def _broadcast_group_state(self, group_id: int) -> None:
        """
        Broadcast group state change via WebSocket.

        Broadcasts for all fixtures in the group.

        Args:
            group_id: ID of the group that changed
        """
        try:
            group_state = self.state_manager.get_group_state(group_id)
            if group_state:
                await broadcast_group_state_change(
                    group_id=group_id,
                    brightness=group_state.brightness,
                    color_temp=group_state.circadian_color_temp if group_state.circadian_enabled else None
                )

            # Also broadcast individual fixture states for the group
            for fixture_id, group_ids in self.state_manager.fixture_group_memberships.items():
                if group_id in group_ids:
                    await self._broadcast_fixture_state(fixture_id)
        except Exception as e:
            # Log error but don't crash the switch handler
            logger.error(f"Failed to broadcast group {group_id} state: {e}")

    async def _broadcast_fixture_state_throttled(self, fixture_id: int, current_time: float) -> None:
        """
        Broadcast fixture state change with throttling.

        Only broadcasts if enough time has passed since the last broadcast
        for this fixture (controlled by broadcast_throttle_ms).

        Args:
            fixture_id: ID of the fixture that changed
            current_time: Current timestamp in seconds
        """
        key = f"fixture:{fixture_id}"
        last_broadcast = self.last_broadcast_time.get(key, 0)
        time_since_last = (current_time - last_broadcast) * 1000  # Convert to ms

        if time_since_last >= self.broadcast_throttle_ms:
            await self._broadcast_fixture_state(fixture_id)
            self.last_broadcast_time[key] = current_time

    async def _broadcast_group_state_throttled(self, group_id: int, current_time: float) -> None:
        """
        Broadcast group state change with throttling.

        Only broadcasts if enough time has passed since the last broadcast
        for this group (controlled by broadcast_throttle_ms).

        Args:
            group_id: ID of the group that changed
            current_time: Current timestamp in seconds
        """
        key = f"group:{group_id}"
        last_broadcast = self.last_broadcast_time.get(key, 0)
        time_since_last = (current_time - last_broadcast) * 1000  # Convert to ms

        if time_since_last >= self.broadcast_throttle_ms:
            await self._broadcast_group_state(group_id)
            self.last_broadcast_time[key] = current_time

    def get_statistics(self) -> dict:
        """
        Get handler statistics

        Returns:
            Dictionary with statistics
        """
        return {
            "switches_loaded": self.switches_loaded,
            "events_processed": self.events_processed,
            "active_switches": len(self.switch_states),
        }
