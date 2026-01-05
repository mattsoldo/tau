# Dim-to-Warm Function Specification

## Version 1.0

---

### 1. Purpose

Define automatic color temperature adjustment based on brightness level, mimicking the behavior of incandescent dimming where lower brightness produces warmer (lower CCT) light. This creates a more natural and comfortable dimming experience.

---

### 2. Glossary

**Dim-to-Warm (DTW):** Automatic CCT adjustment that decreases color temperature as brightness decreases, simulating incandescent thermal behavior.

**Override:** A temporary manual setting that supersedes automatic or inherited values. Overrides expire based on defined conditions.

**Fixture:** A single addressable lighting device.

**Group:** A logical collection of fixtures controlled together.

**Effective Value:** The final computed value after applying inheritance, overrides, and automatic functions.

---

### 3. System Configuration

#### 3.1 Global DTW Settings

| Parameter | Type | Units | Default | Description |
|-----------|------|-------|---------|-------------|
| `dtw_enabled` | bool | — | true | System-wide DTW enable |
| `dtw_min_cct` | int | Kelvin | 1800 | CCT at minimum brightness |
| `dtw_max_cct` | int | Kelvin | 4000 | CCT at maximum brightness |
| `dtw_min_brightness` | float | 0.0–1.0 | 0.001 | Brightness floor for DTW curve |
| `dtw_curve` | enum | — | LOG | Interpolation curve type |
| `override_timeout` | int | seconds | 28800 | Override expiration (default: 8 hours) |

#### 3.2 Fixture/Group DTW Settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `dtw_ignore` | bool | false | Exempt from automatic DTW |
| `dtw_min_cct_override` | int? | null | Per-fixture/group min CCT |
| `dtw_max_cct_override` | int? | null | Per-fixture/group max CCT |

---

### 4. DTW Curve Calculation

#### 4.1 Curve Types

| Curve | Formula | Characteristic |
|-------|---------|----------------|
| `LINEAR` | Direct interpolation | Even CCT change per brightness step |
| `LOG` | Logarithmic | More CCT change at low brightness (recommended) |
| `SQUARE` | Quadratic | Gentle warm-up, aggressive at low end |
| `INCANDESCENT` | Attempt to model actual filament behavior | Most realistic |

**Recommendation:** Use `LOG` for perceptually natural dimming.

#### 4.2 Core Algorithm

```
function calculate_dtw_cct(
    brightness: float,           # 0.0–1.0
    min_cct: int,                # e.g., 1800
    max_cct: int,                # e.g., 4000
    min_brightness: float,       # e.g., 0.001
    curve: enum                  # LINEAR, LOG, SQUARE, INCANDESCENT
) -> int:
    # Clamp brightness to valid range
    if brightness <= 0:
        return min_cct
    if brightness >= 1.0:
        return max_cct
    
    # Normalize brightness to 0–1 within the effective range
    effective_brightness = clamp(brightness, min_brightness, 1.0)
    
    # Apply curve transformation
    switch curve:
        case LINEAR:
            t = effective_brightness
        
        case LOG:
            # Attempt logarithmic feel: more CCT change at low brightness
            t = log10(1 + 9 * effective_brightness) / log10(10)
        
        case SQUARE:
            t = effective_brightness * effective_brightness
        
        case INCANDESCENT:
            # attempt to model filament temperature vs power
            # CCT ∝ T, power ∝ T^4 (Stefan-Boltzmann)
            # So T ∝ power^0.25, and brightness ∝ power
            t = pow(effective_brightness, 0.25)
    
    # Interpolate CCT (note: min_cct is at LOW brightness)
    cct = round(min_cct + (max_cct - min_cct) * t)
    
    return cct
```

#### 4.3 Example Values (LOG curve, 1800K–4000K)

| Brightness | CCT |
|------------|-----|
| 100% | 4000K |
| 75% | 3760K |
| 50% | 3440K |
| 25% | 2960K |
| 10% | 2400K |
| 5% | 2140K |
| 1% | 1800K |

