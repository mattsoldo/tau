"""
Planckian Locus Color Mixing Algorithm

Calculates optimal warm and cool LED channel intensities to achieve a target
correlated color temperature (CCT) while minimizing deviation from the Planckian
locus and maintaining perceptually constant brightness.

Based on the specification in specs/tunable_white.md
"""
import math
from dataclasses import dataclass
from typing import Optional, Tuple


# CIE Planckian locus approximation coefficients
# From CIE 15:2004 and Kim et al. (2002)
# Valid for 1667K ≤ T ≤ 25000K


@dataclass
class ColorMixResult:
    """Result of color mixing calculation"""
    warm_duty: int  # PWM duty cycle for warm channel (0 to pwm_resolution)
    cool_duty: int  # PWM duty cycle for cool channel (0 to pwm_resolution)
    achieved_cct: int  # Actual CCT achieved (may differ at range limits)
    achieved_duv: float  # Distance from Planckian locus (+ = green, − = pink)
    achieved_brightness: float  # Actual relative brightness (0.0-1.0)


@dataclass
class ColorMixParams:
    """Parameters for color mixing calculation.

    Attributes:
        warm_cct: CCT of warm LED channel (Kelvin)
        cool_cct: CCT of cool LED channel (Kelvin)
        warm_xy: CIE 1931 chromaticity coordinates of warm LED
        cool_xy: CIE 1931 chromaticity coordinates of cool LED
        warm_lumens: Luminous flux of warm channel at 100% (lm)
        cool_lumens: Luminous flux of cool channel at 100% (lm)
        pwm_resolution: Maximum PWM value (default 255 for 8-bit DMX)
        min_duty: Minimum non-zero duty cycle for LED drivers that have
            a turn-on threshold. Default 0 for maximum range. Set to ~5%
            of pwm_resolution (e.g., 13 for 8-bit) if LEDs flicker at low
            duty cycles.
        gamma: PWM-to-light gamma correction factor (default 2.2)
    """
    # CCT of warm and cool LED channels
    warm_cct: int
    cool_cct: int
    # CIE 1931 chromaticity coordinates
    warm_xy: Tuple[float, float]
    cool_xy: Tuple[float, float]
    # Luminous flux at 100%
    warm_lumens: int
    cool_lumens: int
    # PWM configuration
    pwm_resolution: int = 255  # 8-bit DMX
    min_duty: int = 0  # Minimum duty cycle (set to ~5% of resolution if LEDs flicker)
    gamma: float = 2.2  # PWM-to-light gamma correction


def planckian_xy(temp_kelvin: int) -> Tuple[float, float]:
    """
    Calculate CIE 1931 xy chromaticity coordinates on the Planckian locus
    for a given color temperature.

    Uses the CIE approximation formulas from CIE 15:2004 which provide
    accurate results across the full range of practical CCT values.

    Args:
        temp_kelvin: Color temperature in Kelvin (1667-25000K)

    Returns:
        Tuple of (x, y) chromaticity coordinates

    Raises:
        ValueError: If temp_kelvin is <= 0

    Note:
        The CIE approximation is valid for 1667K ≤ T ≤ 25000K. Values outside
        this range will extrapolate, which may produce inaccurate results.
        For practical tunable white applications (1800K-8000K), the formulas
        are highly accurate.
    """
    if temp_kelvin <= 0:
        raise ValueError(f"Temperature must be positive, got {temp_kelvin}K")

    t = float(temp_kelvin)

    # Calculate x using piecewise CIE approximation
    if t < 4000:
        # 1667K ≤ T < 4000K
        x = (
            -0.2661239e9 / (t * t * t)
            - 0.2343589e6 / (t * t)
            + 0.8776956e3 / t
            + 0.179910
        )
    else:
        # 4000K ≤ T ≤ 25000K
        x = (
            -3.0258469e9 / (t * t * t)
            + 2.1070379e6 / (t * t)
            + 0.2226347e3 / t
            + 0.240390
        )

    # Calculate y from x using piecewise polynomial
    if t < 2222:
        # 1667K ≤ T < 2222K
        y = -1.1063814 * x * x * x - 1.34811020 * x * x + 2.18555832 * x - 0.20219683
    elif t < 4000:
        # 2222K ≤ T < 4000K
        y = -0.9549476 * x * x * x - 1.37418593 * x * x + 2.09137015 * x - 0.16748867
    else:
        # 4000K ≤ T ≤ 25000K
        y = 3.0817580 * x * x * x - 5.87338670 * x * x + 3.75112997 * x - 0.37001483

    return (x, y)


