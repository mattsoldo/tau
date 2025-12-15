"""
Hardware Manager - Coordinates LabJack and OLA drivers

Manages hardware initialization, health monitoring, and provides
a unified interface for the control loop to interact with hardware.
"""
import asyncio
from typing import Dict, Optional
import structlog

from tau.hardware.base import LabJackInterface, OLAInterface
from tau.hardware.labjack_mock import LabJackMock
from tau.hardware.ola_mock import OLAMock

logger = structlog.get_logger(__name__)


class HardwareManager:
    """
    Central hardware manager

    Coordinates LabJack and OLA drivers, handles initialization,
    health monitoring, and provides unified hardware interface.
    """

    def __init__(
        self,
        labjack_driver: Optional[LabJackInterface] = None,
        ola_driver: Optional[OLAInterface] = None,
        labjack_mock: bool = True,
        ola_mock: bool = True,
        use_mock: Optional[bool] = None,  # Deprecated, kept for backward compatibility
    ):
        """
        Initialize hardware manager

        Args:
            labjack_driver: LabJack driver instance (or None to create default)
            ola_driver: OLA driver instance (or None to create default)
            labjack_mock: If True, use mock LabJack driver
            ola_mock: If True, use mock OLA driver
            use_mock: Deprecated - use labjack_mock and ola_mock instead
        """
        # Handle deprecated use_mock parameter
        if use_mock is not None:
            labjack_mock = use_mock
            ola_mock = use_mock

        self.use_mock = labjack_mock  # Keep for backward compatibility

        # Create drivers if not provided
        if labjack_driver is None:
            if labjack_mock:
                self.labjack = LabJackMock()
            else:
                # Import real driver only if needed
                from tau.hardware.labjack_driver import LabJackDriver

                self.labjack = LabJackDriver()
        else:
            self.labjack = labjack_driver

        if ola_driver is None:
            if ola_mock:
                self.ola = OLAMock()
            else:
                # Import real driver only if needed
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
            labjack_mock=labjack_mock,
            ola_mock=ola_mock,
            labjack=self.labjack.name,
            ola=self.ola.name,
        )

    async def initialize(self) -> bool:
        """
        Initialize all hardware

        Returns:
            True if all hardware initialized successfully
        """
        logger.info("hardware_initializing")

        try:
            # Connect to LabJack
            labjack_ok = await self.labjack.connect()
            if not labjack_ok:
                logger.error("labjack_connection_failed")
                return False

            # Connect to OLA
            ola_ok = await self.ola.connect()
            if not ola_ok:
                logger.error("ola_connection_failed")
                await self.labjack.disconnect()
                return False

            # Start health monitoring
            self.health_check_task = asyncio.create_task(self._health_check_loop())

            logger.info("hardware_initialized")
            return True

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
        """Background task for periodic health checks"""
        logger.info("health_check_loop_started", interval_s=self.health_check_interval)

        try:
            while True:
                await asyncio.sleep(self.health_check_interval)

                # Check LabJack health
                labjack_ok = await self.labjack.health_check()
                ola_ok = await self.ola.health_check()

                if labjack_ok and ola_ok:
                    self.health_checks_passed += 1
                    logger.debug("health_check_passed")
                else:
                    self.health_checks_failed += 1
                    logger.warning(
                        "health_check_failed",
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
        }
