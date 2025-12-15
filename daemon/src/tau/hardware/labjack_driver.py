"""
LabJack Real Driver - LabJack U3 hardware interface

This module provides the real LabJack U3 driver using the LabJackPython library.
Requires physical LabJack hardware and the LabJack Python library installed.

Installation:
    pip install LabJackPython

Docker USB Access:
    The container needs access to USB devices. See docker-compose.production.yml
"""
from typing import Dict, List, Optional, Any
import structlog
import asyncio

from tau.hardware.base import LabJackInterface

logger = structlog.get_logger(__name__)


class LabJackDriver(LabJackInterface):
    """
    Real LabJack U3 driver

    Requires:
    - Physical LabJack U3 hardware (U3-LV or U3-HV)
    - LabJackPython library (pip install LabJackPython)
    - USB device access (privileged mode or device mapping in Docker)
    """

    def __init__(self):
        """Initialize real LabJack driver"""
        super().__init__("LabJack-U3")
        self.device = None
        self.model = "Unknown"
        self.serial_number = None

        # Track analog input values (16 channels)
        self.analog_inputs = {i: 0.0 for i in range(16)}

        # Track digital states (16 channels)
        self.digital_inputs = {i: False for i in range(16)}
        self.digital_outputs = {i: False for i in range(16)}

        # Track channel modes
        self.channel_modes = {i: 'analog' for i in range(16)}

        # Track our intended FIOAnalog bitmask (all analog by default)
        # This is separate from what the hardware reports, as some U3 models
        # may report differently
        self._fio_analog_mask = 0xFF  # All FIO pins as analog

        # Track PWM outputs (2 channels)
        self.pwm_outputs = {0: 0.0, 1: 0.0}

        # Statistics
        self.read_count = 0
        self.write_count = 0
        self.error_count = 0

        logger.info("labjack_driver_initialized")

    async def connect(self) -> bool:
        """
        Connect to real LabJack hardware

        Returns:
            True if connection successful
        """
        try:
            # Import LabJackPython only when connecting (allows mock mode without library)
            import u3

            # Find and connect to first available U3
            self.device = u3.U3()

            # Get device info
            config_info = self.device.configU3()
            self.model = f"U3-{'HV' if config_info['VersionInfo'] & 18 else 'LV'}"
            self.serial_number = str(config_info['SerialNumber'])

            # Configure all FIO pins as analog inputs (FIOAnalog=0xFF means all analog)
            # EIOAnalog=0 means all EIO pins are digital (they cannot be analog on U3)
            self.device.configIO(FIOAnalog=0xFF, EIOAnalog=0x00)

            # Verify the configuration was applied
            verify_config = self.device.configU3()
            logger.debug(
                "labjack_io_configured",
                fio_analog=hex(verify_config.get('FIOAnalog', 0)),
                eio_analog=hex(verify_config.get('EIOAnalog', 0))
            )

            # Configure timers for PWM output
            # Timer0 for PWM channel 0
            # Timer1 for PWM channel 1
            self.device.configTimerClock(TimerClockBase=6, TimerClockDivisor=1)

            self._connected = True
            logger.info(
                "labjack_connected",
                model=self.model,
                serial=self.serial_number
            )
            return True

        except ImportError:
            logger.error(
                "labjack_library_not_installed",
                message="LabJackPython library not installed. Run: pip install LabJackPython"
            )
            return False

        except Exception as e:
            logger.error("labjack_connection_failed", error=str(e))
            self.error_count += 1
            return False

    async def disconnect(self) -> None:
        """Disconnect from real LabJack"""
        if self.device:
            try:
                self.device.close()
                logger.info("labjack_disconnected")
            except Exception as e:
                logger.error("labjack_disconnect_error", error=str(e))
            finally:
                self.device = None
                self._connected = False

    async def read_analog_input(self, channel: int) -> float:
        """
        Read analog input from specified channel

        Args:
            channel: Channel number (0-15)

        Returns:
            Voltage reading
        """
        if not self._connected or not self.device:
            return 0.0

        try:
            # For U3, channels 0-7 are FIO, 8-15 are EIO
            if channel < 8:
                # FIO pins
                voltage = self.device.getAIN(channel)
            else:
                # EIO pins (add 8 to get actual pin number)
                voltage = self.device.getAIN(channel)

            self.analog_inputs[channel] = voltage
            self.read_count += 1
            return voltage

        except Exception as e:
            logger.error(
                "labjack_read_error",
                channel=channel,
                error=str(e)
            )
            self.error_count += 1
            return 0.0

    async def read_analog_inputs(self, channels: List[int]) -> Dict[int, float]:
        """
        Read multiple analog inputs

        Args:
            channels: List of channel numbers

        Returns:
            Dictionary of channel -> voltage
        """
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
        if not self._connected or not self.device:
            return

        try:
            # Configure timer for PWM
            # Using 48MHz base clock with divisor 1
            # Period = 65535 for ~732Hz PWM frequency
            period = 65535
            duty_value = int(duty_cycle * period)

            if channel == 0:
                # Timer0 on FIO4
                self.device.configTimerClock(
                    TimerClockBase=6,
                    TimerClockDivisor=1
                )
                self.device.getFeedback(
                    u3.Timer0Config(
                        TimerMode=0,  # PWM mode
                        Value=duty_value
                    )
                )
            elif channel == 1:
                # Timer1 on FIO5
                self.device.getFeedback(
                    u3.Timer1Config(
                        TimerMode=0,  # PWM mode
                        Value=duty_value
                    )
                )

            self.pwm_outputs[channel] = duty_cycle
            self.write_count += 1

        except Exception as e:
            logger.error(
                "labjack_pwm_error",
                channel=channel,
                duty_cycle=duty_cycle,
                error=str(e)
            )
            self.error_count += 1

    async def set_pwm_outputs(self, outputs: Dict[int, float]) -> None:
        """
        Set multiple PWM outputs

        Args:
            outputs: Dictionary of channel -> duty_cycle
        """
        for channel, duty_cycle in outputs.items():
            await self.set_pwm_output(channel, duty_cycle)

    def get_statistics(self) -> Dict[str, Any]:
        """Get driver statistics"""
        return {
            "connected": self._connected,
            "model": self.model,
            "serial_number": self.serial_number,
            "read_count": self.read_count,
            "write_count": self.write_count,
            "error_count": self.error_count,
            "analog_inputs": self.analog_inputs.copy(),
            "digital_inputs": self.digital_inputs.copy(),
            "digital_outputs": self.digital_outputs.copy(),
            "channel_modes": self.channel_modes.copy(),
            "pwm_outputs": self.pwm_outputs.copy(),
        }

    async def read_digital_input(self, channel: int) -> bool:
        """
        Read digital input state

        Args:
            channel: Channel number (0-15)

        Returns:
            True for HIGH, False for LOW
        """
        if not self._connected or not self.device:
            return False

        try:
            import u3

            # Configure channel as digital input if not already
            if self.channel_modes[channel] != 'digital-in':
                await self.configure_channel(channel, 'digital-in')

            # Read digital state
            if channel < 8:
                # FIO pins (0-7)
                state = self.device.getFIOState(channel)
            else:
                # EIO pins (8-15)
                state = self.device.getEIOState(channel - 8)

            # Update the tracked state
            self.digital_inputs[channel] = bool(state)
            self.read_count += 1

            logger.debug(
                "labjack_digital_read",
                channel=channel,
                state="HIGH" if state else "LOW"
            )

            return bool(state)

        except Exception as e:
            logger.error(
                "labjack_digital_read_error",
                channel=channel,
                error=str(e)
            )
            self.error_count += 1
            return False

    async def write_digital_output(self, channel: int, state: bool) -> None:
        """
        Write digital output state

        Args:
            channel: Channel number (0-15)
            state: True for HIGH, False for LOW
        """
        if not self._connected or not self.device:
            return

        try:
            import u3

            # Configure channel as digital output if not already
            if self.channel_modes[channel] != 'digital-out':
                await self.configure_channel(channel, 'digital-out')

            # Write digital state
            if channel < 8:
                # FIO pins (0-7)
                self.device.setFIOState(channel, int(state))
            else:
                # EIO pins (8-15)
                self.device.setEIOState(channel - 8, int(state))

            self.digital_outputs[channel] = state
            self.write_count += 1

        except Exception as e:
            logger.error(
                "labjack_digital_write_error",
                channel=channel,
                state=state,
                error=str(e)
            )
            self.error_count += 1

    async def configure_channel(self, channel: int, mode: str) -> None:
        """
        Configure channel as analog input, digital input, or digital output

        Args:
            channel: Channel number (0-15)
            mode: 'analog', 'digital-in', or 'digital-out'
        """
        if not self._connected or not self.device:
            return

        try:
            import u3

            if channel < 8:
                # FIO pins (0-7)
                # Use our tracked mask instead of reading from hardware
                # (U3-HV may report different values than what we set)
                current_fio_analog = self._fio_analog_mask

                if mode == 'analog':
                    # Set this channel as analog (set bit to 1)
                    new_fio_analog = current_fio_analog | (1 << channel)
                else:
                    # Set this channel as digital (clear bit to 0)
                    new_fio_analog = current_fio_analog & ~(1 << channel)

                # Apply configuration
                self.device.configIO(FIOAnalog=new_fio_analog)

                # Update our tracked mask
                self._fio_analog_mask = new_fio_analog

                logger.debug(
                    "labjack_fio_config",
                    channel=channel,
                    mode=mode,
                    old_fio_analog=hex(current_fio_analog),
                    new_fio_analog=hex(new_fio_analog)
                )

                if mode in ('digital-in', 'digital-out'):
                    # Configure direction: 0=input, 1=output
                    direction = 1 if mode == 'digital-out' else 0
                    self.device.getFeedback(u3.BitDirWrite(channel, direction))
            else:
                # EIO pins (8-15) are digital only
                # Configure direction: 0=input, 1=output
                direction = 1 if mode == 'digital-out' else 0
                self.device.getFeedback(u3.BitDirWrite(channel, direction))

            self.channel_modes[channel] = mode
            logger.info(
                "labjack_channel_configured",
                channel=channel,
                mode=mode
            )

        except Exception as e:
            logger.error(
                "labjack_configure_error",
                channel=channel,
                mode=mode,
                error=str(e)
            )
            self.error_count += 1

    def is_mock(self) -> bool:
        """Check if this is a mock driver"""
        return False

    def is_connected(self) -> bool:
        """
        Check if hardware is connected

        Returns:
            True if connected, False otherwise
        """
        return self._connected

    async def health_check(self) -> bool:
        """
        Perform health check on hardware

        Returns:
            True if hardware is healthy, False otherwise
        """
        if not self._connected or not self.device:
            return False

        try:
            # Try to read a configuration value to check if device is responsive
            self.device.configU3()
            return True
        except Exception as e:
            logger.error("labjack_health_check_failed", error=str(e))
            self.error_count += 1
            return False