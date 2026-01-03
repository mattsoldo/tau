"""
Raspberry Pi GPIO Driver - Hardware interface for Pi GPIO pins

This module provides GPIO-based switch input and PWM output control
for Raspberry Pi devices. It implements the same interface as the
LabJack driver, allowing the system to work with either hardware.

Installation (on Raspberry Pi):
    pip install gpiozero pigpio

For hardware PWM support, the pigpio daemon must be running:
    sudo pigpiod

Supported GPIO Features:
- Digital inputs for switch detection (with pull-up/pull-down)
- Hardware PWM outputs for LED dimming (via pigpio)
- Analog input simulation via ADC (optional, requires MCP3008/MCP3208)
"""
from typing import Dict, List, Optional, Any
import asyncio
import structlog

from tau.hardware.base import LabJackInterface

logger = structlog.get_logger(__name__)

# Default GPIO pin mappings for switch inputs
# BCM pin numbering
DEFAULT_INPUT_PINS = {
    0: 17,   # Channel 0 -> GPIO 17
    1: 27,   # Channel 1 -> GPIO 27
    2: 22,   # Channel 2 -> GPIO 22
    3: 23,   # Channel 3 -> GPIO 23
    4: 24,   # Channel 4 -> GPIO 24
    5: 25,   # Channel 5 -> GPIO 25
    6: 5,    # Channel 6 -> GPIO 5
    7: 6,    # Channel 7 -> GPIO 6
}

# Default PWM output pins
DEFAULT_PWM_PINS = {
    0: 12,   # PWM channel 0 -> GPIO 12 (hardware PWM)
    1: 13,   # PWM channel 1 -> GPIO 13 (hardware PWM)
}


