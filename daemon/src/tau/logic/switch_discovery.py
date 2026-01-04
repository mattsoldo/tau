"""
Switch Auto-Discovery Service

Monitors LabJack pins for activity on unconfigured pins and notifies
when new switches are detected.
"""
from typing import Dict, Set, Optional
from dataclasses import dataclass
import time
import structlog

from tau.database import get_db_session
from tau.models.switches import Switch
from tau.hardware import HardwareManager

logger = structlog.get_logger(__name__)


@dataclass
class PinActivity:
    """Tracks recent activity on a pin"""
    pin: int
    is_digital: bool
    last_value: float
    first_seen: float
    last_seen: float
    change_count: int


class SwitchDiscovery:
    """
    Auto-discovery service for physical switches

    Monitors all LabJack pins and detects activity on unconfigured pins.
    When a new switch is detected (repeated changes on an unconfigured pin),
    emits notifications via WebSocket.
    """

    def __init__(
        self,
        hardware_manager: HardwareManager,
        change_threshold: int = 3,
        time_window: float = 10.0,
        min_change_magnitude: float = 0.1
    ):
        """
        Initialize switch discovery service

        Args:
            hardware_manager: Reference to hardware for reading inputs
            change_threshold: Number of changes needed to detect a switch
            time_window: Time window in seconds for detecting patterns
            min_change_magnitude: Minimum change in analog value to count as activity
        """
        self.hardware_manager = hardware_manager
        self.change_threshold = change_threshold
        self.time_window = time_window
        self.min_change_magnitude = min_change_magnitude

        # Track configured pins
        self.configured_digital_pins: Set[int] = set()
        self.configured_analog_pins: Set[int] = set()

        # Track activity on unconfigured pins
        self.pin_activity: Dict[int, PinActivity] = {}

        # Recently detected switches (to avoid duplicate notifications)
        self.recently_detected: Dict[int, float] = {}
        self.detection_cooldown = 30.0  # Don't notify about same pin for 30s

        # Statistics
        self.switches_detected = 0
        self.last_scan_time = 0.0

        logger.info("switch_discovery_initialized",
                   change_threshold=change_threshold,
                   time_window=time_window)

    async def load_configured_switches(self) -> None:
        """Load list of already-configured switch pins from database"""
        try:
            async with get_db_session() as session:
                from sqlalchemy import select

                query = select(Switch)
                result = await session.execute(query)
                switches = result.scalars().all()

                self.configured_digital_pins.clear()
                self.configured_analog_pins.clear()

                for switch in switches:
                    if switch.labjack_digital_pin is not None:
                        self.configured_digital_pins.add(switch.labjack_digital_pin)
                    if switch.labjack_analog_pin is not None:
                        self.configured_analog_pins.add(switch.labjack_analog_pin)

                logger.info("configured_switches_loaded",
                           digital_pins=len(self.configured_digital_pins),
                           analog_pins=len(self.configured_analog_pins))

        except Exception as e:
            logger.error("load_configured_switches_failed", error=str(e))

    async def scan_for_activity(self) -> Optional[Dict]:
        """
        Scan all pins for activity and detect new switches

        Returns:
            Dictionary with detected switch info if found, None otherwise
        """
        current_time = time.time()
        self.last_scan_time = current_time

        # Get current pin states from hardware manager
        stats = self.hardware_manager.get_statistics()
        labjack_stats = stats.get("labjack", {})

        if not labjack_stats.get("connected"):
            return None

        digital_inputs = labjack_stats.get("digital_inputs", {})
        analog_inputs = labjack_stats.get("analog_inputs", {})

        # Scan digital pins (0-15)
        for pin in range(16):
            if pin in self.configured_digital_pins:
                continue  # Skip configured pins

            if pin in digital_inputs:
                value = 1.0 if digital_inputs[pin] else 0.0
                detected = await self._check_pin_activity(
                    pin, value, True, current_time
                )
                if detected:
                    return detected

        # Scan analog pins (0-15)
        for pin in range(16):
            if pin in self.configured_analog_pins:
                continue  # Skip configured pins

            if pin in analog_inputs:
                value = analog_inputs[pin]
                detected = await self._check_pin_activity(
                    pin, value, False, current_time
                )
                if detected:
                    return detected

        # Clean up old activity records
        self._cleanup_old_activity(current_time)

        return None

    async def _check_pin_activity(
        self,
        pin: int,
        value: float,
        is_digital: bool,
        current_time: float
    ) -> Optional[Dict]:
        """
        Check if a pin shows activity indicating a new switch

        Returns:
            Detection info if switch detected, None otherwise
        """
        pin_key = pin if is_digital else -(pin + 1)  # Negative for analog

        # Check if we recently detected this pin (cooldown)
        if pin_key in self.recently_detected:
            if current_time - self.recently_detected[pin_key] < self.detection_cooldown:
                return None

        # Get or create activity tracking for this pin
        if pin_key not in self.pin_activity:
            self.pin_activity[pin_key] = PinActivity(
                pin=pin,
                is_digital=is_digital,
                last_value=value,
                first_seen=current_time,
                last_seen=current_time,
                change_count=0
            )
            return None

        activity = self.pin_activity[pin_key]

        # Check for significant change
        changed = False
        if is_digital:
            # Digital: any state change counts
            if abs(value - activity.last_value) > 0.5:
                changed = True
        else:
            # Analog: must exceed minimum change threshold
            if abs(value - activity.last_value) > self.min_change_magnitude:
                changed = True

        if changed:
            activity.change_count += 1
            activity.last_value = value
            activity.last_seen = current_time

            # Check if we've met detection criteria
            time_span = current_time - activity.first_seen
            if (activity.change_count >= self.change_threshold and
                time_span <= self.time_window):

                # New switch detected!
                self.switches_detected += 1
                self.recently_detected[pin_key] = current_time

                logger.info("new_switch_detected",
                           pin=pin,
                           is_digital=is_digital,
                           change_count=activity.change_count,
                           time_span=time_span)

                return {
                    "pin": pin,
                    "is_digital": is_digital,
                    "change_count": activity.change_count,
                    "time_span": time_span,
                    "current_value": value
                }

        return None

    def _cleanup_old_activity(self, current_time: float) -> None:
        """Remove activity records older than time window"""
        to_remove = []
        for pin_key, activity in self.pin_activity.items():
            if current_time - activity.last_seen > self.time_window:
                to_remove.append(pin_key)

        for pin_key in to_remove:
            del self.pin_activity[pin_key]

    def clear_detection(self, pin: int, is_digital: bool) -> None:
        """
        Clear a detection after user acknowledges it

        Args:
            pin: Pin number
            is_digital: True for digital pin, False for analog
        """
        pin_key = pin if is_digital else -(pin + 1)
        if pin_key in self.recently_detected:
            del self.recently_detected[pin_key]
        if pin_key in self.pin_activity:
            del self.pin_activity[pin_key]

    def get_statistics(self) -> Dict:
        """Get discovery statistics"""
        return {
            "switches_detected": self.switches_detected,
            "configured_digital_pins": len(self.configured_digital_pins),
            "configured_analog_pins": len(self.configured_analog_pins),
            "active_pins_monitored": len(self.pin_activity),
            "last_scan_time": self.last_scan_time
        }
