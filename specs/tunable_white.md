# Planckian Locus Tracking with Duv Correction

## Algorithm Specification v1.1

---

### 1. Purpose

Calculate optimal warm and cool LED channel intensities to achieve a target correlated color temperature (CCT) while:
- Minimizing deviation from the Planckian locus (Duv)
- Maintaining perceptually constant brightness across the CCT range
- Respecting hardware constraints (min/max duty cycles)

---

### 2. Glossary

**CCT (Correlated Color Temperature):** The temperature in Kelvin of a theoretical black body radiator that most closely matches the perceived color of a light source. Lower values (2700K) appear warm/orange; higher values (6500K) appear cool/blue.

**Planckian Locus:** The curve on a chromaticity diagram representing the colors of an ideal black body radiator at various temperatures. Natural-looking white light falls on or near this curve.

**PWM Duty Cycle:** LEDs are dimmed by switching them fully on and off thousands of times per second. The duty cycle is the fraction of time the LED is on. A 50% duty cycle means the LED is on half the time, perceived as roughly half brightness. Hardware typically represents this as an integer register (0–255 for 8-bit, 0–65535 for 16-bit).

**Duv (Delta-uv):** The perpendicular distance from a light source's chromaticity to the Planckian locus, measured in CIE 1960 UCS color space. It represents the "tint" of the light:
- Duv = 0: Exactly on the Planckian locus (neutral white)
- Duv > 0: Above the locus (greenish/yellowish tint)
- Duv < 0: Below the locus (pinkish/magenta tint)

ANSI standards allow |Duv| < 0.006 for white LEDs. High-quality lighting targets |Duv| < 0.002.

**CIE 1931 xy:** A color space where chromaticity (hue and saturation) is represented as x and y coordinates, independent of brightness.

**CIE 1960 uv:** A more perceptually uniform color space used for Duv calculations. Distances in this space better correspond to perceived color differences.

---

### 3. Inputs

| Parameter | Type | Units | Description |
|-----------|------|-------|-------------|
| `target_cct` | int | Kelvin | Desired color temperature (1800–10000 typical) |
| `target_brightness` | float | 0.0–1.0 | Desired relative brightness |
| `warm_cct` | int | Kelvin | CCT of warm LED channel (e.g., 2700) |
| `cool_cct` | int | Kelvin | CCT of cool LED channel (e.g., 6500) |
| `warm_xy` | tuple(float, float) | CIE 1931 | Chromaticity coordinates of warm LED |
| `cool_xy` | tuple(float, float) | CIE 1931 | Chromaticity coordinates of cool LED |
| `warm_lumens` | int | lumens | Luminous flux of warm channel at 100% |
| `cool_lumens` | int | lumens | Luminous flux of cool channel at 100% |
| `pwm_resolution` | int | counts | Max PWM value (e.g., 255, 4095, 65535) |
| `min_duty` | int | counts | Minimum PWM duty cycle (default: 5% of resolution) |
| `gamma` | float | — | PWM-to-light gamma correction (default: 2.2) |

---

### 4. Outputs

| Parameter | Type | Units | Description |
|-----------|------|-------|-------------|
| `warm_duty` | int | counts | PWM duty cycle for warm channel (0 to pwm_resolution) |
| `cool_duty` | int | counts | PWM duty cycle for cool channel (0 to pwm_resolution) |
| `achieved_cct` | int | Kelvin | Actual CCT achieved (may differ at range limits) |
| `achieved_duv` | float | — | Distance from Planckian locus (+ = green, − = pink) |
| `achieved_brightness` | float | 0.0–1.0 | Actual relative brightness |

---

### 5. Constants

```
# Planckian locus approximation coefficients (Krystek, 1985)
# Valid for 1667K ≤ T ≤ 25000K
KRYSTEK_X = [0.244063, 0.09911e3, 2.9678e6, -4.6070e9]
KRYSTEK_Y = [-0.275, 0.44585, 2.5539, -0.7243]

# CIE 1960 UCS conversion constants
UCS_DENOM_X = -2.0
UCS_DENOM_Y = 12.0
UCS_DENOM_CONST = 3.0
```

---

### 6. Algorithm Steps

#### 6.1 Calculate Target Chromaticity on Planckian Locus