class GPIODriver(LabJackInterface):
    """
    Raspberry Pi GPIO driver implementing the LabJack interface

    This driver allows the Tau lighting system to run on a Raspberry Pi
    using GPIO pins for switch inputs and PWM outputs for LED control.

    Features:
    - Digital input reading with configurable pull-up/pull-down
    - Hardware PWM output via pigpio for smooth dimming
    - Optional analog input via SPI ADC (MCP3008/MCP3208)
    """

    def __init__(
        self,
        input_pins: Optional[Dict[int, int]] = None,
        pwm_pins: Optional[Dict[int, int]] = None,
        use_pigpio: bool = True,
        pull_up: bool = True,
    ):
        """
        Initialize Raspberry Pi GPIO driver

        Args:
            input_pins: Mapping of channel numbers to GPIO BCM pin numbers
            pwm_pins: Mapping of PWM channel numbers to GPIO BCM pin numbers
            use_pigpio: Use pigpio for hardware PWM (recommended)
            pull_up: Enable internal pull-up resistors on inputs
        """
        super().__init__("RaspberryPi-GPIO")

        self.input_pin_map = input_pins or DEFAULT_INPUT_PINS.copy()
        self.pwm_pin_map = pwm_pins or DEFAULT_PWM_PINS.copy()
        self.use_pigpio = use_pigpio
        self.pull_up = pull_up

        # GPIO library instances (set on connect)
        self._gpio = None
        self._pi = None  # pigpio instance for hardware PWM

        # Track digital input states
        self.digital_inputs: Dict[int, bool] = {i: False for i in range(16)}
        self.digital_outputs: Dict[int, bool] = {i: False for i in range(16)}

        # Track channel modes
        self.channel_modes: Dict[int, str] = {i: 'digital-in' for i in range(16)}

        # Track PWM outputs (duty cycle 0.0 to 1.0)
        self.pwm_outputs: Dict[int, float] = {0: 0.0, 1: 0.0}

        # For analog input simulation (if ADC is connected)
        self.analog_inputs: Dict[int, float] = {i: 0.0 for i in range(16)}
        self._adc = None

        # Statistics
        self.read_count = 0
        self.write_count = 0
        self.error_count = 0

        # Connection state
        self._connected = False

        logger.info(
            "gpio_driver_initialized",
            input_pins=self.input_pin_map,
            pwm_pins=self.pwm_pin_map,
            use_pigpio=use_pigpio,
        )

    async def connect(self) -> bool:
        """
        Connect to Raspberry Pi GPIO

        Returns:
            True if connection successful
        """
        try:
            # Try to import gpiozero
            try:
                from gpiozero import Button, LED, OutputDevice
                from gpiozero.pins.pigpio import PiGPIOFactory

                self._gpio_module = True
            except ImportError:
                logger.error(
                    "gpiozero_not_installed",
                    message="gpiozero library not installed. Run: pip install gpiozero"
                )
                return False

            # Try to use pigpio for hardware PWM
            if self.use_pigpio:
                try:
                    import pigpio
                    self._pi = pigpio.pi()
                    if not self._pi.connected:
                        logger.warning(
                            "pigpio_not_connected",
                            message="pigpio daemon not running. Start with: sudo pigpiod"
                        )
                        self._pi = None
                except ImportError:
                    logger.warning(
                        "pigpio_not_installed",
                        message="pigpio not installed. Using software PWM."
                    )
                    self._pi = None

            # Configure input pins
            from gpiozero import Button
            self._input_buttons = {}
            for channel, gpio_pin in self.input_pin_map.items():
                try:
                    self._input_buttons[channel] = Button(
                        gpio_pin,
                        pull_up=self.pull_up,
                        bounce_time=0.05  # 50ms debounce
                    )
                    logger.debug("gpio_input_configured", channel=channel, gpio=gpio_pin)
                except Exception as e:
                    logger.warning(
                        "gpio_input_config_failed",
                        channel=channel,
                        gpio=gpio_pin,
                        error=str(e)
                    )

            # Configure PWM outputs
            self._pwm_outputs_hw = {}
            for pwm_channel, gpio_pin in self.pwm_pin_map.items():
                if self._pi:
                    # Use pigpio for hardware PWM
                    self._pi.set_mode(gpio_pin, pigpio.OUTPUT)
                    self._pi.set_PWM_frequency(gpio_pin, 1000)  # 1kHz PWM
                    self._pi.set_PWM_dutycycle(gpio_pin, 0)
                    self._pwm_outputs_hw[pwm_channel] = gpio_pin
                    logger.debug("gpio_pwm_configured_pigpio", channel=pwm_channel, gpio=gpio_pin)
                else:
                    # Fallback to gpiozero software PWM
                    from gpiozero import PWMLED
                    try:
                        self._pwm_outputs_hw[pwm_channel] = PWMLED(gpio_pin)
                        logger.debug("gpio_pwm_configured_software", channel=pwm_channel, gpio=gpio_pin)
                    except Exception as e:
                        logger.warning(
                            "gpio_pwm_config_failed",
                            channel=pwm_channel,
                            gpio=gpio_pin,
                            error=str(e)
                        )

            self._connected = True
            logger.info(
                "gpio_connected",
                inputs=len(self._input_buttons),
                pwm_outputs=len(self._pwm_outputs_hw),
                hardware_pwm=self._pi is not None
            )
            return True

        except Exception as e:
            logger.error("gpio_connection_failed", error=str(e), exc_info=True)
            self.error_count += 1
            return False

    async def disconnect(self) -> None:
        """Disconnect from GPIO and clean up"""
        try:
            # Clean up input buttons
            if hasattr(self, '_input_buttons'):
                for button in self._input_buttons.values():
                    button.close()
                self._input_buttons = {}

            # Clean up PWM outputs
            if hasattr(self, '_pwm_outputs_hw'):
                if self._pi:
                    for gpio_pin in self._pwm_outputs_hw.values():
                        self._pi.set_PWM_dutycycle(gpio_pin, 0)
                else:
                    for pwm in self._pwm_outputs_hw.values():
                        if hasattr(pwm, 'close'):
                            pwm.close()
                self._pwm_outputs_hw = {}

            # Disconnect pigpio
            if self._pi:
                self._pi.stop()
                self._pi = None

            self._connected = False
            logger.info("gpio_disconnected")

        except Exception as e:
            logger.error("gpio_disconnect_error", error=str(e))

    def is_connected(self) -> bool:
        """Check if GPIO is connected"""
        return self._connected

    async def health_check(self) -> bool:
        """Perform health check on GPIO"""
        if not self._connected:
            return False

        # Check if pigpio is still connected (if being used)
        if self._pi and not self._pi.connected:
            logger.warning("pigpio_disconnected")
            return False

        return True

    async def read_analog_input(self, channel: int) -> float:
        """
        Read analog input voltage

        On Raspberry Pi without ADC, this returns the digital state
        as a voltage (3.3V for HIGH, 0V for LOW).

        With an ADC (MCP3008/MCP3208), actual analog readings are returned.

        Args:
            channel: Input channel (0-15)

        Returns:
            Voltage reading (0.0 to 3.3V)
        """
        if not self._connected:
            return 0.0

        try:
            # If ADC is available, use it
            if self._adc is not None:
                # Read from ADC (implementation depends on specific ADC chip)
                voltage = self.analog_inputs.get(channel, 0.0)
            else:
                # Fall back to digital read, convert to voltage
                if channel in self._input_buttons:
                    is_pressed = self._input_buttons[channel].is_pressed
                    # With pull-up, pressed = LOW, not pressed = HIGH
                    if self.pull_up:
                        voltage = 0.0 if is_pressed else 3.3
                    else:
                        voltage = 3.3 if is_pressed else 0.0
                else:
                    voltage = 0.0

            self.analog_inputs[channel] = voltage
            self.read_count += 1
            return voltage

        except Exception as e:
            logger.error("gpio_analog_read_error", channel=channel, error=str(e))
            self.error_count += 1
            return 0.0

    async def read_analog_inputs(self, channels: List[int]) -> Dict[int, float]:
        """Read multiple analog inputs"""
        readings = {}
        for channel in channels:
            readings[channel] = await self.read_analog_input(channel)
        return readings

    async def set_pwm_output(self, channel: int, duty_cycle: float) -> None:
        """
        Set PWM output duty cycle

        Args:
            channel: PWM channel (0-1)
            duty_cycle: Duty cycle (0.0 to 1.0)
        """
        if not self._connected:
            return

        try:
            if channel not in self._pwm_outputs_hw:
                logger.warning("gpio_pwm_channel_not_configured", channel=channel)
                return

            duty_cycle = max(0.0, min(1.0, duty_cycle))

            if self._pi:
                # pigpio uses 0-255 for duty cycle
                gpio_pin = self._pwm_outputs_hw[channel]
                self._pi.set_PWM_dutycycle(gpio_pin, int(duty_cycle * 255))
            else:
                # gpiozero PWMLED uses 0.0-1.0
                pwm_led = self._pwm_outputs_hw[channel]
                pwm_led.value = duty_cycle

            self.pwm_outputs[channel] = duty_cycle
            self.write_count += 1

            logger.debug(
                "gpio_pwm_set",
                channel=channel,
                duty_cycle=duty_cycle,
            )

        except Exception as e:
            logger.error(
                "gpio_pwm_error",
                channel=channel,
                duty_cycle=duty_cycle,
                error=str(e)
            )
            self.error_count += 1

    async def set_pwm_outputs(self, outputs: Dict[int, float]) -> None:
        """Set multiple PWM outputs"""
        for channel, duty_cycle in outputs.items():
            await self.set_pwm_output(channel, duty_cycle)

    async def read_digital_input(self, channel: int) -> bool:
        """
        Read digital input state

        Args:
            channel: Channel number (0-15)

        Returns:
            True for HIGH, False for LOW
        """
        if not self._connected:
            return False

        try:
            if channel not in self._input_buttons:
                logger.warning("gpio_input_channel_not_configured", channel=channel)
                return False

            is_pressed = self._input_buttons[channel].is_pressed

            # With pull-up resistors, pressed = LOW (connected to ground)
            if self.pull_up:
                state = not is_pressed
            else:
                state = is_pressed

            self.digital_inputs[channel] = state
            self.read_count += 1

            logger.debug(
                "gpio_digital_read",
                channel=channel,
                state="HIGH" if state else "LOW"
            )

            return state

        except Exception as e:
            logger.error(
                "gpio_digital_read_error",
                channel=channel,
                error=str(e)
            )
            self.error_count += 1
            return False

    async def write_digital_output(self, channel: int, state: bool) -> None:
        """
        Write digital output state

        Note: On Pi, digital outputs use separate pins from inputs.
        This implementation uses the PWM pins for digital output when needed.

        Args:
            channel: Channel number
            state: True for HIGH, False for LOW
        """
        if not self._connected:
            return

        try:
            # Use PWM output as digital (0% or 100%)
            if channel in self._pwm_outputs_hw:
                await self.set_pwm_output(channel, 1.0 if state else 0.0)
                self.digital_outputs[channel] = state
                logger.debug(
                    "gpio_digital_write",
                    channel=channel,
                    state="HIGH" if state else "LOW"
                )
            else:
                logger.warning("gpio_output_channel_not_configured", channel=channel)

        except Exception as e:
            logger.error(
                "gpio_digital_write_error",
                channel=channel,
                state=state,
                error=str(e)
            )
            self.error_count += 1

    async def configure_channel(self, channel: int, mode: str) -> None:
        """
        Configure channel mode

        Note: On Raspberry Pi, pins are typically fixed as either
        input or output based on the initial configuration.

        Args:
            channel: Channel number
            mode: 'analog', 'digital-in', or 'digital-out'
        """
        if mode not in ('analog', 'digital-in', 'digital-out'):
            raise ValueError(f"Invalid mode: {mode}")

        self.channel_modes[channel] = mode
        logger.debug(
            "gpio_channel_configured",
            channel=channel,
            mode=mode
        )

    def get_statistics(self) -> Dict[str, Any]:
        """Get driver statistics"""
        return {
            "connected": self._connected,
            "driver_type": "Raspberry Pi GPIO",
            "hardware_pwm": self._pi is not None,
            "input_pins": self.input_pin_map,
            "pwm_pins": self.pwm_pin_map,
            "read_count": self.read_count,
            "write_count": self.write_count,
            "error_count": self.error_count,
            "analog_inputs": dict(self.analog_inputs),
            "digital_inputs": dict(self.digital_inputs),
            "digital_outputs": dict(self.digital_outputs),
            "channel_modes": dict(self.channel_modes),
            "pwm_outputs": dict(self.pwm_outputs),
        }

    def is_mock(self) -> bool:
        """Check if this is a mock driver"""
        return False
