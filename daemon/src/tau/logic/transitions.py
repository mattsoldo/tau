"""
Transition and Easing Functions for Lighting Control

Provides smooth transitions for brightness and CCT changes with configurable
easing functions. Transition times are proportional to the amount of change
within the full range.

Appendix B: Smooth Transitions Implementation
"""
import math
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class EasingFunction(Enum):
    """Available easing functions for transitions.

    LINEAR: Constant speed from start to end
    EASE_IN: Starts slow, accelerates toward end (quadratic)
    EASE_OUT: Starts fast, decelerates toward end (quadratic)
    EASE_IN_OUT: Starts slow, speeds up in middle, slows at end (quadratic)
    EASE_IN_CUBIC: Starts slow, accelerates toward end (cubic - more pronounced)
    EASE_OUT_CUBIC: Starts fast, decelerates toward end (cubic - more pronounced)
    EASE_IN_OUT_CUBIC: Slow start/end, fast middle (cubic - more pronounced)
    """
    LINEAR = "linear"
    EASE_IN = "ease_in"
    EASE_OUT = "ease_out"
    EASE_IN_OUT = "ease_in_out"
    EASE_IN_CUBIC = "ease_in_cubic"
    EASE_OUT_CUBIC = "ease_out_cubic"
    EASE_IN_OUT_CUBIC = "ease_in_out_cubic"


# Default easing function for all transitions
DEFAULT_EASING = EasingFunction.EASE_IN_OUT


def ease_linear(t: float) -> float:
    """Linear interpolation - constant speed.

    Args:
        t: Progress from 0.0 to 1.0

    Returns:
        Eased progress value
    """
    return t


def ease_in_quadratic(t: float) -> float:
    """Quadratic ease-in - starts slow, accelerates.

    Args:
        t: Progress from 0.0 to 1.0

    Returns:
        Eased progress value
    """
    return t * t


def ease_out_quadratic(t: float) -> float:
    """Quadratic ease-out - starts fast, decelerates.

    Args:
        t: Progress from 0.0 to 1.0

    Returns:
        Eased progress value
    """
    return 1.0 - (1.0 - t) * (1.0 - t)


def ease_in_out_quadratic(t: float) -> float:
    """Quadratic ease-in-out - slow start/end, fast middle.

    Args:
        t: Progress from 0.0 to 1.0

    Returns:
        Eased progress value
    """
    if t < 0.5:
        return 2.0 * t * t
    else:
        return 1.0 - math.pow(-2.0 * t + 2.0, 2) / 2.0


def ease_in_cubic(t: float) -> float:
    """Cubic ease-in - starts slow, accelerates (more pronounced).

    Args:
        t: Progress from 0.0 to 1.0

    Returns:
        Eased progress value
    """
    return t * t * t


def ease_out_cubic(t: float) -> float:
    """Cubic ease-out - starts fast, decelerates (more pronounced).

    Args:
        t: Progress from 0.0 to 1.0

    Returns:
        Eased progress value
    """
    return 1.0 - math.pow(1.0 - t, 3)


def ease_in_out_cubic(t: float) -> float:
    """Cubic ease-in-out - slow start/end, fast middle (more pronounced).

    Args:
        t: Progress from 0.0 to 1.0

    Returns:
        Eased progress value
    """
    if t < 0.5:
        return 4.0 * t * t * t
    else:
        return 1.0 - math.pow(-2.0 * t + 2.0, 3) / 2.0


# Mapping from EasingFunction enum to actual function
EASING_FUNCTIONS: dict[EasingFunction, Callable[[float], float]] = {
    EasingFunction.LINEAR: ease_linear,
    EasingFunction.EASE_IN: ease_in_quadratic,
    EasingFunction.EASE_OUT: ease_out_quadratic,
    EasingFunction.EASE_IN_OUT: ease_in_out_quadratic,
    EasingFunction.EASE_IN_CUBIC: ease_in_cubic,
    EasingFunction.EASE_OUT_CUBIC: ease_out_cubic,
    EasingFunction.EASE_IN_OUT_CUBIC: ease_in_out_cubic,
}


def get_easing_function(easing: EasingFunction) -> Callable[[float], float]:
    """Get the easing function for the given enum value.

    Args:
        easing: The easing function type

    Returns:
        The corresponding easing function
    """
    return EASING_FUNCTIONS.get(easing, ease_in_out_quadratic)


def apply_easing(t: float, easing: EasingFunction = DEFAULT_EASING) -> float:
    """Apply easing function to linear progress.

    Args:
        t: Linear progress from 0.0 to 1.0
        easing: The easing function to apply

    Returns:
        Eased progress value (0.0 to 1.0)
    """
    # Clamp input to valid range
    t = max(0.0, min(1.0, t))
    ease_func = get_easing_function(easing)
    return ease_func(t)


