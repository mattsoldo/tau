"""
OLA Mock Driver - Simulated Open Lighting Architecture for testing

Provides a simulated OLA DMX controller that behaves like real hardware
but runs entirely in software for development and testing.
"""
import asyncio
from typing import Dict
import structlog

from tau.hardware.base import OLAInterface

logger = structlog.get_logger(__name__)


class OLAMock(OLAInterface):
    """
    Mock OLA driver for testing

    Simulates DMX512 universes without physical hardware.
    Each universe has 512 channels (0-255 values).
    """

    def __init__(self, max_universes: int = 4):
        """
        Initialize mock OLA

        Args:
            max_universes: Maximum number of universes to support
        """
        super().__init__("OLA-Mock")

        self.max_universes = max_universes

        # Simulated DMX universes (each is 512 bytes)
        self.universes: Dict[int, bytearray] = {}
        for universe in range(max_universes):
            self.universes[universe] = bytearray(512)

        # Statistics
        self.channel_set_count = 0
        self.universe_set_count = 0
        self.total_channels_updated = 0

        logger.info("ola_mock_initialized", max_universes=max_universes)

    async def connect(self) -> bool:
        """
        Simulate connecting to OLA

        Returns:
            Always True (mock always succeeds)
        """
        await asyncio.sleep(0.001)  # Simulate connection delay
        self.connected = True
        logger.info("ola_mock_connected")
        return True

    async def disconnect(self) -> None:
        """Simulate disconnecting from OLA"""
        self.connected = False
        logger.info("ola_mock_disconnected")

    def is_connected(self) -> bool:
        """
        Check if mock OLA is connected

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

    async def set_dmx_channel(self, universe: int, channel: int, value: int) -> None:
        """
        Set single simulated DMX channel

        Args:
            universe: DMX universe number (0-based)
            channel: DMX channel (1-512)
            value: Channel value (0-255)
        """
        if not self.connected:
            logger.error("ola_not_connected", operation="set_dmx_channel")
            raise RuntimeError("OLA not connected")

        if universe < 0 or universe >= self.max_universes:
            raise ValueError(
                f"Invalid universe: {universe} (must be 0-{self.max_universes-1})"
            )

        if channel < 1 or channel > 512:
            raise ValueError(f"Invalid channel: {channel} (must be 1-512)")

        if value < 0 or value > 255:
            raise ValueError(f"Invalid value: {value} (must be 0-255)")

        # Simulate write delay
        await asyncio.sleep(0.00001)

        # DMX channels are 1-indexed, but arrays are 0-indexed
        self.universes[universe][channel - 1] = value
        self.channel_set_count += 1
        self.total_channels_updated += 1

        logger.debug(
            "dmx_channel_set",
            universe=universe,
            channel=channel,
            value=value,
        )

    async def set_dmx_channels(
        self, universe: int, channels: Dict[int, int]
    ) -> None:
        """
        Set multiple simulated DMX channels

        Args:
            universe: DMX universe number
            channels: Dictionary mapping channel (1-512) to value (0-255)
        """
        if not self.connected:
            logger.error("ola_not_connected", operation="set_dmx_channels")
            raise RuntimeError("OLA not connected")

        if universe < 0 or universe >= self.max_universes:
            raise ValueError(
                f"Invalid universe: {universe} (must be 0-{self.max_universes-1})"
            )

        # Validate all channels first
        for channel, value in channels.items():
            if channel < 1 or channel > 512:
                raise ValueError(f"Invalid channel: {channel} (must be 1-512)")
            if value < 0 or value > 255:
                raise ValueError(f"Invalid value: {value} (must be 0-255)")

        # Simulate write delay (slightly faster than individual writes)
        await asyncio.sleep(0.00001 * len(channels) * 0.5)

        # Update all channels
        for channel, value in channels.items():
            self.universes[universe][channel - 1] = value

        self.channel_set_count += len(channels)
        self.total_channels_updated += len(channels)

        logger.debug(
            "dmx_channels_set_batch",
            universe=universe,
            count=len(channels),
        )

    async def set_dmx_universe(self, universe: int, data: bytes) -> None:
        """
        Set entire simulated DMX universe

        Args:
            universe: DMX universe number
            data: 512 bytes of DMX data
        """
        if not self.connected:
            logger.error("ola_not_connected", operation="set_dmx_universe")
            raise RuntimeError("OLA not connected")

        if universe < 0 or universe >= self.max_universes:
            raise ValueError(
                f"Invalid universe: {universe} (must be 0-{self.max_universes-1})"
            )

        if len(data) != 512:
            raise ValueError(f"Invalid data length: {len(data)} (must be 512 bytes)")

        # Simulate write delay for full universe
        await asyncio.sleep(0.0001)

        # Update entire universe
        self.universes[universe] = bytearray(data)
        self.universe_set_count += 1
        self.total_channels_updated += 512

        logger.debug(
            "dmx_universe_set",
            universe=universe,
            non_zero_channels=sum(1 for b in data if b > 0),
        )

    async def get_dmx_universe(self, universe: int) -> bytes:
        """
        Get current simulated DMX universe data

        Args:
            universe: DMX universe number

        Returns:
            512 bytes of current DMX data
        """
        if not self.connected:
            logger.error("ola_not_connected", operation="get_dmx_universe")
            raise RuntimeError("OLA not connected")

        if universe < 0 or universe >= self.max_universes:
            raise ValueError(
                f"Invalid universe: {universe} (must be 0-{self.max_universes-1})"
            )

        # Simulate read delay
        await asyncio.sleep(0.00005)

        return bytes(self.universes[universe])

    def get_statistics(self) -> dict:
        """
        Get mock driver statistics

        Returns:
            Dictionary with statistics
        """
        # Calculate non-zero channels across all universes
        non_zero_channels = 0
        for universe_data in self.universes.values():
            non_zero_channels += sum(1 for b in universe_data if b > 0)

        return {
            "connected": self.connected,
            "max_universes": self.max_universes,
            "channel_set_count": self.channel_set_count,
            "universe_set_count": self.universe_set_count,
            "total_channels_updated": self.total_channels_updated,
            "non_zero_channels": non_zero_channels,
            "error_count": self.error_count,
        }

    # Helper methods for testing

    def get_channel(self, universe: int, channel: int) -> int:
        """
        Get current value of a DMX channel (for testing)

        Args:
            universe: Universe number
            channel: Channel number (1-512)

        Returns:
            Channel value (0-255)
        """
        if universe < 0 or universe >= self.max_universes:
            raise ValueError(f"Invalid universe: {universe}")
        if channel < 1 or channel > 512:
            raise ValueError(f"Invalid channel: {channel}")

        return self.universes[universe][channel - 1]

    def get_universe_summary(self, universe: int) -> dict:
        """
        Get summary of universe state (for testing/debugging)

        Args:
            universe: Universe number

        Returns:
            Dictionary with universe statistics
        """
        if universe < 0 or universe >= self.max_universes:
            raise ValueError(f"Invalid universe: {universe}")

        data = self.universes[universe]
        non_zero = [(i + 1, data[i]) for i in range(512) if data[i] > 0]

        return {
            "universe": universe,
            "total_channels": 512,
            "non_zero_channels": len(non_zero),
            "non_zero_values": non_zero[:20],  # First 20 non-zero channels
            "max_value": max(data) if any(data) else 0,
        }

    def is_mock(self) -> bool:
        """Check if this is a mock driver"""
        return True