```
function planckian_xy(T: int) -> (float, float):
    # Krystek approximation
    T_float = float(T)
    x = KRYSTEK_X[0] + KRYSTEK_X[1]/T_float + KRYSTEK_X[2]/T_float² + KRYSTEK_X[3]/T_float³
    
    # y as function of x
    y = KRYSTEK_Y[0] + KRYSTEK_Y[1]*x + KRYSTEK_Y[2]*x² + KRYSTEK_Y[3]*x³
    
    return (x, y)
```

#### 6.2 Convert CIE 1931 xy to CIE 1960 uv

The Duv calculation must be done in the CIE 1960 UCS (uniform chromaticity scale):

```
function xy_to_uv(x: float, y: float) -> (float, float):
    denom = UCS_DENOM_X * x + UCS_DENOM_Y * y + UCS_DENOM_CONST
    u = 4 * x / denom
    v = 6 * y / denom
    return (u, v)
```

#### 6.3 Calculate Mixing Ratio

The mixed chromaticity lies on the line between warm and cool in xy space, weighted by relative luminous flux:

```
function calculate_mix_ratio(target_xy, warm_xy, cool_xy) -> float:
    # Solve for α where: target = α * cool + (1-α) * warm
    # Using x-coordinate (y would give same result for collinear points)
    
    dx = cool_xy.x - warm_xy.x
    if abs(dx) < 1e-9:
        # LEDs have same x-coordinate, use y instead
        dy = cool_xy.y - warm_xy.y
        α = (target_xy.y - warm_xy.y) / dy
    else:
        α = (target_xy.x - warm_xy.x) / dx
    
    # Clamp to valid range
    α = clamp(α, 0.0, 1.0)
    
    return α
```

#### 6.4 Apply Luminous Flux Compensation

Raw mixing ratio assumes equal brightness; compensate for different LED efficacies:

```
function flux_compensated_duties(
    α: float, 
    target_brightness: float, 
    warm_lumens: int, 
    cool_lumens: int
) -> (float, float):
    # Relative contribution each channel needs to make
    warm_contribution = (1 - α)
    cool_contribution = α
    
    # Total lumens at full output
    total_lumens = warm_lumens + cool_lumens
    
    # Scale factor for target brightness
    # Normalize so brightness=1.0 gives maximum output at current CCT
    warm_duty_linear = warm_contribution * target_brightness
    cool_duty_linear = cool_contribution * target_brightness
    
    # Normalize by luminous flux to maintain constant perceived brightness
    warm_duty_linear = warm_duty_linear * (float(total_lumens) / (2.0 * warm_lumens))
    cool_duty_linear = cool_duty_linear * (float(total_lumens) / (2.0 * cool_lumens))
    
    return (warm_duty_linear, cool_duty_linear)
```

#### 6.5 Apply Gamma Correction and Quantize

Convert linear light output to PWM duty cycle and quantize to integer:

```
function apply_gamma_and_quantize(
    duty_linear: float, 
    gamma: float, 
    pwm_resolution: int
) -> int:
    # Inverse gamma: duty_pwm^gamma = duty_linear
    duty_normalized = pow(duty_linear, 1.0 / gamma)
    
    # Quantize to integer PWM counts
    duty_int = round(duty_normalized * pwm_resolution)
    
    return duty_int
```

#### 6.6 Apply Hardware Constraints

```
function apply_constraints(
    warm_duty: int, 
    cool_duty: int, 
    min_duty: int, 
    pwm_resolution: int
) -> (int, int):
    # If a channel is below minimum but non-zero, floor it
    if 0 < warm_duty < min_duty:
        warm_duty = min_duty
    if 0 < cool_duty < min_duty:
        cool_duty = min_duty
    
    # Clamp to max
    warm_duty = min(warm_duty, pwm_resolution)
    cool_duty = min(cool_duty, pwm_resolution)
    
    return (warm_duty, cool_duty)
```

#### 6.7 Calculate Achieved Duv

```
function calculate_duv(achieved_xy, achieved_cct: int) -> float:
    # Get the Planckian reference point for this CCT
    planck_xy = planckian_xy(achieved_cct)
    
    # Convert both to CIE 1960 uv
    achieved_uv = xy_to_uv(achieved_xy.x, achieved_xy.y)
    planck_uv = xy_to_uv(planck_xy.x, planck_xy.y)
    
    # Euclidean distance in uv space
    du = achieved_uv.u - planck_uv.u
    dv = achieved_uv.v - planck_uv.v
    distance = sqrt(du² + dv²)
    
    # Sign convention: positive = above locus (greenish), negative = below (pinkish)
    if achieved_uv.v > planck_uv.v:
        duv = distance
    else:
        duv = -distance
    
    return duv
```