def xy_to_uv(x: float, y: float) -> Tuple[float, float]:
    """
    Convert CIE 1931 xy to CIE 1960 uv chromaticity coordinates.

    The Duv calculation must be done in CIE 1960 UCS (uniform chromaticity scale).

    Args:
        x, y: CIE 1931 chromaticity coordinates

    Returns:
        Tuple of (u, v) chromaticity coordinates in CIE 1960 UCS
    """
    denom = -2.0 * x + 12.0 * y + 3.0
    if abs(denom) < 1e-9:
        return (0.0, 0.0)
    u = 4.0 * x / denom
    v = 6.0 * y / denom
    return (u, v)


def xy_to_cct(x: float, y: float) -> int:
    """
    Calculate CCT from CIE 1931 xy coordinates using McCamy's approximation.

    Args:
        x, y: CIE 1931 chromaticity coordinates

    Returns:
        Correlated Color Temperature in Kelvin
    """
    # McCamy's formula
    n = (x - 0.3320) / (0.1858 - y) if abs(0.1858 - y) > 1e-9 else 0.0
    n2 = n * n
    n3 = n2 * n
    cct = 449.0 * n3 + 3525.0 * n2 + 6823.3 * n + 5520.33
    return max(1000, min(25000, round(cct)))


def calculate_mix_ratio(
    target_xy: Tuple[float, float],
    warm_xy: Tuple[float, float],
    cool_xy: Tuple[float, float]
) -> float:
    """
    Calculate the mixing ratio (alpha) where:
    target = alpha * cool + (1 - alpha) * warm

    Args:
        target_xy: Target chromaticity coordinates
        warm_xy: Warm LED chromaticity coordinates
        cool_xy: Cool LED chromaticity coordinates

    Returns:
        Alpha value (0.0 = all warm, 1.0 = all cool)
    """
    dx = cool_xy[0] - warm_xy[0]

    if abs(dx) < 1e-9:
        # LEDs have same x-coordinate, use y instead
        dy = cool_xy[1] - warm_xy[1]
        if abs(dy) < 1e-9:
            return 0.5  # LEDs too similar
        alpha = (target_xy[1] - warm_xy[1]) / dy
    else:
        alpha = (target_xy[0] - warm_xy[0]) / dx

    # Clamp to valid range
    return max(0.0, min(1.0, alpha))


def calculate_duv(achieved_xy: Tuple[float, float], achieved_cct: int) -> float:
    """
    Calculate Duv (deviation from Planckian locus).

    Args:
        achieved_xy: Actual chromaticity coordinates
        achieved_cct: Actual CCT in Kelvin

    Returns:
        Duv value (positive = greenish, negative = pinkish)
    """
    # Get the Planckian reference point for this CCT
    planck_xy = planckian_xy(achieved_cct)

    # Convert both to CIE 1960 uv
    achieved_uv = xy_to_uv(achieved_xy[0], achieved_xy[1])
    planck_uv = xy_to_uv(planck_xy[0], planck_xy[1])

    # Euclidean distance in uv space
    du = achieved_uv[0] - planck_uv[0]
    dv = achieved_uv[1] - planck_uv[1]
    distance = math.sqrt(du * du + dv * dv)

    # Sign convention: positive = above locus (greenish), negative = below (pinkish)
    if achieved_uv[1] > planck_uv[1]:
        return distance
    else:
        return -distance


