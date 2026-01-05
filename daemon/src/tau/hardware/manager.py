"""
Hardware Manager - Coordinates LabJack, GPIO, and OLA drivers

Manages hardware initialization, health monitoring, and provides
a unified interface for the control loop to interact with hardware.

Supports:
- LabJack U3 for switch inputs and PWM outputs
- Raspberry Pi GPIO for switch inputs and PWM outputs
- OLA (Open Lighting Architecture) for DMX512 control
"""
import asyncio
from typing import Dict, Optional
import structlog

from tau.hardware.base import LabJackInterface, OLAInterface

logger = structlog.get_logger(__name__)


def parse_pin_mapping(mapping_str: Optional[str]) -> Optional[Dict[int, int]]:
    """
    Parse a pin mapping string into a dictionary

    Args:
        mapping_str: Format "channel:pin,channel:pin" (e.g., "0:17,1:27,2:22")

    Returns:
        Dictionary mapping channel numbers to GPIO pin numbers, or None
    """
    if not mapping_str:
        return None

    result = {}
    for pair in mapping_str.split(','):
        pair = pair.strip()
        if ':' in pair:
            try:
                channel, pin = pair.split(':')
                result[int(channel.strip())] = int(pin.strip())
            except ValueError:
                logger.warning("invalid_pin_mapping", pair=pair)
    return result if result else None