---

### 5. Override System

#### 5.1 Override Types

| Type | Trigger | Supersedes |
|------|---------|------------|
| `DTW_CCT` | Manual CCT change when DTW active | Automatic DTW calculation |
| `FIXTURE_GROUP` | Individual fixture control when in group | Group-level settings |
| `SCENE` | Scene recall | All automatic functions |

#### 5.2 Unified Override Structure

```
Override {
    id: uuid
    target_type: enum            # FIXTURE, GROUP
    target_id: uuid              # Fixture or group ID
    override_type: enum          # DTW_CCT, FIXTURE_GROUP, SCENE
    property: string             # "cct", "brightness", etc.
    value: any                   # The override value
    created_at: timestamp
    expires_at: timestamp        # created_at + override_timeout
    source: enum                 # USER, API, SCENE, SCHEDULE
}
```

#### 5.3 Override Creation

```
function create_override(
    target_type: enum,
    target_id: uuid,
    override_type: enum,
    property: string,
    value: any,
    timeout_seconds: int = 28800
) -> Override:
    override = Override {
        id: generate_uuid(),
        target_type: target_type,
        target_id: target_id,
        override_type: override_type,
        property: property,
        value: value,
        created_at: now(),
        expires_at: now() + timeout_seconds,
        source: determine_source()
    }
    
    store_override(override)
    return override
```

#### 5.4 Override Expiration Conditions

An override is automatically removed when ANY of these conditions is met:

| Condition | Description |
|-----------|-------------|
| Timeout | `now() > override.expires_at` |
| Power off | Target brightness set to 0 |
| Explicit cancel | User or API cancels override |
| Target deleted | Fixture or group removed from system |

```
function check_override_expiration(override: Override) -> bool:
    # Time-based expiration
    if now() > override.expires_at:
        return true
    
    # Power-off expiration
    target = get_target(override.target_type, override.target_id)
    if target.brightness == 0:
        return true
    
    return false
```

#### 5.5 Override Cancellation

```
function cancel_override(
    target_type: enum,
    target_id: uuid,
    override_type: enum,
    property: string? = null     # null = cancel all overrides of this type
) -> int:                        # Returns count of cancelled overrides
    
    query = {
        target_type: target_type,
        target_id: target_id,
        override_type: override_type
    }
    
    if property is not null:
        query.property = property
    
    overrides = find_overrides(query)
    
    for override in overrides:
        delete_override(override.id)
    
    return len(overrides)
```

---

### 6. Effective Value Resolution

#### 6.1 Priority Order (highest to lowest)

1. Active override (not expired)
2. DTW automatic calculation (if enabled and not ignored)
3. Inherited group value (for fixtures in groups)
4. Fixture default value

#### 6.2 Resolution Algorithm

```
function resolve_effective_cct(
    fixture: Fixture,
    brightness: float
) -> {cct: int, source: enum}:
    
    # 1. Check for active CCT override
    override = find_active_override(
        target_type = FIXTURE,
        target_id = fixture.id,
        property = "cct"
    )
    
    if override is not null:
        return {cct: override.value, source: OVERRIDE}
    
    # 2. Check if fixture ignores DTW
    if fixture.dtw_ignore:
        return {cct: fixture.cct, source: FIXTURE_DEFAULT}
    
    # 3. Check if fixture is in a group with DTW override
    group = get_fixture_group(fixture.id)
    if group is not null:
        group_override = find_active_override(
            target_type = GROUP,
            target_id = group.id,
            property = "cct"
        )
        
        if group_override is not null:
            return {cct: group_override.value, source: GROUP_OVERRIDE}
        
        if group.dtw_ignore:
            return {cct: group.cct, source: GROUP_DEFAULT}
    
    # 4. Apply DTW if enabled
    if system.dtw_enabled:
        # Determine effective DTW range
        min_cct = fixture.dtw_min_cct_override ?? 
                  group?.dtw_min_cct_override ?? 
                  system.dtw_min_cct
        
        max_cct = fixture.dtw_max_cct_override ?? 
                  group?.dtw_max_cct_override ?? 
                  system.dtw_max_cct
        
        cct = calculate_dtw_cct(
            brightness = brightness,
            min_cct = min_cct,
            max_cct = max_cct,
            min_brightness = system.dtw_min_brightness,
            curve = system.dtw_curve
        )
        
        return {cct: cct, source: DTW_AUTO}
    
    # 5. Fall back to fixture default
    return {cct: fixture.cct, source: FIXTURE_DEFAULT}
```