def calculate_led_mix(
    target_cct: int,
    target_brightness: float,
    params: ColorMixParams
) -> ColorMixResult:
    """
    Calculate optimal warm and cool LED duty cycles for target CCT and brightness.

    This implements the Planckian locus tracking algorithm with:
    - Chromaticity-based mixing for accurate color
    - Luminous flux compensation for constant brightness
    - Gamma correction for perceptual linearity

    Args:
        target_cct: Desired color temperature in Kelvin
        target_brightness: Desired brightness (0.0-1.0)
        params: Color mixing parameters

    Returns:
        ColorMixResult with duty cycles and achieved values
    """
    # Handle zero brightness
    if target_brightness <= 0:
        return ColorMixResult(
            warm_duty=0,
            cool_duty=0,
            achieved_cct=target_cct,
            achieved_duv=0.0,
            achieved_brightness=0.0
        )

    # 1. Clamp target CCT to achievable range
    effective_cct = max(params.warm_cct, min(params.cool_cct, target_cct))

    # 2. Get target chromaticity on Planckian locus
    target_xy = planckian_xy(effective_cct)

    # 3. Calculate mixing ratio
    alpha = calculate_mix_ratio(target_xy, params.warm_xy, params.cool_xy)

    # 4. Calculate flux-compensated linear duties
    # For constant brightness across CCT range, we need:
    #   warm_flux + cool_flux = target_brightness × total_lumens
    # where warm_flux = warm_duty^γ × warm_lumens
    #
    # The mixing ratio α determines color, so:
    #   warm_flux = (1-α) × target_brightness × total_lumens
    #   cool_flux = α × target_brightness × total_lumens
    #
    # Solving for linear duty (pre-gamma):
    #   warm_linear = (1-α) × target_brightness × total_lumens / warm_lumens
    #   cool_linear = α × target_brightness × total_lumens / cool_lumens
    warm_contribution = 1.0 - alpha
    cool_contribution = alpha

    total_lumens = params.warm_lumens + params.cool_lumens

    # Calculate linear duty with flux compensation
    if params.warm_lumens > 0:
        warm_linear = warm_contribution * target_brightness * (float(total_lumens) / params.warm_lumens)
    else:
        warm_linear = 0.0
    if params.cool_lumens > 0:
        cool_linear = cool_contribution * target_brightness * (float(total_lumens) / params.cool_lumens)
    else:
        cool_linear = 0.0

    # Clamp to prevent overflow
    warm_linear = max(0.0, min(1.0, warm_linear))
    cool_linear = max(0.0, min(1.0, cool_linear))

    # 5. Apply inverse gamma correction and quantize to integers
    # duty_pwm^gamma = duty_linear, so duty_pwm = duty_linear^(1/gamma)
    gamma_inv = 1.0 / params.gamma
    warm_normalized = math.pow(warm_linear, gamma_inv) if warm_linear > 0 else 0.0
    cool_normalized = math.pow(cool_linear, gamma_inv) if cool_linear > 0 else 0.0

    warm_duty = round(warm_normalized * params.pwm_resolution)
    cool_duty = round(cool_normalized * params.pwm_resolution)

    # 6. Apply hardware constraints
    if 0 < warm_duty < params.min_duty:
        warm_duty = params.min_duty
    if 0 < cool_duty < params.min_duty:
        cool_duty = params.min_duty

    warm_duty = min(warm_duty, params.pwm_resolution)
    cool_duty = min(cool_duty, params.pwm_resolution)

    # 7. Calculate achieved values for verification
    warm_flux = params.warm_lumens * math.pow(
        float(warm_duty) / params.pwm_resolution, params.gamma
    ) if warm_duty > 0 else 0.0
    cool_flux = params.cool_lumens * math.pow(
        float(cool_duty) / params.pwm_resolution, params.gamma
    ) if cool_duty > 0 else 0.0
    total_flux = warm_flux + cool_flux

    if total_flux > 0:
        achieved_x = (params.warm_xy[0] * warm_flux + params.cool_xy[0] * cool_flux) / total_flux
        achieved_y = (params.warm_xy[1] * warm_flux + params.cool_xy[1] * cool_flux) / total_flux
        achieved_cct = xy_to_cct(achieved_x, achieved_y)
        achieved_duv = calculate_duv((achieved_x, achieved_y), achieved_cct)
        achieved_brightness = total_flux / float(total_lumens)
    else:
        achieved_cct = effective_cct
        achieved_duv = 0.0
        achieved_brightness = 0.0

    return ColorMixResult(
        warm_duty=warm_duty,
        cool_duty=cool_duty,
        achieved_cct=achieved_cct,
        achieved_duv=achieved_duv,
        achieved_brightness=achieved_brightness
    )


