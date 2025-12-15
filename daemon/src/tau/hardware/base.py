"""
Hardware Base Classes - Abstract interfaces for hardware drivers

Defines the interface that all hardware drivers must implement,
allowing for easy swapping between mock and real implementations.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
import structlog

logger = structlog.get_logger(__name__)


class HardwareDriver(ABC):
    """Base class for all hardware drivers"""

    def __init__(self, name: str):
        """
        Initialize hardware driver

        Args:
            name: Human-readable driver name
        """
        self.name = name
        self.connected = False
        self.error_count = 0

    @abstractmethod
    async def connect(self) -> bool:
        """
        Connect to hardware

        Returns:
            True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from hardware"""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if hardware is connected

        Returns:
            True if connected, False otherwise
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Perform health check on hardware

        Returns:
            True if hardware is healthy, False otherwise
        """
        pass


class LabJackInterface(HardwareDriver):
    """
    Abstract interface for LabJack U3 operations

    The LabJack U3 provides:
    - 16 flexible I/O lines (analog/digital)
    - 2 analog inputs (0-2.4V or -10 to +10V)
    - 2 PWM outputs (for LED drivers)
    - USB interface
    """

    @abstractmethod
    async def read_analog_input(self, channel: int) -> float:
        """
        Read analog input voltage

        Args:
            channel: Analog input channel (0-15)

        Returns:
            Voltage reading (0.0 to 2.4V)
        """
        pass

    @abstractmethod
    async def read_analog_inputs(self, channels: List[int]) -> Dict[int, float]:
        """
        Read multiple analog inputs in one operation

        Args:
            channels: List of channel numbers to read

        Returns:
            Dictionary mapping channel to voltage reading
        """
        pass

    @abstractmethod
    async def set_pwm_output(self, channel: int, duty_cycle: float) -> None:
        """
        Set PWM output duty cycle

        Args:
            channel: PWM channel (0-1)
            duty_cycle: Duty cycle (0.0 to 1.0)
        """
        pass

    @abstractmethod
    async def set_pwm_outputs(self, outputs: Dict[int, float]) -> None:
        """
        Set multiple PWM outputs in one operation

        Args:
            outputs: Dictionary mapping channel to duty cycle
        """
        pass

    @abstractmethod
    async def read_digital_input(self, channel: int) -> bool:
        """
        Read digital input state

        Args:
            channel: Channel number (0-15)

        Returns:
            True for HIGH, False for LOW
        """
        pass

    @abstractmethod
    async def write_digital_output(self, channel: int, state: bool) -> None:
        """
        Write digital output state

        Args:
            channel: Channel number (0-15)
            state: True for HIGH, False for LOW
        """
        pass

    @abstractmethod
    async def configure_channel(self, channel: int, mode: str) -> None:
        """
        Configure channel as analog input, digital input, or digital output

        Args:
            channel: Channel number (0-15)
            mode: 'analog', 'digital-in', or 'digital-out'
        """
        pass

    @abstractmethod
    def get_statistics(self) -> dict:
        """
        Get driver statistics

        Returns:
            Dictionary with driver statistics
        """
        pass


class OLAInterface(HardwareDriver):
    """
    Abstract interface for OLA (Open Lighting Architecture) operations

    OLA provides:
    - DMX512 universe control (512 channels per universe)
    - Multiple universe support
    - USB DMX interfaces (e.g., ENTTEC, DMXKing)
    """

    @abstractmethod
    async def set_dmx_channel(self, universe: int, channel: int, value: int) -> None:
        """
        Set single DMX channel value

        Args:
            universe: DMX universe number (0-based)
            channel: DMX channel (1-512)
            value: Channel value (0-255)
        """
        pass

    @abstractmethod
    async def set_dmx_channels(
        self, universe: int, channels: Dict[int, int]
    ) -> None:
        """
        Set multiple DMX channels in one operation

        Args:
            universe: DMX universe number
            channels: Dictionary mapping channel to value
        """
        pass

    @abstractmethod
    async def set_dmx_universe(self, universe: int, data: bytes) -> None:
        """
        Set entire DMX universe at once

        Args:
            universe: DMX universe number
            data: 512 bytes of DMX data
        """
        pass

    @abstractmethod
    async def get_dmx_universe(self, universe: int) -> bytes:
        """
        Get current DMX universe data

        Args:
            universe: DMX universe number

        Returns:
            512 bytes of current DMX data
        """
        pass

    @abstractmethod
    def get_statistics(self) -> dict:
        """
        Get driver statistics

        Returns:
            Dictionary with driver statistics
        """
        pass
