"""
Raspberry Pi Platform Detection

Detects if the system is running on a Raspberry Pi and identifies the model.
Only Pi 4 and Pi 5 series are supported for GPIO input.
"""
import os
import re
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass
from functools import lru_cache
import structlog

logger = structlog.get_logger(__name__)


@dataclass
class PlatformInfo:
    """Information about the running platform"""
    is_raspberry_pi: bool
    model: Optional[str]  # e.g., "Raspberry Pi 5 Model B"
    model_number: Optional[int]  # 4 or 5
    gpio_available: bool
    reason: Optional[str] = None  # Why GPIO is unavailable if not


# GPIO pins available for switch input (BCM numbering)
# Excludes: I2C (0,1,2,3), SPI (7,8,9,10,11), UART (14,15)
AVAILABLE_GPIO_PINS = [4, 5, 6, 12, 13, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27]

# Disabled pins with reasons
DISABLED_GPIO_PINS = {
    0: "I2C ID EEPROM (reserved for HAT detection)",
    1: "I2C ID EEPROM (reserved for HAT detection)",
    2: "I2C1 SDA (common peripheral bus)",
    3: "I2C1 SCL (common peripheral bus)",
    7: "SPI0 CE1",
    8: "SPI0 CE0",
    9: "SPI0 MISO",
    10: "SPI0 MOSI",
    11: "SPI0 SCLK",
    14: "UART TX (serial console)",
    15: "UART RX (serial console)",
}

# Physical pin to BCM mapping for 40-pin header
# Format: physical_pin -> (bcm_number or None, label, type)
# type: 'gpio', 'power', 'ground', 'disabled'
GPIO_HEADER_LAYOUT: Dict[int, Tuple[Optional[int], str, str]] = {
    # Left column (odd pins)
    1: (None, "3.3V", "power"),
    3: (2, "GPIO2 (SDA)", "disabled"),
    5: (3, "GPIO3 (SCL)", "disabled"),
    7: (4, "GPIO4", "gpio"),
    9: (None, "GND", "ground"),
    11: (17, "GPIO17", "gpio"),
    13: (27, "GPIO27", "gpio"),
    15: (22, "GPIO22", "gpio"),
    17: (None, "3.3V", "power"),
    19: (10, "GPIO10 (MOSI)", "disabled"),
    21: (9, "GPIO9 (MISO)", "disabled"),
    23: (11, "GPIO11 (SCLK)", "disabled"),
    25: (None, "GND", "ground"),
    27: (0, "GPIO0 (ID_SD)", "disabled"),
    29: (5, "GPIO5", "gpio"),
    31: (6, "GPIO6", "gpio"),
    33: (13, "GPIO13", "gpio"),
    35: (19, "GPIO19", "gpio"),
    37: (26, "GPIO26", "gpio"),
    39: (None, "GND", "ground"),
    # Right column (even pins)
    2: (None, "5V", "power"),
    4: (None, "5V", "power"),
    6: (None, "GND", "ground"),
    8: (14, "GPIO14 (TX)", "disabled"),
    10: (15, "GPIO15 (RX)", "disabled"),
    12: (18, "GPIO18", "gpio"),
    14: (None, "GND", "ground"),
    16: (23, "GPIO23", "gpio"),
    18: (24, "GPIO24", "gpio"),
    20: (None, "GND", "ground"),
    22: (25, "GPIO25", "gpio"),
    24: (8, "GPIO8 (CE0)", "disabled"),
    26: (7, "GPIO7 (CE1)", "disabled"),
    28: (1, "GPIO1 (ID_SC)", "disabled"),
    30: (None, "GND", "ground"),
    32: (12, "GPIO12", "gpio"),
    34: (None, "GND", "ground"),
    36: (16, "GPIO16", "gpio"),
    38: (20, "GPIO20", "gpio"),
    40: (21, "GPIO21", "gpio"),
}