def calculate_led_mix_simple(
    target_cct: int,
    target_brightness: float,
    cct_min: int,
    cct_max: int,
    pwm_resolution: int = 255,
    gamma: float = 2.2
) -> Tuple[int, int]:
    """
    Simplified color mixing when chromaticity coordinates are not available.

    Uses linear interpolation based on CCT with gamma correction.
    This is a fallback when full Planckian locus parameters aren't configured.

    Args:
        target_cct: Desired color temperature in Kelvin
        target_brightness: Desired brightness (0.0-1.0)
        cct_min: Warm LED CCT
        cct_max: Cool LED CCT
        pwm_resolution: Maximum PWM value (e.g., 255)
        gamma: PWM-to-light gamma correction

    Returns:
        Tuple of (warm_duty, cool_duty)
    """
    if target_brightness <= 0:
        return (0, 0)

    # Clamp CCT to range
    effective_cct = max(cct_min, min(cct_max, target_cct))

    # Normalize CCT to 0-1 (0 = warm, 1 = cool)
    cct_range = cct_max - cct_min
    if cct_range <= 0:
        cct_normalized = 0.5
    else:
        cct_normalized = (effective_cct - cct_min) / cct_range

    # Linear mixing ratios
    warm_linear = (1.0 - cct_normalized) * target_brightness
    cool_linear = cct_normalized * target_brightness

    # Apply inverse gamma correction
    gamma_inv = 1.0 / gamma
    warm_normalized = math.pow(warm_linear, gamma_inv) if warm_linear > 0 else 0.0
    cool_normalized = math.pow(cool_linear, gamma_inv) if cool_linear > 0 else 0.0

    # Quantize
    warm_duty = round(warm_normalized * pwm_resolution)
    cool_duty = round(cool_normalized * pwm_resolution)

    return (min(warm_duty, pwm_resolution), min(cool_duty, pwm_resolution))


def get_default_chromaticity(cct: int) -> Tuple[float, float]:
    """
    Get CIE 1931 xy chromaticity for a CCT value on the Planckian locus.

    This is an alias for planckian_xy() for backwards compatibility.

    Args:
        cct: Color temperature in Kelvin

    Returns:
        Tuple of (x, y) chromaticity coordinates
    """
    return planckian_xy(cct)


@dataclass
class ColorMixResultDerived(ColorMixResult):
    """Result of color mixing with derived xy (fallback mode)"""
    xy_derived: bool = True  # Indicates xy was derived from CCT
    duv_uncertainty: float = 0.0  # Estimated ± error on achieved_duv


def calculate_led_mix_lumens_only(
    target_cct: int,
    target_brightness: float,
    warm_cct: int,
    cool_cct: int,
    warm_lumens: int,
    cool_lumens: int,
    pwm_resolution: int = 255,
    min_duty: int = 0,
    gamma: float = 2.2,
    macadam_step: int = 7
) -> ColorMixResultDerived:
    """
    Calculate LED mix when only lumens are available (no chromaticity data).

    This fallback mode derives xy chromaticity from CCT using the Planckian locus
    approximation. It assumes both LED channels sit exactly on the black body curve
    (Duv = 0), which is rarely true for real LEDs.

    The algorithm is less accurate than using measured chromaticity data, but still
    provides flux compensation for constant brightness across the CCT range.

    Args:
        target_cct: Desired color temperature in Kelvin
        target_brightness: Desired brightness (0.0-1.0)
        warm_cct: CCT of warm LED channel
        cool_cct: CCT of cool LED channel
        warm_lumens: Luminous flux of warm channel at 100%
        cool_lumens: Luminous flux of cool channel at 100%
        pwm_resolution: Maximum PWM value (e.g., 255)
        min_duty: Minimum duty cycle
        gamma: PWM-to-light gamma correction
        macadam_step: LED binning tolerance (default 7 = worst case)

    Returns:
        ColorMixResultDerived with duty cycles, achieved values, and uncertainty
    """
    # Derive xy from CCT using Planckian locus
    warm_xy = planckian_xy(warm_cct)
    cool_xy = planckian_xy(cool_cct)

    # Create params and use the full algorithm
    params = ColorMixParams(
        warm_cct=warm_cct,
        cool_cct=cool_cct,
        warm_xy=warm_xy,
        cool_xy=cool_xy,
        warm_lumens=warm_lumens,
        cool_lumens=cool_lumens,
        pwm_resolution=pwm_resolution,
        min_duty=min_duty,
        gamma=gamma,
    )

    result = calculate_led_mix(target_cct, target_brightness, params)

    # Calculate Duv uncertainty from MacAdam step
    # 1-step ≈ 0.001 Duv, scales roughly linearly
    duv_uncertainty = macadam_step * 0.0011

    return ColorMixResultDerived(
        warm_duty=result.warm_duty,
        cool_duty=result.cool_duty,
        achieved_cct=result.achieved_cct,
        achieved_duv=result.achieved_duv,
        achieved_brightness=result.achieved_brightness,
        xy_derived=True,
        duv_uncertainty=duv_uncertainty,
    )
