"""
OLA Real Driver - Open Lighting Architecture interface

This module provides the real OLA driver using the ola Python library.
Requires OLA daemon (olad) running and Python bindings installed.

Installation:
    # On Ubuntu/Debian:
    sudo apt-get install ola ola-python

    # On macOS with Homebrew:
    brew install ola
    pip install ola

Architecture:
    OLA uses a callback-based event loop. To integrate with our async
    architecture, we run OLA's wrapper.Run() in a background thread.
    DMX updates are sent via the client from the main thread, and
    callbacks are processed by the OLA event loop.
"""
import array
import asyncio
import threading
import time
from typing import Dict, Optional
import structlog

from tau.hardware.base import OLAInterface

logger = structlog.get_logger(__name__)


class _Py3CompatArray(array.array):
    """Array subclass that provides tostring() for Python 3.9+ compatibility with old OLA library"""

    def __new__(cls, typecode, initializer=None):
        if initializer is None:
            return super().__new__(cls, typecode)
        return super().__new__(cls, typecode, initializer)

    def tostring(self):
        """Compatibility method - tostring() was renamed to tobytes() in Python 3.2"""
        return self.tobytes()


class OLADriver(OLAInterface):
    """
    Real OLA driver for DMX512 output

    Requires:
    - OLA daemon (olad) running
    - Python OLA bindings installed (pip install ola)
    - DMX hardware configured in OLA (e.g., ENTTEC USB DMX Pro)
    """

    def __init__(self, max_universes: int = 4):
        """
        Initialize real OLA driver

        Args:
            max_universes: Maximum number of universes to support
        """
        super().__init__("OLA")
        self.max_universes = max_universes

        # OLA components (initialized on connect)
        self.wrapper = None
        self.client = None

        # Background thread for OLA event loop
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._connected = False

        # Local DMX state cache (for get operations)
        self._universes: Dict[int, bytearray] = {}
        for universe in range(max_universes):
            self._universes[universe] = bytearray(512)

        # Statistics
        self.channel_set_count = 0
        self.universe_set_count = 0
        self.total_channels_updated = 0
        self.send_errors = 0

        # Thread synchronization
        self._lock = threading.Lock()
        self._connect_event = threading.Event()
        self._connect_result = False

        logger.info("ola_driver_initialized", max_universes=max_universes)

    async def connect(self) -> bool:
        """
        Connect to OLA daemon

        Starts a background thread running the OLA event loop.

        Returns:
            True if connection successful
        """
        if self._connected:
            return True

        try:
            # Import OLA modules
            from ola.ClientWrapper import ClientWrapper

            # Create wrapper and client
            self.wrapper = ClientWrapper()
            self.client = self.wrapper.Client()

            # Start the background thread for OLA event processing
            self._running = True
            self._connect_event.clear()
            self._thread = threading.Thread(target=self._ola_thread_main, daemon=True)
            self._thread.start()

            # Wait for connection result (with timeout)
            connected = await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._connect_event.wait(timeout=5.0)
            )

            if not connected or not self._connect_result:
                logger.error("ola_connection_timeout")
                await self.disconnect()
                return False

            self._connected = True
            logger.info("ola_connected")
            return True

        except ImportError as e:
            logger.error(
                "ola_library_not_installed",
                error=str(e),
                message="OLA Python bindings not installed. Run: pip install ola",
            )
            return False
        except Exception as e:
            logger.error("ola_connection_failed", error=str(e))
            return False

    def _ola_thread_main(self) -> None:
        """Background thread running OLA event loop"""
        try:
            # Test connection by fetching universe list
            def on_universe_info(status, universes):
                if status.Succeeded():
                    self._connect_result = True
                    logger.info(
                        "ola_universes_found",
                        count=len(universes) if universes else 0
                    )
                else:
                    self._connect_result = False
                    logger.error("ola_fetch_universes_failed", message=status.message)
                self._connect_event.set()

            # Fetch universes to verify connection
            self.client.FetchUniverses(on_universe_info)

            # Schedule periodic keepalive/health check
            def schedule_keepalive():
                if self._running and self.wrapper:
                    # Just schedule the next one - the callback itself is the keepalive
                    try:
                        self.wrapper.AddEvent(5000, schedule_keepalive)
                    except TypeError:
                        # Python 3.12 heapq comparison issue - ignore and just run without keepalive
                        pass

            # Try to add keepalive, but don't fail if it doesn't work
            try:
                self.wrapper.AddEvent(5000, schedule_keepalive)
            except TypeError:
                logger.warning("ola_keepalive_disabled", reason="Python 3.12 heapq compatibility")

            # Run the OLA event loop (blocks until Stop() called)
            self.wrapper.Run()

        except Exception as e:
            logger.error("ola_thread_error", error=str(e))
            self._connect_result = False
            self._connect_event.set()
        finally:
            self._running = False
            logger.info("ola_thread_stopped")

    async def disconnect(self) -> None:
        """Disconnect from OLA daemon"""
        self._running = False

        if self.wrapper:
            try:
                self.wrapper.Stop()
            except Exception as e:
                logger.error("ola_stop_error", error=str(e))

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

        self.wrapper = None
        self.client = None
        self._connected = False
        logger.info("ola_disconnected")

    def is_connected(self) -> bool:
        """Check if connected to OLA daemon"""
        return self._connected and self._running

    async def health_check(self) -> bool:
        """Perform health check on OLA daemon"""
        return self.is_connected()

    async def set_dmx_channel(self, universe: int, channel: int, value: int) -> None:
        """
        Set single DMX channel via OLA

        Args:
            universe: DMX universe number (0-based)
            channel: DMX channel (1-512)
            value: Channel value (0-255)
        """
        if not self._connected:
            raise RuntimeError("OLA not connected")

        if universe < 0 or universe >= self.max_universes:
            raise ValueError(f"Invalid universe: {universe}")

        if channel < 1 or channel > 512:
            raise ValueError(f"Invalid channel: {channel}")

        if value < 0 or value > 255:
            raise ValueError(f"Invalid value: {value}")

        # Update local cache
        with self._lock:
            self._universes[universe][channel - 1] = value

        # Send the update via OLA
        self._send_universe(universe)

        self.channel_set_count += 1
        self.total_channels_updated += 1

    async def set_dmx_channels(
        self, universe: int, channels: Dict[int, int]
    ) -> None:
        """
        Set multiple DMX channels via OLA

        Args:
            universe: DMX universe number
            channels: Dictionary mapping channel (1-512) to value (0-255)
        """
        if not self._connected:
            raise RuntimeError("OLA not connected")

        if universe < 0 or universe >= self.max_universes:
            raise ValueError(f"Invalid universe: {universe}")

        # Validate and update local cache
        with self._lock:
            for channel, value in channels.items():
                if channel < 1 or channel > 512:
                    raise ValueError(f"Invalid channel: {channel}")
                if value < 0 or value > 255:
                    raise ValueError(f"Invalid value: {value}")
                self._universes[universe][channel - 1] = value

        # Send the update via OLA
        self._send_universe(universe)

        self.channel_set_count += len(channels)
        self.total_channels_updated += len(channels)

    async def set_dmx_universe(self, universe: int, data: bytes) -> None:
        """
        Set entire DMX universe via OLA

        Args:
            universe: DMX universe number
            data: 512 bytes of DMX data
        """
        if not self._connected:
            raise RuntimeError("OLA not connected")

        if universe < 0 or universe >= self.max_universes:
            raise ValueError(f"Invalid universe: {universe}")

        if len(data) != 512:
            raise ValueError(f"Invalid data length: {len(data)}")

        # Update local cache
        with self._lock:
            self._universes[universe] = bytearray(data)

        # Send the update via OLA
        self._send_universe(universe)

        self.universe_set_count += 1
        self.total_channels_updated += 512

    def _send_universe(self, universe: int) -> None:
        """Send universe data to OLA daemon (thread-safe)"""
        if not self.wrapper or not self.client:
            return

        # Get current universe data as bytes
        with self._lock:
            data_bytes = bytes(self._universes[universe])

        def dmx_sent_callback(status):
            if not status.Succeeded():
                self.send_errors += 1
                logger.error(
                    "dmx_send_failed",
                    universe=universe,
                    message=status.message
                )

        # Use Execute to safely call SendDmx from any thread
        # Execute queues the function to run in the OLA event loop thread
        def do_send():
            try:
                # Create a Python3-compatible array with tostring() for old OLA library
                # OLA uses .tostring() which was deprecated in Python 3.2 and
                # removed in Python 3.13 in favor of .tobytes()
                data = _Py3CompatArray('B', data_bytes)
                self.client.SendDmx(universe, data, dmx_sent_callback)
            except Exception as e:
                self.send_errors += 1
                logger.error("dmx_send_error", universe=universe, error=str(e))

        try:
            self.wrapper._ss.Execute(do_send)
        except Exception as e:
            # If Execute fails, try direct send (less thread-safe but may work)
            logger.warning("ola_execute_failed", error=str(e))
            do_send()


    async def get_dmx_universe(self, universe: int) -> bytes:
        """
        Get current DMX universe data from local cache

        Args:
            universe: DMX universe number

        Returns:
            512 bytes of current DMX data
        """
        if universe < 0 or universe >= self.max_universes:
            raise ValueError(f"Invalid universe: {universe}")

        with self._lock:
            return bytes(self._universes[universe])

    def get_statistics(self) -> dict:
        """Get driver statistics"""
        with self._lock:
            non_zero_channels = sum(
                sum(1 for b in u if b > 0)
                for u in self._universes.values()
            )

        return {
            "connected": self._connected,
            "running": self._running,
            "max_universes": self.max_universes,
            "channel_set_count": self.channel_set_count,
            "universe_set_count": self.universe_set_count,
            "total_channels_updated": self.total_channels_updated,
            "non_zero_channels": non_zero_channels,
            "send_errors": self.send_errors,
        }

    # Helper methods for testing/debugging

    def get_channel(self, universe: int, channel: int) -> int:
        """
        Get current value of a DMX channel from local cache

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

        with self._lock:
            return self._universes[universe][channel - 1]

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

        with self._lock:
            data = self._universes[universe]
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
        return False