#### 6.8 Calculate Achieved CCT from Mixed xy

For verification, calculate the CCT of the actual mixed output using McCamy's approximation:

```
function xy_to_cct(x: float, y: float) -> int:
    # McCamy's formula
    n = (x - 0.3320) / (0.1858 - y)
    cct = 449 * n³ + 3525 * n² + 6823.3 * n + 5520.33
    return round(cct)
```

---

### 7. Main Algorithm

```
function calculate_led_mix(
    target_cct: int,
    target_brightness: float,
    warm_cct: int,
    cool_cct: int,
    warm_xy: (float, float),
    cool_xy: (float, float),
    warm_lumens: int,
    cool_lumens: int,
    pwm_resolution: int = 65535,
    min_duty: int = 3277,          # ~5% of 65535
    gamma: float = 2.2
) -> {
    warm_duty: int,
    cool_duty: int,
    achieved_cct: int,
    achieved_duv: float,
    achieved_brightness: float
}:
    # 1. Clamp target CCT to achievable range
    effective_cct = clamp(target_cct, warm_cct, cool_cct)
    
    # 2. Get target chromaticity on Planckian locus
    target_xy = planckian_xy(effective_cct)
    
    # 3. Calculate mixing ratio
    α = calculate_mix_ratio(target_xy, warm_xy, cool_xy)
    
    # 4. Calculate flux-compensated linear duties
    (warm_linear, cool_linear) = flux_compensated_duties(
        α, target_brightness, warm_lumens, cool_lumens
    )
    
    # 5. Apply gamma correction and quantize to integers
    warm_duty = apply_gamma_and_quantize(warm_linear, gamma, pwm_resolution)
    cool_duty = apply_gamma_and_quantize(cool_linear, gamma, pwm_resolution)
    
    # 6. Apply hardware constraints
    (warm_duty, cool_duty) = apply_constraints(
        warm_duty, cool_duty, min_duty, pwm_resolution
    )
    
    # 7. Calculate achieved values for verification
    # Actual mixed chromaticity (weighted by luminous flux)
    warm_flux = warm_lumens * pow(float(warm_duty) / pwm_resolution, gamma)
    cool_flux = cool_lumens * pow(float(cool_duty) / pwm_resolution, gamma)
    total_flux = warm_flux + cool_flux
    
    if total_flux > 0:
        achieved_x = (warm_xy.x * warm_flux + cool_xy.x * cool_flux) / total_flux
        achieved_y = (warm_xy.y * warm_flux + cool_xy.y * cool_flux) / total_flux
        achieved_cct = xy_to_cct(achieved_x, achieved_y)
        achieved_duv = calculate_duv((achieved_x, achieved_y), achieved_cct)
        achieved_brightness = total_flux / float(warm_lumens + cool_lumens)
    else:
        achieved_cct = 0
        achieved_duv = 0.0
        achieved_brightness = 0.0
    
    return {
        warm_duty: warm_duty,
        cool_duty: cool_duty,
        achieved_cct: achieved_cct,
        achieved_duv: achieved_duv,
        achieved_brightness: achieved_brightness
    }
```

---

### 8. Edge Cases

| Condition | Behavior |
|-----------|----------|
| `target_cct < warm_cct` | Clamp to warm_cct, warm channel only |
| `target_cct > cool_cct` | Clamp to cool_cct, cool channel only |
| `target_brightness = 0` | Return both duties = 0 |
| `warm_xy ≈ cool_xy` | LEDs too similar; return error or 50/50 mix |
| Computed duty exceeds pwm_resolution | Clamp and recalculate achieved values |
| Quantization pushes duty below min_duty | Floor to min_duty or zero |

---

### 9. Validation Criteria

A correct implementation should satisfy:

1. **Monotonicity:** Increasing `target_cct` should increase `cool_duty` / decrease `warm_duty`
2. **Boundary conditions:** At `target_cct = warm_cct`, cool_duty = 0; at `target_cct = cool_cct`, warm_duty = 0
3. **Brightness consistency:** `achieved_brightness` should be within ±5% of `target_brightness` across the CCT range
4. **Duv bounds:** For typical LED pairs, |achieved_duv| should be < 0.006 (ANSI tolerance)
5. **Integer bounds:** Output duties must satisfy 0 ≤ duty ≤ pwm_resolution

---

### 10. Optional Enhancements