---

### 7. Control Page Behavior

#### 7.1 Brightness Change (DTW Active)

When user adjusts brightness slider and DTW is active:

```
function on_brightness_change(target, new_brightness):
    # Update brightness
    target.brightness = new_brightness
    
    # Check for power-off → clear overrides
    if new_brightness == 0:
        clear_all_overrides(target)
        return
    
    # If no CCT override active, recalculate DTW
    if not has_active_override(target, "cct"):
        result = resolve_effective_cct(target, new_brightness)
        target.cct = result.cct
        update_ui_cct_display(result.cct, result.source)
```

#### 7.2 Manual CCT Change (Creates Override)

When user manually adjusts CCT:

```
function on_cct_manual_change(target, new_cct):
    # Determine if this should create an override
    result = resolve_effective_cct(target, target.brightness)
    
    if result.source == DTW_AUTO:
        # User is overriding DTW → create override
        create_override(
            target_type = get_target_type(target),
            target_id = target.id,
            override_type = DTW_CCT,
            property = "cct",
            value = new_cct
        )
        update_ui_override_indicator(visible = true)
    else:
        # No DTW active, just set the value directly
        target.cct = new_cct
```

#### 7.3 UI Indicators

| State | Indicator | Description |
|-------|-----------|-------------|
| DTW active | Animated link icon | CCT slider follows brightness |
| DTW override | Static unlink icon + badge | Manual CCT set, can be cancelled |
| DTW ignored | Dimmed link icon | This fixture/group exempt |
| No DTW | No icon | System DTW disabled |

#### 7.4 Override Cancellation UI

```
function on_cancel_override_click(target):
    cancel_override(
        target_type = get_target_type(target),
        target_id = target.id,
        override_type = DTW_CCT,
        property = "cct"
    )
    
    # Recalculate CCT from DTW
    result = resolve_effective_cct(target, target.brightness)
    target.cct = result.cct
    update_ui_cct_display(result.cct, result.source)
    update_ui_override_indicator(visible = false)
```

---

### 8. Group and Fixture Override Interaction

#### 8.1 Inheritance Rules

| Scenario | Behavior |
|----------|----------|
| Group brightness changes | All member fixtures follow (unless fixture override) |
| Group CCT changes | Creates group DTW override; members follow |
| Fixture brightness changes | Creates fixture-over-group override for brightness |
| Fixture CCT changes | Creates fixture DTW override |
| Group turned off | Clears group AND member overrides |
| Fixture turned off | Clears fixture overrides only |

#### 8.2 Unified Override Query

```
function get_all_active_overrides(target) -> list[Override]:
    overrides = []
    
    # Get fixture-level overrides
    overrides += find_overrides(
        target_type = FIXTURE,
        target_id = target.id,
        expired = false
    )
    
    # Get group-level overrides if fixture is in group
    group = get_fixture_group(target.id)
    if group is not null:
        overrides += find_overrides(
            target_type = GROUP,
            target_id = group.id,
            expired = false
        )
    
    return overrides
```

#### 8.3 Bulk Override Clear (Power Off)

```
function on_target_power_off(target):
    if target is Group:
        # Clear group overrides
        clear_all_overrides(target)
        
        # Clear member fixture overrides
        for fixture in target.fixtures:
            clear_all_overrides(fixture)
    
    else if target is Fixture:
        clear_all_overrides(target)
```

---

### 9. Background Tasks

#### 9.1 Override Expiration Daemon

