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
import subprocess
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

            # Verify and auto-patch DMX device to Universe 0 using reliable method
            await self._ensure_dmx_device_patched()

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

    async def _ensure_dmx_device_patched(self) -> bool:
        """
        Ensure DMX output device is patched to Universe 0.

        Uses ola_dev_info and ola_patch commands for reliable patching.
        This handles cases where OLA's Python API patching doesn't work correctly.

        Returns:
            True if patching verified/successful, False otherwise
        """
        try:
            # Get device info to find DMX output device
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["ola_dev_info"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
            )

            if result.returncode != 0:
                logger.warning("ola_dev_info_failed", stderr=result.stderr)
                return False

            # Parse output to find ENTTEC USB DMX Pro (prioritize over other devices)
            # Example line: "Device 10: Enttec Usb Pro Device, Serial #: 02312614, firmware 2.4"
            device_id = None
            fallback_device_id = None
            lines = result.stdout.split('\n')

            for line in lines:
                line_lower = line.lower()
                if line.startswith('Device '):
                    try:
                        current_id = int(line.split(':')[0].replace('Device ', '').strip())
                        # First priority: ENTTEC devices
                        if 'enttec' in line_lower:
                            device_id = current_id
                            logger.info(
                                "ola_enttec_device_detected",
                                device_id=device_id,
                                device_line=line.strip()
                            )
                            break
                        # Fallback: Other USB DMX devices (but not network protocols like E1.31, ArtNet)
                        elif ('dmx' in line_lower and 'usb' in line_lower and
                              'e1.31' not in line_lower and 'artnet' not in line_lower and
                              fallback_device_id is None):
                            fallback_device_id = current_id
                    except (ValueError, IndexError):
                        continue

            # Use fallback if no Enttec found
            if device_id is None and fallback_device_id is not None:
                device_id = fallback_device_id
                logger.info(
                    "ola_fallback_dmx_device_detected",
                    device_id=device_id
                )

            if device_id is None:
                logger.warning("ola_no_dmx_device_found_for_patching")
                return False

            # Check if THIS specific device is already patched to Universe 0
            # We can't easily check this via HTTP API, so we'll just patch it
            # OLA handles re-patching gracefully (no error if already patched)

            # Patch device to Universe 0
            logger.info(
                "ola_patching_device_to_universe_0",
                device_id=device_id,
                port=0
            )

            patch_result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["ola_patch", "--device", str(device_id), "--port", "0", "--universe", "0"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
            )

            if patch_result.returncode == 0:
                logger.info(
                    "ola_device_patched_successfully",
                    device_id=device_id,
                    universe=0
                )
                return True
            else:
                logger.error(
                    "ola_patch_command_failed",
                    device_id=device_id,
                    returncode=patch_result.returncode,
                    stderr=patch_result.stderr
                )
                return False

        except subprocess.TimeoutExpired:
            logger.error("ola_patching_timeout")
            return False
        except FileNotFoundError:
            logger.error("ola_patch_command_not_found")
            return False
        except Exception as e:
            logger.error("ola_patching_error", error=str(e))
            return False

    def _ola_thread_main(self) -> None:
        """Background thread running OLA event loop"""
        try:
            # Test connection and verify universe configuration
            def on_universe_info(status, universes):
                if not status.Succeeded():
                    self._connect_result = False
                    logger.error("ola_fetch_universes_failed", message=status.message)
                    self._connect_event.set()
                    return

                logger.info(
                    "ola_universes_found",
                    count=len(universes) if universes else 0
                )

                # Check if Universe 0 exists
                universe_0_exists = False
                if universes:
                    for universe in universes:
                        if universe.id == 0:
                            universe_0_exists = True
                            logger.info("ola_universe_0_exists", name=universe.name)
                            break

                if not universe_0_exists:
                    logger.warning("ola_universe_0_missing")

                # Now fetch devices to verify patching
                def on_device_info(status, devices):
                    if not status.Succeeded():
                        logger.error("ola_fetch_devices_failed", message=status.message)
                        self._connect_result = True  # Still connected, just couldn't verify devices
                        self._connect_event.set()
                        return

                    if not devices:
                        logger.warning("ola_no_devices_found")
                        self._connect_result = True
                        self._connect_event.set()
                        return

                    # Find ENTTEC USB DMX Pro (prioritize over other DMX devices)
                    enttec_device = None
                    fallback_device = None

                    for device in devices:
                        device_name = device.name.lower()
                        # First priority: ENTTEC devices (USB DMX Pro, Open DMX)
                        if 'enttec' in device_name:
                            enttec_device = device
                            logger.info(
                                "ola_enttec_device_found",
                                device_id=device.id,
                                device_name=device.name,
                                device_alias=device.alias
                            )
                            break
                        # Fallback: Other USB DMX devices (but not network protocols)
                        elif 'dmx' in device_name and 'usb' in device_name and fallback_device is None:
                            fallback_device = device

                    # Use fallback if no Enttec found
                    if enttec_device is None and fallback_device is not None:
                        enttec_device = fallback_device
                        logger.info(
                            "ola_fallback_dmx_device_found",
                            device_id=fallback_device.id,
                            device_name=fallback_device.name,
                            device_alias=fallback_device.alias
                        )

                    if not enttec_device:
                        logger.warning("ola_no_dmx_device_found")
                        self._connect_result = True
                        self._connect_event.set()
                        return

                    # Check if device has output port patched to Universe 0
                    output_port_patched = False
                    output_port_id = None

                    if hasattr(enttec_device, 'output_ports'):
                        for port in enttec_device.output_ports:
                            if port.universe == 0:
                                output_port_patched = True
                                logger.info(
                                    "ola_device_already_patched",
                                    device_id=enttec_device.id,
                                    port_id=port.id,
                                    universe=0
                                )
                                break
                            if output_port_id is None:
                                output_port_id = port.id  # Remember first output port

                    # If not patched, patch the first output port to Universe 0
                    if not output_port_patched and output_port_id is not None:
                        logger.warning(
                            "ola_auto_patching_device",
                            device_id=enttec_device.id,
                            device_alias=enttec_device.alias,
                            port_id=output_port_id,
                            universe=0
                        )

                        def on_patch_complete(status):
                            if status.Succeeded():
                                logger.info(
                                    "ola_device_patched_successfully",
                                    device_id=enttec_device.id,
                                    port_id=output_port_id,
                                    universe=0
                                )
                            else:
                                logger.error(
                                    "ola_device_patch_failed",
                                    device_id=enttec_device.id,
                                    message=status.message
                                )
                            self._connect_result = True
                            self._connect_event.set()

                        # Patch port to Universe 0
                        # PatchPort(device_alias, port_id, is_output, action, universe, callback)
                        # action: 0 = unpatch, 1 = patch
                        self.client.PatchPort(
                            enttec_device.alias,
                            output_port_id,
                            True,  # is_output
                            1,     # action: patch
                            0,     # universe
                            on_patch_complete
                        )
                    else:
                        # Already patched or no output ports
                        self._connect_result = True
                        self._connect_event.set()

                # Fetch devices to check patching
                self.client.FetchDevices(on_device_info)

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