# Ground pins for wiring suggestions
GROUND_PINS = [6, 9, 14, 20, 25, 30, 34, 39]


def _read_file_content(filepath: str) -> Optional[str]:
    """Safely read file content"""
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                return f.read().strip()
    except (IOError, PermissionError) as e:
        logger.debug("file_read_error", path=filepath, error=str(e))
    return None


def _parse_pi_model(model_string: str) -> Tuple[Optional[str], Optional[int]]:
    """
    Parse the Pi model string to extract model name and number.

    Args:
        model_string: Raw model string from /sys/firmware/devicetree/base/model

    Returns:
        Tuple of (clean_model_name, model_number)
    """
    if not model_string:
        return None, None

    # Clean up the string (remove null bytes)
    model_string = model_string.replace('\x00', '').strip()

    # Check if it's a Raspberry Pi
    if 'Raspberry Pi' not in model_string:
        return None, None

    # Extract model number (4 or 5)
    match = re.search(r'Raspberry Pi (\d)', model_string)
    if match:
        model_number = int(match.group(1))
        return model_string, model_number

    return model_string, None


def _check_pi_mock() -> Optional[PlatformInfo]:
    """
    Check if PI_MOCK environment variable is set.

    When PI_MOCK=true, returns a mocked Pi 5 platform for testing
    GPIO features on non-Pi systems (e.g., macOS development).
    """
    pi_mock = os.environ.get('PI_MOCK', 'false').lower()
    if pi_mock in ('true', '1', 'yes'):
        logger.info(
            "pi_mock_enabled",
            model="Raspberry Pi 5 Model B Rev 1.0 (Mock)",
            model_number=5,
            gpio_available=True
        )
        return PlatformInfo(
            is_raspberry_pi=True,
            model="Raspberry Pi 5 Model B Rev 1.0 (Mock)",
            model_number=5,
            gpio_available=True
        )
    return None


@lru_cache(maxsize=1)
def detect_platform() -> PlatformInfo:
    """
    Detect if running on a Raspberry Pi and which model.

    Set PI_MOCK=true environment variable to simulate a Pi 5 for testing.

    Returns:
        PlatformInfo with detection results
    """
    # Check for mock mode first (for development/testing)
    mock_platform = _check_pi_mock()
    if mock_platform:
        return mock_platform

    # Try to read the device tree model
    model_content = _read_file_content('/sys/firmware/devicetree/base/model')

    if model_content:
        model_name, model_number = _parse_pi_model(model_content)

        if model_name and model_number:
            # Check if it's a supported model (Pi 4 or 5)
            if model_number in (4, 5):
                logger.info(
                    "raspberry_pi_detected",
                    model=model_name,
                    model_number=model_number,
                    gpio_available=True
                )
                return PlatformInfo(
                    is_raspberry_pi=True,
                    model=model_name,
                    model_number=model_number,
                    gpio_available=True
                )
            else:
                logger.info(
                    "raspberry_pi_unsupported",
                    model=model_name,
                    model_number=model_number,
                    reason="Only Pi 4 and Pi 5 are supported"
                )
                return PlatformInfo(
                    is_raspberry_pi=True,
                    model=model_name,
                    model_number=model_number,
                    gpio_available=False,
                    reason=f"Raspberry Pi {model_number} is not supported. Only Pi 4 and Pi 5 are supported."
                )

    # Fallback: check /proc/cpuinfo for older detection method
    cpuinfo = _read_file_content('/proc/cpuinfo')
    if cpuinfo and 'Raspberry Pi' in cpuinfo:
        # Try to extract model from cpuinfo
        match = re.search(r'Model\s*:\s*(.+)', cpuinfo)
        if match:
            model_name, model_number = _parse_pi_model(match.group(1))
            if model_name and model_number in (4, 5):
                logger.info(
                    "raspberry_pi_detected_cpuinfo",
                    model=model_name,
                    model_number=model_number
                )
                return PlatformInfo(
                    is_raspberry_pi=True,
                    model=model_name,
                    model_number=model_number,
                    gpio_available=True
                )
            elif model_name and model_number:
                # It's a Pi, but not a supported model (Pi 3, Pi Zero, etc.)
                logger.info(
                    "raspberry_pi_unsupported_cpuinfo",
                    model=model_name,
                    model_number=model_number,
                    reason="Only Pi 4 and Pi 5 are supported"
                )
                return PlatformInfo(
                    is_raspberry_pi=True,
                    model=model_name,
                    model_number=model_number,
                    gpio_available=False,
                    reason=f"Raspberry Pi {model_number} is not supported. Only Pi 4 and Pi 5 are supported."
                )
            else:
                # It's a Pi but we couldn't determine the model number
                logger.info(
                    "raspberry_pi_unknown_model",
                    model=model_name,
                    reason="Could not determine Pi model number"
                )
                return PlatformInfo(
                    is_raspberry_pi=True,
                    model=model_name,
                    model_number=None,
                    gpio_available=False,
                    reason="Could not determine Raspberry Pi model. Only Pi 4 and Pi 5 are supported."
                )

    # Not a Raspberry Pi
    logger.info("not_raspberry_pi", reason="Device tree model not found or not a Pi")
    return PlatformInfo(
        is_raspberry_pi=False,
        model=None,
        model_number=None,
        gpio_available=False,
        reason="Not running on a Raspberry Pi"
    )