def interpolate_with_easing(
    start: float,
    end: float,
    t: float,
    easing: EasingFunction = DEFAULT_EASING
) -> float:
    """Interpolate between start and end using an easing function.

    Args:
        start: Starting value
        end: Ending value
        t: Linear progress from 0.0 to 1.0
        easing: The easing function to apply

    Returns:
        Interpolated value between start and end
    """
    eased_t = apply_easing(t, easing)
    return start + (end - start) * eased_t


@dataclass
class TransitionConfig:
    """Global configuration for lighting transitions.

    Transition times are specified for the full range of change:
    - brightness_transition_seconds: Time to go from 0% to 100% (or vice versa)
    - cct_transition_seconds: Time to go across the full CCT range of a fixture

    Actual transition time is proportional to the amount of change:
    - A 50% brightness change takes half the configured time
    - A CCT change of half the fixture's range takes half the configured time
    """
    # Time in seconds for full brightness transition (0% to 100%)
    brightness_transition_seconds: float = 0.5

    # Time in seconds for full CCT range transition
    cct_transition_seconds: float = 0.5

    # Default easing function
    default_easing: EasingFunction = DEFAULT_EASING

    # Minimum transition duration (prevents too-fast transitions)
    min_transition_seconds: float = 0.0

    # Maximum transition duration (prevents too-slow transitions)
    max_transition_seconds: float = 60.0


# Global transition configuration instance
_transition_config: Optional[TransitionConfig] = None


def get_transition_config() -> TransitionConfig:
    """Get the global transition configuration.

    Returns:
        The current TransitionConfig instance
    """
    global _transition_config
    if _transition_config is None:
        _transition_config = TransitionConfig()
    return _transition_config


def set_transition_config(config: TransitionConfig) -> None:
    """Set the global transition configuration.

    Args:
        config: The new TransitionConfig to use
    """
    global _transition_config
    _transition_config = config


def calculate_brightness_transition_time(
    start_brightness: float,
    end_brightness: float,
    config: Optional[TransitionConfig] = None
) -> float:
    """Calculate the transition time for a brightness change.

    Time is proportional to the amount of change within the 0-1 range.

    Args:
        start_brightness: Starting brightness (0.0 to 1.0)
        end_brightness: Ending brightness (0.0 to 1.0)
        config: Optional config override (uses global config if None)

    Returns:
        Transition time in seconds
    """
    if config is None:
        config = get_transition_config()

    # Calculate the fraction of the full range being traversed
    change = abs(end_brightness - start_brightness)

    # Proportional time based on change amount
    duration = config.brightness_transition_seconds * change

    # Apply min/max constraints
    duration = max(config.min_transition_seconds, min(config.max_transition_seconds, duration))

    return duration


def calculate_cct_transition_time(
    start_cct: int,
    end_cct: int,
    cct_min: int,
    cct_max: int,
    config: Optional[TransitionConfig] = None
) -> float:
    """Calculate the transition time for a CCT change.

    Time is proportional to the amount of change within the fixture's CCT range.

    Args:
        start_cct: Starting CCT in Kelvin
        end_cct: Ending CCT in Kelvin
        cct_min: Fixture's minimum CCT capability
        cct_max: Fixture's maximum CCT capability
        config: Optional config override (uses global config if None)

    Returns:
        Transition time in seconds
    """
    if config is None:
        config = get_transition_config()

    # Calculate the fraction of the fixture's CCT range being traversed
    cct_range = cct_max - cct_min
    if cct_range <= 0:
        return 0.0

    change = abs(end_cct - start_cct)
    fraction = change / cct_range

    # Proportional time based on change amount
    duration = config.cct_transition_seconds * fraction

    # Apply min/max constraints
    duration = max(config.min_transition_seconds, min(config.max_transition_seconds, duration))

    return duration


def calculate_combined_transition_time(
    start_brightness: float,
    end_brightness: float,
    start_cct: Optional[int],
    end_cct: Optional[int],
    cct_min: Optional[int],
    cct_max: Optional[int],
    config: Optional[TransitionConfig] = None
) -> float:
    """Calculate transition time when both brightness and CCT are changing.

    Returns the longer of the two individual transition times so both
    complete at the same time.

    Args:
        start_brightness: Starting brightness (0.0 to 1.0)
        end_brightness: Ending brightness (0.0 to 1.0)
        start_cct: Starting CCT in Kelvin (or None)
        end_cct: Ending CCT in Kelvin (or None)
        cct_min: Fixture's minimum CCT capability
        cct_max: Fixture's maximum CCT capability
        config: Optional config override (uses global config if None)

    Returns:
        Transition time in seconds (the longer of brightness or CCT time)
    """
    brightness_time = calculate_brightness_transition_time(
        start_brightness, end_brightness, config
    )

    cct_time = 0.0
    if start_cct is not None and end_cct is not None and cct_min is not None and cct_max is not None:
        cct_time = calculate_cct_transition_time(
            start_cct, end_cct, cct_min, cct_max, config
        )

    return max(brightness_time, cct_time)