```
function override_expiration_task():
    # Run every 60 seconds
    while true:
        expired = find_overrides(
            expires_at < now()
        )
        
        for override in expired:
            delete_override(override.id)
            
            # Recalculate effective values for affected targets
            target = get_target(override.target_type, override.target_id)
            recalculate_effective_values(target)
            notify_ui_override_expired(target, override)
        
        sleep(60 seconds)
```

---

### 10. API Endpoints

#### 10.1 System DTW Configuration

```
GET  /api/system/dtw
PUT  /api/system/dtw
     Body: {dtw_enabled, dtw_min_cct, dtw_max_cct, dtw_curve, ...}
```

#### 10.2 Fixture/Group DTW Settings

```
GET  /api/fixtures/{id}/dtw
PUT  /api/fixtures/{id}/dtw
     Body: {dtw_ignore, dtw_min_cct_override, dtw_max_cct_override}

GET  /api/groups/{id}/dtw
PUT  /api/groups/{id}/dtw
     Body: {dtw_ignore, dtw_min_cct_override, dtw_max_cct_override}
```

#### 10.3 Override Management

```
GET  /api/overrides
     Query: target_type, target_id, override_type, active_only

POST /api/overrides
     Body: {target_type, target_id, override_type, property, value, timeout}

DELETE /api/overrides/{id}

DELETE /api/overrides
       Query: target_type, target_id, override_type, property
       (Bulk cancel)
```

---

### 11. Edge Cases

| Scenario | Behavior |
|----------|----------|
| DTW disabled while overrides exist | Overrides remain but become no-ops; cleared on next power cycle |
| Min CCT > Max CCT configured | Reject configuration; return error |
| Brightness at exactly 0 | Return min_cct but don't send to fixture (off is off) |
| Override timeout set to 0 | Override never expires automatically |
| Fixture removed from group while override active | Fixture override persists; group override no longer applies |
| DTW range changed while override active | Override value unchanged; may now be outside new range |
| Multiple overlapping overrides | Most recent override wins (by created_at) |

---

### 12. Integration with Mixing Algorithm

The DTW function produces a target CCT which is then passed to the Planckian Locus Tracking algorithm:

```
function apply_lighting_state(fixture, brightness):
    # 1. Resolve effective CCT (DTW or override)
    cct_result = resolve_effective_cct(fixture, brightness)
    target_cct = cct_result.cct
    
    # 2. Calculate LED channel mix
    mix_result = calculate_led_mix(
        target_cct = target_cct,
        target_brightness = brightness,
        warm_cct = fixture.warm_cct,
        cool_cct = fixture.cool_cct,
        warm_xy = fixture.warm_xy,
        cool_xy = fixture.cool_xy,
        warm_lumens = fixture.warm_lumens,
        cool_lumens = fixture.cool_lumens,
        pwm_resolution = fixture.pwm_resolution,
        gamma = fixture.gamma
    )
    
    # 3. Apply smooth transition if CCT changed significantly
    if should_smooth_transition(fixture.current_cct, target_cct):
        transition = generate_transition(
            start_cct = fixture.current_cct,
            end_cct = target_cct,
            brightness = brightness,
            transition_time = 500,  # ms
            easing = EASE_OUT
        )
        execute_transition(fixture, transition)
    else:
        # 4. Send PWM values to fixture
        send_to_fixture(fixture, mix_result.warm_duty, mix_result.cool_duty)
    
    fixture.current_cct = target_cct
    fixture.current_brightness = brightness
```

---

### 13. Validation Criteria

1. **DTW Curve Continuity:** CCT should change smoothly with no discontinuities across the brightness range
2. **Override Isolation:** Override on one fixture should not affect other fixtures in the same group
3. **Expiration Accuracy:** Overrides should expire within ±1 minute of configured timeout
4. **Power-off Clearing:** All overrides must clear synchronously with power-off command
5. **UI Sync:** Override indicator must update within 100ms of state change
6. **Round-trip Consistency:** `brightness → DTW CCT → brightness` should be idempotent