def get_gpio_layout() -> Dict[str, Any]:
    """
    Get the GPIO header pin layout for the UI.

    Returns:
        Dictionary with header_pins array and ground_pins for wiring suggestions
    """
    header_pins = []

    for physical_pin in range(1, 41):
        bcm, label, pin_type = GPIO_HEADER_LAYOUT[physical_pin]

        pin_info = {
            "physical": physical_pin,
            "type": pin_type,
            "label": label,
        }

        if bcm is not None:
            pin_info["bcm"] = bcm

            # Add reason if disabled
            if pin_type == "disabled" and bcm in DISABLED_GPIO_PINS:
                pin_info["disabled_reason"] = DISABLED_GPIO_PINS[bcm]

        header_pins.append(pin_info)

    return {
        "header_pins": header_pins,
        "ground_pins": GROUND_PINS,
        "available_bcm_pins": AVAILABLE_GPIO_PINS,
    }


def find_nearest_ground(physical_pin: int) -> int:
    """
    Find the nearest ground pin to a given physical pin.

    Args:
        physical_pin: Physical pin number (1-40)

    Returns:
        Physical pin number of nearest ground
    """
    if physical_pin < 1 or physical_pin > 40:
        return GROUND_PINS[0]

    # Find the closest ground pin
    min_distance = float('inf')
    nearest = GROUND_PINS[0]

    for ground_pin in GROUND_PINS:
        distance = abs(ground_pin - physical_pin)
        if distance < min_distance:
            min_distance = distance
            nearest = ground_pin

    return nearest


def bcm_to_physical(bcm_pin: int) -> Optional[int]:
    """
    Convert BCM pin number to physical pin number.

    Args:
        bcm_pin: BCM GPIO number

    Returns:
        Physical pin number or None if not found
    """
    for physical, (bcm, _, _) in GPIO_HEADER_LAYOUT.items():
        if bcm == bcm_pin:
            return physical
    return None


def physical_to_bcm(physical_pin: int) -> Optional[int]:
    """
    Convert physical pin number to BCM pin number.

    Args:
        physical_pin: Physical pin number (1-40)

    Returns:
        BCM GPIO number or None if not a GPIO pin
    """
    if physical_pin in GPIO_HEADER_LAYOUT:
        bcm, _, pin_type = GPIO_HEADER_LAYOUT[physical_pin]
        if pin_type == "gpio":
            return bcm
    return None
