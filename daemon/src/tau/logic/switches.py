"""
Switch Handler

Processes physical switch inputs (buttons, dimmers, rotary encoders) and
translates them into lighting control actions. Handles debouncing, state
tracking, and dimming curves.
"""
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import time
import structlog

from tau.database import get_db_session
from tau.models.switches import Switch, SwitchModel
from tau.control.state_manager import StateManager
from tau.hardware import HardwareManager

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


class SwitchHandler:
    """
    Switch input processing engine

    Monitors physical switch inputs, applies debouncing and filtering,
    and translates raw inputs into lighting control actions based on
    switch configuration.
    """

    def __init__(
        self,
        state_manager: StateManager,
        hardware_manager: HardwareManager,
        hold_threshold: float = 1.0
    ):
        """
        Initialize switch handler

        Args:
            state_manager: Reference to state manager for updating lights
            hardware_manager: Reference to hardware for reading inputs
            hold_threshold: Duration in seconds to consider a press as "hold"
        """
        self.state_manager = state_manager
        self.hardware_manager = hardware_manager
        self.hold_threshold = hold_threshold

        # Switch configurations {switch_id: (Switch, SwitchModel)}
        self.switches: Dict[int, Tuple[Switch, SwitchModel]] = {}

        # Runtime state tracking {switch_id: SwitchState}
        self.switch_states: Dict[int, SwitchState] = {}

        # Statistics
        self.events_processed = 0
        self.switches_loaded = 0

        logger.info("switch_handler_initialized", hold_threshold=hold_threshold)

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

                logger.info("switches_loaded", count=self.switches_loaded)
                return self.switches_loaded

        except Exception as e:
            logger.error(
                "switches_load_failed",
                error=str(e),
                exc_info=True,
            )
            return 0

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
        elif switch.target_group_id:
            self.state_manager.set_group_brightness(
                switch.target_group_id,
                brightness,
                current_time
            )
            logger.debug(
                "switch_toggled_group",
                switch_id=switch.id,
                group_id=switch.target_group_id,
                state="on" if digital_value else "off"
            )

        self.events_processed += 1

    async def _process_retractive_switch(
        self,
        switch: Switch,
        model: SwitchModel,
        state: SwitchState,
        digital_value: Optional[bool],
        current_time: float
    ) -> None:
        """Process a momentary (retractive) switch"""
        if digital_value is None:
            return

        # Check if value changed
        if digital_value == state.last_digital_value:
            # Check for hold event
            if state.is_pressed and state.press_start_time:
                hold_duration = current_time - state.press_start_time
                if hold_duration >= self.hold_threshold:
                    # Generate hold event (once)
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
            # Pressed
            state.is_pressed = True
            state.press_start_time = current_time
            await self._handle_press_event(switch, state, current_time)
        else:
            # Released
            state.is_pressed = False
            state.press_start_time = None
            await self._handle_release_event(switch, state, current_time)

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
        elif switch.target_group_id:
            self.state_manager.set_group_brightness(
                switch.target_group_id,
                brightness,
                current_time
            )
            logger.debug(
                "rotary_adjusted_group",
                switch_id=switch.id,
                group_id=switch.target_group_id,
                brightness=brightness
            )

        self.events_processed += 1

    async def _handle_press_event(
        self,
        switch: Switch,
        state: SwitchState,
        current_time: float
    ) -> None:
        """Handle press event for retractive switch (toggle on)"""
        # Toggle target on
        if switch.target_fixture_id:
            # Get current state and toggle
            current = self.state_manager.get_fixture_state(switch.target_fixture_id)
            new_brightness = 0.0 if (current and current.brightness > 0) else 1.0

            self.state_manager.set_fixture_brightness(
                switch.target_fixture_id,
                new_brightness,
                current_time
            )
            logger.debug(
                "retractive_pressed_fixture",
                switch_id=switch.id,
                fixture_id=switch.target_fixture_id,
                brightness=new_brightness
            )
        elif switch.target_group_id:
            # Toggle group
            current = self.state_manager.get_group_state(switch.target_group_id)
            new_brightness = 0.0 if (current and current.brightness > 0) else 1.0

            self.state_manager.set_group_brightness(
                switch.target_group_id,
                new_brightness,
                current_time
            )
            logger.debug(
                "retractive_pressed_group",
                switch_id=switch.id,
                group_id=switch.target_group_id,
                brightness=new_brightness
            )

    async def _handle_release_event(
        self,
        switch: Switch,
        state: SwitchState,
        current_time: float
    ) -> None:
        """Handle release event for retractive switch"""
        # For now, just log it
        logger.debug("retractive_released", switch_id=switch.id)

    async def _handle_hold_event(
        self,
        switch: Switch,
        state: SwitchState,
        current_time: float
    ) -> None:
        """Handle hold event for retractive switch (held for > threshold)"""
        # TODO: Implement hold actions (e.g., start dimming, activate scene)
        logger.debug("retractive_held", switch_id=switch.id)

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
