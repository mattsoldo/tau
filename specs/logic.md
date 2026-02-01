# Logic Truth Tables & Control Algorithms

NUC Lighting Controller - Version 1.0

## Composite Paddle Dimmer Logic

A "Paddle Composite" input combines one digital input (rocker switch) and one analog input (slider) into a single logical control. The digital switch controls ON/OFF state; the analog slider controls target brightness.

| Digital Pin | Analog Pin (0-10V) | Previous State | Action / Output | Explanation |
| :--- | :--- | :--- | :--- | :--- |
| OFF (0) | Any Value | Any | Turn OFF (0%) | Hard cutoff. Slider position is ignored when switch is off. |
| ON (1) | V_in (e.g., 5.0V) | OFF | Turn ON to 50% | When switched ON, light jumps/fades to current slider position immediately. |
| ON (1) | V_in changes (e.g., 5V → 8V) | ON | Update to 80% | Live dimming. While ON, light tracks the slider in real-time. |
| ON (1) | V_in changes | OFF | Stay OFF | **Critical:** If hardware reports voltage jitter while switch is OFF, light must NOT turn on. |

## Circadian Rhythm & Override Logic

The Circadian Engine runs continuously. User manual interaction triggers a "Suspension" state for that specific group.

| Current Mode | Trigger Event | New Mode | Light Behavior |
| :--- | :--- | :--- | :--- |
| Active (Auto) | User adjusts Brightness (Slider/Switch) | Suspended | Light updates to user's requested brightness. Circadian updates stop for this group. |
| Active (Auto) | User adjusts CCT (Slider) | Suspended | Light updates to user's requested CCT. Circadian updates stop for this group. |
| Suspended | Time advances (e.g., Day → Evening) | Suspended | No change. Light stays at user's manual setting regardless of time. |
| Suspended | User clicks "Resume" (UI) | Active (Auto) | Light fades immediately to the calculated brightness/CCT for the current time of day. |
| Suspended | System Reboot | Suspended | State persists. User's manual override is honored even after power loss. |
| Any | Profile assigned to group | Active (Auto) | Profile immediately hot-reloaded; lights transition to calculated values on next loop. |
| Any | Profile keyframes updated | No change | Profile cache reloaded; lights reflect new keyframes on next calculation. |

### Hot-Reload Behavior

When a circadian profile is assigned to a group or a profile's keyframes are edited:

1. The API triggers a hot-reload in the lighting controller
2. The circadian engine reloads the profile from the database
3. On the next control loop iteration (~33ms), new values are calculated and applied
4. No daemon restart is required

## Fixture Override System

The Override System provides per-fixture control that bypasses group and circadian automation. This enables users to manually set individual fixtures without affecting the automation state of other fixtures in the same group.

### Override Behavior Truth Table

| Control Action | Override Effect | Circadian | Group Multiplier | Duration |
| :--- | :--- | :--- | :--- | :--- |
| Individual fixture brightness/CCT set | Override activated | Bypassed | Bypassed | 8 hours |
| Group brightness/CCT set | All member fixture overrides cleared | Resumes | Applied | Immediate |
| Override expires (8h) | Override deactivated | Resumes | Applied | Automatic |
| Manual "Remove Override" | Override deactivated | Resumes | Applied | Immediate |

### Priority Order (Highest to Lowest)

1. **Individual Fixture Override** - When `override_active=true`, the fixture's state is used directly without any multipliers
2. **Group Control** - When a group is controlled, it clears all individual overrides for fixtures in that group
3. **Circadian Automation** - Applied to fixtures without active overrides, modified by group multipliers

### Override State Schema

Each fixture maintains override tracking:

```python
# In FixtureStateData
override_active: bool = False           # Whether override is currently active
override_expires_at: Optional[float]    # Unix timestamp for auto-expiry
override_source: Optional[str]          # 'fixture' (individual) or 'group'
```

### Effective State Calculation

The `get_effective_fixture_state()` function implements this priority:

```python
# Pseudocode
if fixture.override_active:
    if current_time >= fixture.override_expires_at:
        clear_override(fixture)  # Expired, fall through to normal logic
    else:
        return fixture.current_state  # No multipliers applied

# Normal path: apply circadian + group multipliers
effective_brightness = fixture.brightness * group.brightness * circadian.brightness
```

### Override Expiry

- **Automatic expiry**: Overrides expire after 8 hours to prevent "forgotten" fixtures from being stuck in manual mode
- **Expiry check frequency**: Every 30 seconds (900 iterations at 30 Hz control loop)
- **Expiry behavior**: When expired, the fixture silently returns to circadian/group control

## Tunable White Mixing Algorithm

How the backend translates Target Brightness (B) and Target Kelvin (K) into DMX channels Warm (W) and Cool (C).