class HardwareManager:
    """
    Central hardware manager

    Coordinates LabJack/GPIO and OLA drivers, handles initialization,
    health monitoring, and provides unified hardware interface.

    On Raspberry Pi, GPIO can be used instead of LabJack for switch
    inputs and PWM outputs.
    """

    def __init__(
        self,
        labjack_driver: Optional[LabJackInterface] = None,
        ola_driver: Optional[OLAInterface] = None,
        # Raspberry Pi GPIO options
        use_gpio: bool = False,
        gpio_use_pigpio: bool = True,
        gpio_pull_up: bool = True,
        gpio_input_pins: Optional[str] = None,
        gpio_pwm_pins: Optional[str] = None,
    ):
        """
        Initialize hardware manager

        Args:
            labjack_driver: LabJack driver instance (or None to create default)
            ola_driver: OLA driver instance (or None to create default)
            use_gpio: If True, use Raspberry Pi GPIO instead of LabJack
            gpio_use_pigpio: Use pigpio for hardware PWM on Raspberry Pi
            gpio_pull_up: Enable internal pull-up resistors on GPIO inputs
            gpio_input_pins: Custom GPIO input pin mapping string
            gpio_pwm_pins: Custom GPIO PWM pin mapping string
        """
        self.use_gpio = use_gpio
        self.gpio_use_pigpio = gpio_use_pigpio
        self.gpio_pull_up = gpio_pull_up
        self.gpio_input_pins_str = gpio_input_pins
        self.gpio_pwm_pins_str = gpio_pwm_pins

        # Create drivers if not provided
        if labjack_driver is None:
            if use_gpio:
                # Use Raspberry Pi GPIO driver
                from tau.hardware.gpio_driver import GPIODriver

                input_pins = parse_pin_mapping(gpio_input_pins)
                pwm_pins = parse_pin_mapping(gpio_pwm_pins)

                self.labjack = GPIODriver(
                    input_pins=input_pins,
                    pwm_pins=pwm_pins,
                    use_pigpio=gpio_use_pigpio,
                    pull_up=gpio_pull_up,
                )
                logger.info(
                    "using_gpio_driver",
                    use_pigpio=gpio_use_pigpio,
                    pull_up=gpio_pull_up,
                )
            else:
                from tau.hardware.labjack_driver import LabJackDriver

                self.labjack = LabJackDriver()
        else:
            self.labjack = labjack_driver

        if ola_driver is None:
            from tau.hardware.ola_driver import OLADriver

            self.ola = OLADriver()
        else:
            self.ola = ola_driver

        # Health monitoring
        self.health_check_interval = 10.0  # seconds
        self.health_check_task: Optional[asyncio.Task] = None

        # Statistics
        self.health_checks_passed = 0
        self.health_checks_failed = 0

        logger.info(
            "hardware_manager_initialized",
            use_gpio=use_gpio,
            labjack=self.labjack.name,
            ola=self.ola.name,
        )

    async def initialize(self) -> bool:
        """
        Initialize all hardware

        Returns:
            True if at least one hardware device initialized successfully, False otherwise
        """
        logger.info("hardware_initializing")

        try:
            # Try to connect to LabJack (non-fatal if it fails)
            labjack_ok = await self.labjack.connect()
            if not labjack_ok:
                logger.warning("labjack_connection_failed", message="LabJack not available - will retry in background")

            # Try to connect to OLA (non-fatal if it fails)
            ola_ok = await self.ola.connect()
            if not ola_ok:
                logger.warning("ola_connection_failed", message="OLA not available - will retry in background")

            # Start health monitoring even if hardware isn't connected yet
            # The health check loop will attempt reconnection
            self.health_check_task = asyncio.create_task(self._health_check_loop())

            if labjack_ok or ola_ok:
                logger.info("hardware_initialized", labjack_ok=labjack_ok, ola_ok=ola_ok)
                return True
            else:
                logger.warning("hardware_initialization_incomplete", message="No hardware available - running in software-only mode")
                return False

        except Exception as e:
            logger.error("hardware_initialization_failed", error=str(e), exc_info=True)
            return False

    async def shutdown(self) -> None:
        """Shutdown all hardware"""
        logger.info("hardware_shutting_down")

        # Stop health monitoring
        if self.health_check_task and not self.health_check_task.done():
            self.health_check_task.cancel()
            try:
                await self.health_check_task
            except asyncio.CancelledError:
                pass

        # Disconnect hardware
        try:
            await self.ola.disconnect()
        except Exception as e:
            logger.error("ola_disconnect_error", error=str(e))

        try:
            await self.labjack.disconnect()
        except Exception as e:
            logger.error("labjack_disconnect_error", error=str(e))

        logger.info("hardware_shutdown_complete")

    async def _health_check_loop(self) -> None:
        """
        Background task for periodic health checks and automatic reconnection

        This loop monitors hardware health and attempts to reconnect to devices
        that become disconnected or are plugged in after startup.
        """
        logger.info("health_check_loop_started", interval_s=self.health_check_interval)

        try:
            while True:
                await asyncio.sleep(self.health_check_interval)

                # Check LabJack health
                labjack_ok = await self.labjack.health_check()

                # If LabJack failed health check, try to reconnect
                if not labjack_ok:
                    logger.info("labjack_unhealthy_attempting_reconnect")
                    reconnect_ok = await self.labjack.connect()
                    if reconnect_ok:
                        logger.info("labjack_reconnected_successfully")
                        labjack_ok = True

                # Check OLA health
                ola_ok = await self.ola.health_check()

                # If OLA failed health check, try to reconnect
                if not ola_ok:
                    logger.info("ola_unhealthy_attempting_reconnect")
                    reconnect_ok = await self.ola.connect()
                    if reconnect_ok:
                        logger.info("ola_reconnected_successfully")
                        ola_ok = True

                if labjack_ok and ola_ok:
                    self.health_checks_passed += 1
                    logger.debug("health_check_passed", labjack_ok=True, ola_ok=True)
                else:
                    self.health_checks_failed += 1
                    logger.debug(
                        "health_check_incomplete",
                        labjack_ok=labjack_ok,
                        ola_ok=ola_ok,
                    )

        except asyncio.CancelledError:
            logger.info("health_check_loop_cancelled")
            raise
        except Exception as e:
            logger.error("health_check_loop_error", error=str(e), exc_info=True)

    # LabJack convenience methods

    async def read_switch_inputs(self, channels: list[int]) -> Dict[int, float]:
        """
        Read switch inputs (analog or digital based on channel mode)

        Args:
            channels: List of LabJack channels to read

        Returns:
            Dictionary mapping channel to voltage (3.3V for digital HIGH, 0.0V for LOW)
        """
        readings = {}

        for channel in channels:
            # Check the channel mode
            if hasattr(self.labjack, 'channel_modes'):
                mode = self.labjack.channel_modes.get(channel, 'analog')

                if mode in ('digital-in', 'digital-out'):
                    # Read as digital and convert to voltage representation
                    state = await self.labjack.read_digital_input(channel)
                    # Represent HIGH as 3.3V, LOW as 0V for compatibility
                    readings[channel] = 3.3 if state else 0.0
                else:
                    # Read as analog
                    readings[channel] = await self.labjack.read_analog_input(channel)
            else:
                # Fallback to analog read if channel_modes not available
                readings[channel] = await self.labjack.read_analog_input(channel)

        return readings

    async def set_led_pwm(self, channel: int, brightness: float) -> None:
        """
        Set LED driver PWM output

        Args:
            channel: PWM channel
            brightness: Brightness (0.0 to 1.0)
        """
        await self.labjack.set_pwm_output(channel, brightness)

    # OLA convenience methods

    async def set_fixture_dmx(
        self, universe: int, start_channel: int, values: list[int]
    ) -> None:
        """
        Set DMX values for a fixture

        Args:
            universe: DMX universe
            start_channel: Starting DMX channel (1-512)
            values: List of DMX values to set
        """
        channels = {start_channel + i: value for i, value in enumerate(values)}
        await self.ola.set_dmx_channels(universe, channels)

    async def set_dmx_output(
        self, universe: int, channels: Dict[int, int]
    ) -> None:
        """
        Set multiple DMX channels

        Args:
            universe: DMX universe
            channels: Dictionary mapping channel to value
        """
        await self.ola.set_dmx_channels(universe, channels)

    # Status and statistics

    def is_healthy(self) -> bool:
        """
        Check if all hardware is healthy

        Returns:
            True if all hardware is connected and healthy
        """
        return self.labjack.is_connected() and self.ola.is_connected()

    def get_statistics(self) -> dict:
        """
        Get hardware statistics

        Returns:
            Dictionary with statistics from all drivers
        """
        return {
            "labjack": self.labjack.get_statistics(),
            "ola": self.ola.get_statistics(),
            "health_checks": {
                "passed": self.health_checks_passed,
                "failed": self.health_checks_failed,
                "interval_s": self.health_check_interval,
            },
            "overall_healthy": self.is_healthy(),
            "mode": {
                "use_gpio": self.use_gpio,
            },
        }
