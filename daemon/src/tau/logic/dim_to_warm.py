"""
Dim-to-Warm Logic

Implements automatic color temperature adjustment based on brightness level,
mimicking the behavior of incandescent bulbs. As incandescent bulbs dim, they
get warmer (lower CCT) due to the physics of the heated filament.

The relationship follows a power curve (typically square root) for natural feel:
- At 100% brightness: higher CCT (e.g., 3000K) - bright white
- At lower brightness: progressively warmer (lower CCT)
- At minimum brightness: warmest CCT (e.g., 1800K) - candle-like

Configuration hierarchy (highest priority first):
1. Fixture-level overrides
2. Group-level overrides
3. System defaults
4. Fixture model CCT limits (always enforced)
"""
from dataclasses import dataclass
from typing import Optional, Tuple
import structlog

logger = structlog.get_logger(__name__)


# Default values (used when no system settings are loaded)
DEFAULT_MAX_CCT_KELVIN = 3000  # At 100% brightness
DEFAULT_MIN_CCT_KELVIN = 1800  # At minimum brightness
DEFAULT_CURVE_EXPONENT = 0.5   # Square root for incandescent-like feel


@dataclass
class DimToWarmConfig:
    """Configuration for dim-to-warm behavior"""
    max_cct_kelvin: int = DEFAULT_MAX_CCT_KELVIN
    min_cct_kelvin: int = DEFAULT_MIN_CCT_KELVIN
    curve_exponent: float = DEFAULT_CURVE_EXPONENT


@dataclass
class DimToWarmParams:
    """Parameters for a specific fixture's dim-to-warm calculation"""
    enabled: bool = False
    max_cct: int = DEFAULT_MAX_CCT_KELVIN
    min_cct: int = DEFAULT_MIN_CCT_KELVIN
    curve_exponent: float = DEFAULT_CURVE_EXPONENT
    # Fixture model limits (hard constraints)
    fixture_cct_min: Optional[int] = None
    fixture_cct_max: Optional[int] = None


