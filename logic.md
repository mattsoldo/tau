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