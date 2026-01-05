"""
Dim-to-Warm (DTW) Calculation Module

Provides automatic color temperature adjustment based on brightness level,
mimicking the behavior of incandescent dimming where lower brightness
produces warmer (lower CCT) light.

Supports multiple curve types:
- LINEAR: Direct interpolation, even CCT change per brightness step
- LOG: Logarithmic, more CCT change at low brightness (recommended)
- SQUARE: Quadratic, gentle warm-up, aggressive at low end
- INCANDESCENT: Models actual filament behavior (T ∝ power^0.25)
"""
import math
from enum import Enum
from dataclasses import dataclass
from typing import Optional


class DTWCurve(Enum):
    """Curve types for dim-to-warm calculation."""
    LINEAR = "linear"
    LOG = "log"
    SQUARE = "square"
    INCANDESCENT = "incandescent"


@dataclass
class DTWConfig:
    """Configuration for dim-to-warm calculations."""
    enabled: bool = True
    min_cct: int = 1800  # CCT at minimum brightness (Kelvin)
    max_cct: int = 4000  # CCT at maximum brightness (Kelvin)
    min_brightness: float = 0.001  # Brightness floor for DTW curve
    curve: DTWCurve = DTWCurve.LOG
    override_timeout: int = 28800  # Override expiration in seconds (8 hours)


@dataclass
class DTWResult:
    """Result of a DTW calculation."""
    cct: int  # Calculated CCT in Kelvin
    source: str  # Source of the CCT value ('dtw_auto', 'override', 'fixture_default', etc.)


# Default system configuration
DEFAULT_DTW_CONFIG = DTWConfig()


def calculate_dtw_cct(
    brightness: float,
    min_cct: int = 1800,
    max_cct: int = 4000,
    min_brightness: float = 0.001,
    curve: DTWCurve = DTWCurve.LOG
) -> int:
    """
    Calculate color temperature based on brightness level using dim-to-warm curve.

    Lower brightness produces warmer (lower CCT) light, simulating incandescent
    thermal behavior for a more natural dimming experience.

    Args:
        brightness: Target brightness (0.0 to 1.0)
        min_cct: Color temperature at minimum brightness (Kelvin)
        max_cct: Color temperature at maximum brightness (Kelvin)
        min_brightness: Brightness floor for DTW curve (below this, use min_cct)
        curve: Interpolation curve type

    Returns:
        Calculated color temperature in Kelvin

    Examples:
        >>> calculate_dtw_cct(1.0, 1800, 4000, 0.001, DTWCurve.LOG)
        4000
        >>> calculate_dtw_cct(0.0, 1800, 4000, 0.001, DTWCurve.LOG)
        1800
        >>> calculate_dtw_cct(0.5, 1800, 4000, 0.001, DTWCurve.LINEAR)
        2900
    """
    # Validate inputs
    if min_cct >= max_cct:
        raise ValueError(f"min_cct ({min_cct}) must be less than max_cct ({max_cct})")

    # Handle edge cases
    if brightness <= 0:
        return min_cct
    if brightness >= 1.0:
        return max_cct

    # Clamp brightness to valid range
    effective_brightness = max(min_brightness, min(1.0, brightness))

    # Apply curve transformation to get normalized position (0.0 to 1.0)
    t = _apply_curve(effective_brightness, curve)

    # Interpolate CCT (min_cct is at LOW brightness, max_cct at HIGH)
    cct = round(min_cct + (max_cct - min_cct) * t)

    return cct


def _apply_curve(brightness: float, curve: DTWCurve) -> float:
    """
    Apply curve transformation to brightness value.

    Args:
        brightness: Effective brightness (0.0 to 1.0, already clamped)
        curve: Curve type to apply

    Returns:
        Normalized position on curve (0.0 to 1.0)
    """
    if curve == DTWCurve.LINEAR:
        # Direct interpolation
        return brightness

    elif curve == DTWCurve.LOG:
        # Logarithmic: more CCT change at low brightness
        # Formula: log10(1 + 9 * brightness) / log10(10)
        # At brightness=0: log10(1)/1 = 0
        # At brightness=1: log10(10)/1 = 1
        return math.log10(1 + 9 * brightness) / math.log10(10)

    elif curve == DTWCurve.SQUARE:
        # Quadratic: gentle warm-up, aggressive at low end
        return brightness * brightness

    elif curve == DTWCurve.INCANDESCENT:
        # Models actual filament behavior
        # CCT ∝ T, power ∝ T^4 (Stefan-Boltzmann)
        # So T ∝ power^0.25, and brightness ∝ power
        return math.pow(brightness, 0.25)

    else:
        # Fallback to linear
        return brightness


def calculate_dtw_cct_with_config(
    brightness: float,
    config: Optional[DTWConfig] = None
) -> int:
    """
    Calculate DTW CCT using a configuration object.

    Args:
        brightness: Target brightness (0.0 to 1.0)
        config: DTW configuration (uses defaults if not provided)

    Returns:
        Calculated color temperature in Kelvin
    """
    if config is None:
        config = DEFAULT_DTW_CONFIG

    if not config.enabled:
        # If DTW is disabled, return max_cct (neutral)
        return config.max_cct

    return calculate_dtw_cct(
        brightness=brightness,
        min_cct=config.min_cct,
        max_cct=config.max_cct,
        min_brightness=config.min_brightness,
        curve=config.curve
    )


def get_example_values(
    min_cct: int = 1800,
    max_cct: int = 4000,
    curve: DTWCurve = DTWCurve.LOG
) -> list:
    """
    Get example CCT values for a range of brightness levels.

    Useful for testing and displaying curve behavior.

    Args:
        min_cct: Minimum CCT in Kelvin
        max_cct: Maximum CCT in Kelvin
        curve: Curve type

    Returns:
        List of (brightness, cct) tuples
    """
    brightness_levels = [1.0, 0.75, 0.50, 0.25, 0.10, 0.05, 0.01]
    return [
        (b, calculate_dtw_cct(b, min_cct, max_cct, 0.001, curve))
        for b in brightness_levels
    ]


def validate_dtw_config(config: DTWConfig) -> list:
    """
    Validate a DTW configuration.

    Args:
        config: Configuration to validate

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    if config.min_cct < 1000:
        errors.append(f"min_cct ({config.min_cct}) must be at least 1000K")
    if config.min_cct > 10000:
        errors.append(f"min_cct ({config.min_cct}) must be at most 10000K")
    if config.max_cct < 1000:
        errors.append(f"max_cct ({config.max_cct}) must be at least 1000K")
    if config.max_cct > 10000:
        errors.append(f"max_cct ({config.max_cct}) must be at most 10000K")
    if config.min_cct >= config.max_cct:
        errors.append(f"min_cct ({config.min_cct}) must be less than max_cct ({config.max_cct})")
    if config.min_brightness < 0.0 or config.min_brightness > 1.0:
        errors.append(f"min_brightness ({config.min_brightness}) must be between 0.0 and 1.0")
    if config.override_timeout < 0:
        errors.append(f"override_timeout ({config.override_timeout}) must be non-negative")

    return errors