class DimToWarmEngine:
    """
    Engine for calculating dim-to-warm color temperature based on brightness.

    Manages system-wide configuration and provides calculation methods for
    individual fixtures and groups.
    """

    def __init__(self):
        """Initialize with default configuration"""
        self.config = DimToWarmConfig()
        logger.info(
            "dim_to_warm_engine_initialized",
            max_cct=self.config.max_cct_kelvin,
            min_cct=self.config.min_cct_kelvin,
            curve_exponent=self.config.curve_exponent,
        )

    def update_config(
        self,
        max_cct_kelvin: Optional[int] = None,
        min_cct_kelvin: Optional[int] = None,
        curve_exponent: Optional[float] = None,
    ) -> None:
        """
        Update system-wide dim-to-warm configuration.

        Args:
            max_cct_kelvin: CCT at 100% brightness
            min_cct_kelvin: CCT at minimum brightness
            curve_exponent: Power curve exponent (0.5 = square root)
        """
        if max_cct_kelvin is not None:
            self.config.max_cct_kelvin = max_cct_kelvin
        if min_cct_kelvin is not None:
            self.config.min_cct_kelvin = min_cct_kelvin
        if curve_exponent is not None:
            self.config.curve_exponent = curve_exponent

        logger.info(
            "dim_to_warm_config_updated",
            max_cct=self.config.max_cct_kelvin,
            min_cct=self.config.min_cct_kelvin,
            curve_exponent=self.config.curve_exponent,
        )

    def get_effective_params(
        self,
        fixture_enabled: Optional[bool] = None,
        fixture_max_cct: Optional[int] = None,
        fixture_min_cct: Optional[int] = None,
        group_enabled: Optional[bool] = None,
        group_max_cct: Optional[int] = None,
        group_min_cct: Optional[int] = None,
        fixture_cct_min: Optional[int] = None,
        fixture_cct_max: Optional[int] = None,
    ) -> DimToWarmParams:
        """
        Resolve effective dim-to-warm parameters using priority hierarchy.

        Priority (highest first):
        1. Fixture-level settings
        2. Group-level settings
        3. System defaults

        The final CCT range is also constrained by fixture model limits.

        Args:
            fixture_enabled: Fixture-level dim-to-warm enabled flag
            fixture_max_cct: Fixture-level max CCT override
            fixture_min_cct: Fixture-level min CCT override
            group_enabled: Group-level dim-to-warm enabled flag
            group_max_cct: Group-level max CCT override
            group_min_cct: Group-level min CCT override
            fixture_cct_min: Fixture model minimum CCT (hard limit)
            fixture_cct_max: Fixture model maximum CCT (hard limit)

        Returns:
            DimToWarmParams with resolved configuration
        """
        # Determine if enabled (fixture overrides group)
        if fixture_enabled is not None:
            enabled = fixture_enabled
        elif group_enabled is not None:
            enabled = group_enabled
        else:
            enabled = False

        # Resolve max CCT (fixture overrides group overrides system)
        if fixture_max_cct is not None:
            max_cct = fixture_max_cct
        elif group_max_cct is not None:
            max_cct = group_max_cct
        else:
            # Use system default, but cap at fixture max if specified
            max_cct = self.config.max_cct_kelvin
            if fixture_cct_max is not None:
                max_cct = min(max_cct, fixture_cct_max)

        # Resolve min CCT (fixture overrides group overrides system)
        if fixture_min_cct is not None:
            min_cct = fixture_min_cct
        elif group_min_cct is not None:
            min_cct = group_min_cct
        else:
            # Use system default, but floor at fixture min if specified
            min_cct = self.config.min_cct_kelvin
            if fixture_cct_min is not None:
                min_cct = max(min_cct, fixture_cct_min)

        # Enforce fixture model limits
        if fixture_cct_min is not None:
            min_cct = max(min_cct, fixture_cct_min)
        if fixture_cct_max is not None:
            max_cct = min(max_cct, fixture_cct_max)

        # Ensure min <= max
        if min_cct > max_cct:
            # If limits are inverted, use the midpoint
            midpoint = (min_cct + max_cct) // 2
            min_cct = midpoint
            max_cct = midpoint

        return DimToWarmParams(
            enabled=enabled,
            max_cct=max_cct,
            min_cct=min_cct,
            curve_exponent=self.config.curve_exponent,
            fixture_cct_min=fixture_cct_min,
            fixture_cct_max=fixture_cct_max,
        )

    def calculate_cct(
        self,
        brightness: float,
        params: DimToWarmParams,
    ) -> Optional[int]:
        """
        Calculate the color temperature for a given brightness level.

        Uses a power curve to mimic incandescent behavior:
        CCT = min_cct + (max_cct - min_cct) * (brightness ^ exponent)

        With exponent < 1 (e.g., 0.5), the CCT drops more quickly at lower
        brightness levels, which matches how incandescent bulbs behave.

        Args:
            brightness: Brightness level from 0.0 to 1.0
            params: Dim-to-warm parameters for this calculation

        Returns:
            Calculated CCT in Kelvin, or None if not enabled
        """
        if not params.enabled:
            return None

        # Clamp brightness to valid range
        brightness = max(0.0, min(1.0, brightness))

        # Apply power curve
        # At brightness=0: CCT = min_cct
        # At brightness=1: CCT = max_cct
        if params.curve_exponent <= 0:
            # Avoid invalid exponent
            curve_factor = brightness
        else:
            curve_factor = brightness ** params.curve_exponent

        cct = params.min_cct + (params.max_cct - params.min_cct) * curve_factor

        # Round to integer and clamp to fixture limits
        cct = round(cct)
        if params.fixture_cct_min is not None:
            cct = max(cct, params.fixture_cct_min)
        if params.fixture_cct_max is not None:
            cct = min(cct, params.fixture_cct_max)

        return cct

    def calculate_cct_simple(
        self,
        brightness: float,
        max_cct: int = DEFAULT_MAX_CCT_KELVIN,
        min_cct: int = DEFAULT_MIN_CCT_KELVIN,
        curve_exponent: float = DEFAULT_CURVE_EXPONENT,
    ) -> int:
        """
        Simple CCT calculation without full parameter resolution.

        Useful for quick calculations when all parameters are already known.

        Args:
            brightness: Brightness level from 0.0 to 1.0
            max_cct: CCT at 100% brightness
            min_cct: CCT at minimum brightness
            curve_exponent: Power curve exponent

        Returns:
            Calculated CCT in Kelvin
        """
        brightness = max(0.0, min(1.0, brightness))

        if curve_exponent <= 0:
            curve_factor = brightness
        else:
            curve_factor = brightness ** curve_exponent

        cct = min_cct + (max_cct - min_cct) * curve_factor
        return round(cct)

    def get_statistics(self) -> dict:
        """Get engine statistics"""
        return {
            "max_cct_kelvin": self.config.max_cct_kelvin,
            "min_cct_kelvin": self.config.min_cct_kelvin,
            "curve_exponent": self.config.curve_exponent,
        }


# Global engine instance
_engine: Optional[DimToWarmEngine] = None


def get_dim_to_warm_engine() -> DimToWarmEngine:
    """Get or create the global dim-to-warm engine instance"""
    global _engine
    if _engine is None:
        _engine = DimToWarmEngine()
    return _engine


def calculate_dim_to_warm_cct(
    brightness: float,
    fixture_enabled: Optional[bool] = None,
    fixture_max_cct: Optional[int] = None,
    fixture_min_cct: Optional[int] = None,
    group_enabled: Optional[bool] = None,
    group_max_cct: Optional[int] = None,
    group_min_cct: Optional[int] = None,
    fixture_cct_min: Optional[int] = None,
    fixture_cct_max: Optional[int] = None,
) -> Optional[int]:
    """
    Convenience function to calculate dim-to-warm CCT.

    Resolves parameters and calculates CCT in one call.

    Args:
        brightness: Brightness level from 0.0 to 1.0
        fixture_enabled: Fixture-level dim-to-warm enabled
        fixture_max_cct: Fixture-level max CCT override
        fixture_min_cct: Fixture-level min CCT override
        group_enabled: Group-level dim-to-warm enabled
        group_max_cct: Group-level max CCT override
        group_min_cct: Group-level min CCT override
        fixture_cct_min: Fixture model minimum CCT
        fixture_cct_max: Fixture model maximum CCT

    Returns:
        Calculated CCT in Kelvin, or None if dim-to-warm not enabled
    """
    engine = get_dim_to_warm_engine()
    params = engine.get_effective_params(
        fixture_enabled=fixture_enabled,
        fixture_max_cct=fixture_max_cct,
        fixture_min_cct=fixture_min_cct,
        group_enabled=group_enabled,
        group_max_cct=group_max_cct,
        group_min_cct=group_min_cct,
        fixture_cct_min=fixture_cct_min,
        fixture_cct_max=fixture_cct_max,
    )
    return engine.calculate_cct(brightness, params)