- **Thermal compensation:** Accept LED junction temperature as input; apply chromaticity shift coefficients
- **LUT-based gamma:** Replace power function with measured lookup table for more accurate dimming
- **Duv targeting:** Accept non-zero Duv target for deliberate warm/cool tint preference
- **Smooth transitions:** Apply slew rate limiting when CCT changes to avoid visible jumps
- **Fixed-point math:** For embedded systems, convert all float operations to fixed-point using scaled integers

Appendix A: Fallback Mode When Chromaticity Data is Unavailable
A.1 Overview
When CIE xy chromaticity coordinates are not available from manufacturer datasheets, the algorithm can derive approximate values from CCT using the Planckian locus. This fallback assumes both LED channels sit exactly on the black body curve (Duv = 0).

A.2 Modified Inputs
ParameterTypeRequiredDescriptionwarm_cctint✅CCT of warm LED channelcool_cctint✅CCT of cool LED channelwarm_xytuple(float, float)❌If omitted, derived from warm_cctcool_xytuple(float, float)❌If omitted, derived from cool_cctwarm_lumensint✅Luminous flux of warm channel at 100%cool_lumensint✅Luminous flux of cool channel at 100%warm_macadam_stepint❌Optional: binning tolerance (default: 7)cool_macadam_stepint❌Optional: binning tolerance (default: 7)

A.3 Deriving xy from CCT
When warm_xy or cool_xy is not provided, derive it using the Planckian locus approximation:
function derive_xy_from_cct(cct: int) -> (float, float):
    return planckian_xy(cct)  # Uses Krystek formula from Section 6.1

A.4 Modified Initialization
Add this preprocessing step at the start of calculate_led_mix:
function resolve_chromaticity_inputs(
    warm_cct: int,
    cool_cct: int,
    warm_xy: optional (float, float),
    cool_xy: optional (float, float)
) -> {
    warm_xy: (float, float),
    cool_xy: (float, float),
    xy_derived: bool
}:
    xy_derived = false
    
    if warm_xy is null:
        warm_xy = planckian_xy(warm_cct)
        xy_derived = true
    
    if cool_xy is null:
        cool_xy = planckian_xy(cool_cct)
        xy_derived = true
    
    return {
        warm_xy: warm_xy,
        cool_xy: cool_xy,
        xy_derived: xy_derived
    }

A.5 Additional Output
When operating in fallback mode, add an uncertainty indicator to the output:
ParameterTypeDescriptionxy_derivedboolTrue if any xy was derived from CCTduv_uncertaintyfloatEstimated ± error on achieved_duv
Calculate uncertainty from MacAdam step if provided:
function estimate_duv_uncertainty(
    warm_macadam_step: int,
    cool_macadam_step: int,
    xy_derived: bool
) -> float:
    if not xy_derived:
        return 0.0
    
    # Approximate Duv uncertainty per MacAdam step: ~0.0011
    # Use worst-case (larger) of the two channels
    worst_step = max(warm_macadam_step, cool_macadam_step)
    
    # 1-step ≈ 0.001 Duv, scales roughly linearly
    return worst_step * 0.0011

A.6 Accuracy Expectations
| Scenario | Expected |Duv| Error | Notes |
|----------|----------------------|-------|
| Both xy from datasheet | < 0.001 | Limited by measurement precision |
| Derived xy, 3-step LEDs | < 0.004 | Typical quality tunable white |
| Derived xy, 5-step LEDs | < 0.006 | At ANSI tolerance boundary |
| Derived xy, 7-step LEDs | < 0.008 | May have visible tint shift |
| Derived xy, unknown binning | Unknown | Assume worst case (7-step) |

A.7 Limitations of Fallback Mode

Assumes zero Duv: Real LEDs rarely sit exactly on the Planckian locus. Most have slight positive or negative tint.
Ignores phosphor variation: Different phosphor chemistries with the same CCT can have different xy coordinates.
No thermal compensation: Chromaticity shifts with temperature. Datasheet values at Tc=85°C may differ from cold-start values.
Mid-range accuracy degrades: Error compounds when mixing. If both endpoints are off-locus in the same direction, the blend could have double the Duv error.


A.8 Recommendations
Data AvailableRecommendationFull xy from datasheet at TcUse exact values. Best accuracy.CCT + MacAdam step onlyUse fallback with uncertainty output. Acceptable for most applications.CCT only, no binning infoUse fallback but assume 7-step tolerance. Flag output as approximate.NothingRequire user input. Do not guess CCT.
For production systems where color consistency matters, always prefer measured chromaticity data from manufacturer datasheets or direct measurement of sample fixtures.