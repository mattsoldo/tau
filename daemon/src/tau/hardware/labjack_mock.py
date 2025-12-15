"""
LabJack Mock Driver - Simulated LabJack U3 for testing

Provides a simulated LabJack that behaves like real hardware
but runs entirely in software for development and testing.
"""
import asyncio
from typing import Dict, List
import structlog

from tau.hardware.base import LabJackInterface

logger = structlog.get_logger(__name__)


class LabJackMock(LabJackInterface):
    """
    Mock LabJack U3 driver for testing

    Simulates analog inputs and PWM outputs without physical hardware.
    """

    def __init__(self):
        """Initialize mock LabJack"""
        super().__init__("LabJack-Mock")

        # Simulated analog input values (16 channels)
        self.analog_inputs: Dict[int, float] = {i: 0.0 for i in range(16)}

        # Simulated digital input states (16 channels)
        self.digital_inputs: Dict[int, bool] = {i: False for i in range(16)}

        # Simulated digital output states (16 channels)
        self.digital_outputs: Dict[int, bool] = {i: False for i in range(16)}

        # Track channel modes (analog, digital-in, digital-out)
        self.channel_modes: Dict[int, str] = {i: 'analog' for i in range(16)}

        # Simulated PWM output values (2 channels)
        self.pwm_outputs: Dict[int, float] = {0: 0.0, 1: 0.0}

        # Statistics
        self.read_count = 0
        self.write_count = 0
        self.total_read_time = 0.0
        self.total_write_time = 0.0

        logger.info("labjack_mock_initialized")

    async def connect(self) -> bool:
        """
        Simulate connecting to LabJack

        Returns:
            Always True (mock always succeeds)
        """
        await asyncio.sleep(0.001)  # Simulate connection delay
        self.connected = True
        logger.info("labjack_mock_connected")
        return True

    async def disconnect(self) -> None:
        """Simulate disconnecting from LabJack"""
        self.connected = False
        logger.info("labjack_mock_disconnected")

    def is_connected(self) -> bool:
        """
        Check if mock LabJack is connected

        Returns:
            Connection status
        """
        return self.connected

    async def health_check(self) -> bool:
        """
        Simulate health check

        Returns:
            Always True (mock is always healthy)
        """
        return self.connected

    async def read_analog_input(self, channel: int) -> float:
        """
        Read simulated analog input

        Args:
            channel: Analog input channel (0-15)

        Returns:
            Simulated voltage reading
        """
        if not self.connected:
            logger.error("labjack_not_connected", operation="read_analog_input")
            raise RuntimeError("LabJack not connected")

        if channel < 0 or channel > 15:
            raise ValueError(f"Invalid channel: {channel} (must be 0-15)")

        # Simulate read delay
        await asyncio.sleep(0.0001)

        self.read_count += 1
        voltage = self.analog_inputs[channel]

        logger.debug(
            "labjack_analog_read",
            channel=channel,
            voltage=voltage,
        )

        return voltage

    async def read_analog_inputs(self, channels: List[int]) -> Dict[int, float]:
        """
        Read multiple simulated analog inputs

        Args:
            channels: List of channel numbers to read

        Returns:
            Dictionary mapping channel to voltage reading
        """
        if not self.connected:
            logger.error("labjack_not_connected", operation="read_analog_inputs")
            raise RuntimeError("LabJack not connected")

        # Validate channels
        for channel in channels:
            if channel < 0 or channel > 15:
                raise ValueError(f"Invalid channel: {channel} (must be 0-15)")

        # Simulate read delay (slightly faster than individual reads)
        await asyncio.sleep(0.0001 * len(channels) * 0.7)

        result = {channel: self.analog_inputs[channel] for channel in channels}
        self.read_count += len(channels)

        logger.debug(
            "labjack_analog_read_batch",
            channels=channels,
            count=len(channels),
        )

        return result

    async def set_pwm_output(self, channel: int, duty_cycle: float) -> None:
        """
        Set simulated PWM output

        Args:
            channel: PWM channel (0-1)
            duty_cycle: Duty cycle (0.0 to 1.0)
        """
        if not self.connected:
            logger.error("labjack_not_connected", operation="set_pwm_output")
            raise RuntimeError("LabJack not connected")

        if channel < 0 or channel > 1:
            raise ValueError(f"Invalid PWM channel: {channel} (must be 0-1)")

        if duty_cycle < 0.0 or duty_cycle > 1.0:
            raise ValueError(f"Invalid duty cycle: {duty_cycle} (must be 0.0-1.0)")

        # Simulate write delay
        await asyncio.sleep(0.0001)

        self.pwm_outputs[channel] = duty_cycle
        self.write_count += 1

        logger.debug(
            "labjack_pwm_set",
            channel=channel,
            duty_cycle=duty_cycle,
        )

    async def set_pwm_outputs(self, outputs: Dict[int, float]) -> None:
        """
        Set multiple simulated PWM outputs

        Args:
            outputs: Dictionary mapping channel to duty cycle
        """
        if not self.connected:
            logger.error("labjack_not_connected", operation="set_pwm_outputs")
            raise RuntimeError("LabJack not connected")

        # Validate all outputs first
        for channel, duty_cycle in outputs.items():
            if channel < 0 or channel > 1:
                raise ValueError(f"Invalid PWM channel: {channel} (must be 0-1)")
            if duty_cycle < 0.0 or duty_cycle > 1.0:
                raise ValueError(f"Invalid duty cycle: {duty_cycle} (must be 0.0-1.0)")

        # Simulate write delay (slightly faster than individual writes)
        await asyncio.sleep(0.0001 * len(outputs) * 0.7)

        for channel, duty_cycle in outputs.items():
            self.pwm_outputs[channel] = duty_cycle

        self.write_count += len(outputs)

        logger.debug(
            "labjack_pwm_set_batch",
            channels=list(outputs.keys()),
            count=len(outputs),
        )

    async def read_digital_input(self, channel: int) -> bool:
        """
        Read simulated digital input

        Args:
            channel: Digital input channel (0-15)

        Returns:
            True for HIGH, False for LOW
        """
        if not self.connected:
            logger.error("labjack_not_connected", operation="read_digital_input")
            raise RuntimeError("LabJack not connected")

        if channel < 0 or channel > 15:
            raise ValueError(f"Invalid channel: {channel} (must be 0-15)")

        # Auto-configure channel if needed
        if self.channel_modes[channel] == 'analog':
            await self.configure_channel(channel, 'digital-in')

        # Simulate read delay
        await asyncio.sleep(0.0001)

        self.read_count += 1
        state = self.digital_inputs[channel]

        logger.debug(
            "labjack_digital_read",
            channel=channel,
            state="HIGH" if state else "LOW",
        )

        return state

    async def write_digital_output(self, channel: int, state: bool) -> None:
        """
        Write simulated digital output

        Args:
            channel: Digital output channel (0-15)
            state: True for HIGH, False for LOW
        """
        if not self.connected:
            logger.error("labjack_not_connected", operation="write_digital_output")
            raise RuntimeError("LabJack not connected")

        if channel < 0 or channel > 15:
            raise ValueError(f"Invalid channel: {channel} (must be 0-15)")

        # Auto-configure channel if needed
        if self.channel_modes[channel] != 'digital-out':
            await self.configure_channel(channel, 'digital-out')

        # Simulate write delay
        await asyncio.sleep(0.0001)

        self.digital_outputs[channel] = state
        self.write_count += 1

        logger.debug(
            "labjack_digital_write",
            channel=channel,
            state="HIGH" if state else "LOW",
        )

    async def configure_channel(self, channel: int, mode: str) -> None:
        """
        Configure channel as analog or digital I/O

        Args:
            channel: Channel number (0-15)
            mode: 'analog', 'digital-in', or 'digital-out'
        """
        if not self.connected:
            logger.error("labjack_not_connected", operation="configure_channel")
            raise RuntimeError("LabJack not connected")

        if channel < 0 or channel > 15:
            raise ValueError(f"Invalid channel: {channel} (must be 0-15)")

        if mode not in ('analog', 'digital-in', 'digital-out'):
            raise ValueError(f"Invalid mode: {mode}")

        # EIO pins (8-15) cannot be analog in real hardware
        if channel >= 8 and mode == 'analog':
            logger.warning(
                "eio_pins_digital_only",
                channel=channel,
                message="EIO pins (8-15) are digital only, ignoring analog configuration"
            )
            mode = 'digital-in'  # Default to digital input

        self.channel_modes[channel] = mode

        logger.debug(
            "labjack_channel_configured",
            channel=channel,
            mode=mode,
        )

    def get_statistics(self) -> dict:
        """
        Get mock driver statistics

        Returns:
            Dictionary with statistics
        """
        return {
            "connected": self.connected,
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
        return True

    # Helper methods for testing

    def simulate_analog_input(self, channel: int, voltage: float) -> None:
        """
        Simulate an analog input change (for testing)

        Args:
            channel: Channel to simulate
            voltage: Voltage to set
        """
        if channel < 0 or channel > 15:
            raise ValueError(f"Invalid channel: {channel}")
        if voltage < 0.0 or voltage > 2.4:
            logger.warning(
                "voltage_out_of_range",
                channel=channel,
                voltage=voltage,
                valid_range="0.0-2.4V",
            )

        self.analog_inputs[channel] = voltage
        logger.debug("analog_input_simulated", channel=channel, voltage=voltage)

    def simulate_digital_input(self, channel: int, state: bool) -> None:
        """
        Simulate a digital input change (for testing)

        Args:
            channel: Channel to simulate
            state: True for HIGH, False for LOW
        """
        if channel < 0 or channel > 15:
            raise ValueError(f"Invalid channel: {channel}")

        self.digital_inputs[channel] = state
        logger.debug(
            "digital_input_simulated",
            channel=channel,
            state="HIGH" if state else "LOW"
        )