**Variables:**
- $K_{target}$ - Desired CCT (e.g., 4000K)
- $K_{warm}$ - Fixture min CCT (e.g., 2700K)
- $K_{cool}$ - Fixture max CCT (e.g., 6500K)
- $B_{target}$ - Desired Brightness (0.0 - 1.0)

### Linear Profile (Standard)

1. Calculate Mix Factor $t$ (0.0 to 1.0):

$$t = \frac{K_{target} - K_{warm}}{K_{cool} - K_{warm}}$$

2. Calculate Channel Intensities:
   - $Cool\_Channel = B_{target} \times t$
   - $Warm\_Channel = B_{target} \times (1 - t)$

### Perceptual Profile (Constant Intensity)

Linear mixing often results in a dip in total brightness at the midpoint (50/50 mix). Perceptual mixing boosts the midpoint using a sine-based approach.

1. Calculate Mix Factor $t$ (same as above):

$$t = \frac{K_{target} - K_{warm}}{K_{cool} - K_{warm}}$$

2. Apply Trigonometric Power Correction:
   - $Cool\_Channel = B_{target} \times \sin(t \times \frac{\pi}{2})$
   - $Warm\_Channel = B_{target} \times \cos(t \times \frac{\pi}{2})$

## DMX Channel Mapping for Merged Fixtures

Standard tunable white fixtures use consecutive DMX channels (e.g., CH 1 for warm, CH 2 for cool). However, some installations have separate LED drivers for warm and cool channels that may be assigned to non-consecutive DMX addresses.

**Merged Fixture DMX Output:**

| Fixture Configuration | DMX Output |
| :--- | :--- |
| Standard (dmx_footprint=2) | Warm → `dmx_channel_start`, Cool → `dmx_channel_start + 1` |
| Merged (has secondary_dmx_channel) | Warm → `dmx_channel_start`, Cool → `secondary_dmx_channel` |

**Example:**
- Fixture with `dmx_channel_start=1`, `secondary_dmx_channel=5`
- At 50% brightness, 3500K:
  - Warm channel (CH 1): ~64 (0.5 × 0.5 × 255)
  - Cool channel (CH 5): ~64 (0.5 × 0.5 × 255)

The mixing algorithm output is the same; only the DMX address mapping differs.

## Switch Action Broadcasting and Real-Time Updates

Physical switch actions trigger WebSocket broadcasts to connected clients for responsive UI updates. This enables the frontend to reflect hardware changes without polling.

### Broadcast Trigger Conditions

| Switch Type | Action | Broadcast Timing | Throttling |
| :--- | :--- | :--- | :--- |
| Momentary | Press (toggle) | Immediate after state change | None (single event) |
| Latching | State change | Immediate after state change | None (single event) |
| Retractive | Press and release | Once at release | None (final state only) |
| Retractive | Hold (dimming) | Continuous during hold | Throttled to 100ms intervals |

### Broadcast Event Flow

1. **Switch Input Detected**: Hardware polling detects switch state change
2. **State Update Applied**: Switch handler updates fixture or group state in state manager
3. **Broadcast Triggered**: WebSocket broadcast sent to all connected clients
4. **Error Handling**: If broadcast fails, error is logged but switch handler continues

### Hold Event Throttling

During retractive switch dimming (hold events), broadcasts are throttled to prevent overwhelming WebSocket clients:

- **Throttle Interval**: 100ms minimum between broadcasts per fixture/group
- **Throttle Scope**: Independent per target (fixture or group)
- **Visual Result**: ~10 fps update rate for smooth dimming visualization
- **Implementation**: Track last broadcast timestamp per `fixture:{id}` or `group:{id}` key

### Frontend Race Condition Prevention

The frontend implements pending request tracking to avoid race conditions where WebSocket updates could overwrite user actions:

| Scenario | Frontend Behavior | Reason |
| :--- | :--- | :--- |
| User adjusts slider | Mark request as pending | Prevents WebSocket from overwriting optimistic UI update |
| API request in flight | Ignore WebSocket updates for that fixture/group | Waits for user's request to complete |
| API request completes | Clear pending flag | Allows WebSocket updates to resume |
| WebSocket arrives during grace period | Ignored | Prevents overwriting just-completed user action |

### State Update Optimization

The frontend optimizes re-renders by comparing incoming WebSocket state with current state:

```typescript
// Early return if state unchanged (avoid unnecessary re-renders)
if (
  existing.goal_brightness === newBrightness &&
  existing.goal_cct === newCct &&
  existing.is_on === newIsOn
) {
  return prev; // Same reference = no re-render
}
```

This pattern is critical during high-frequency dimming updates where multiple consecutive broadcasts may contain identical values due to throttling or state resolution timing.