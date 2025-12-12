Below is the **complete, concise, engineering-ready Product Specification** for your controller software.
It focuses **only on functionality**, not architecture, consistent with your instructions.

---

# **Product Specification: Lighting Control Software (Functional Requirements)**

**Version 1.0**

---

# **1. Overview**

The system is a Linux-based lighting controller running on a NUC.
It reads inputs from a **LabJack U3-HV**, processes high-level lighting logic, and outputs DMX512 via **OLA** through a USB-to-DMX interface.

Primary capabilities:

* Read 0–10V dimmers, retractive switches, rotary controls, and paddle dimmers
* Control standard, dim-to-warm, and tunable white fixtures
* Support scenes, groups, and circadian rhythms
* Provide a modern web UI for configuration and control
* Maintain persistent logical lighting state

---

# **2. Hardware Interfaces**

## 2.1 OLA / DMX

* System controls **one DMX universe** (future multi-universe support planned).
* DMX output defaults to OLA’s refresh rate; a config option allows user override.
* RDM device discovery is **invoked only through a UI link** to OLA’s built-in interface.
* No auto-polling in V1; periodic scanning is phase 2.

## 2.2 DMX Output Device

* Software uses OLA to recognize and communicate with the USB-to-DMX adapter.
* If the adapter is disconnected, system displays an alert and enters a wait/retry state.

## 2.3 LabJack U3-LV

* Reads unlimited (logical) number of analog and digital inputs as configured.
* System must detect disconnection and alert the user; continues software control until reconnection.
* Polls for reconnection until restored.

---

# **3. Input Devices and Behavior**

## 3.1 Supported Input Types

For each LabJack channel, users may assign:

1. **Retractive switch** (momentary up/down)
2. **Absolute rotary dimmer (0–10V)**
3. **Relative rotary encoder (infinite encoder)**
4. **Decora-style paddle dimmer (0–10V analog)**
5. **Simple on/off switch**

Users may upload a photo for each input to aid identification.

## 3.2 Per-Input Configuration

Each input must support:

* Assigned type (from above list)
* Assigned target: **fixture** or **group**
* Input mode:

  * Retractive: tap, hold, dim
  * Simple on/off
  * Absolute dimmer
  * Relative dimmer
  * Paddle dimmer
* Tap timing thresholds:

  * Default: 500 ms
  * User-adjustable between 200–900 ms
* Dimming speed:

  * Defined as **seconds required to dim from 100% → 0%**
* Ability to trigger:

  * Single-tap actions
  * Double-tap actions (e.g., activate scene)
  * Triple-tap actions (e.g., activate another scene)

## 3.3 Retractive Switch Default Behavior

* If light is OFF:

  * Tap → ON to full brightness
  * Hold → ramp up from 0% until released
* If light is ON:

  * Hold → ramp down to 0% until released
  * Tap → OFF
* Dimming follows the assigned **dimming curve** (linear/log) and **color curve** for associated fixture(s).

---

# **4. Fixture Model**

## 4.1 Fixture Types

The system supports three categories:

1. **Standard dimmable**

   * 1 DMX channel
   * Brightness only

2. **Fixed CCT / Dim-to-Warm (single channel)**

   * 1 DMX channel
   * Brightness only
   * CCT is fixed (e.g., 2700K)
   * Dim-to-warm handled internally if fixture is designed that way (not software-controlled)

3. **Tunable white (TW)**

   * 2 DMX channels: warm level, cool level
   * Software controls brightness *and* CCT
   * Software must convert brightness + target CCT → warm/cool channel intensities

Future expansion (RGB, RGBW) will use the same fixture abstraction.

## 4.2 Fixture Parameters

Each fixture has:

* Name
* Type (from above)
* DMX channel or channel pair
* CCT range (for tunable white)
* Assigned dimming curve (linear, log, or inherited)
* Assigned color curve (for TW)
* Optional lumen output

## 4.3 Universal Fixture API

All fixtures must support:

```
set_brightness(value)
set_cct(kelvin)          # if applicable
get_dmx_values()         # returns one or two DMX channel values
```

---

# **5. Color Curves (for Tunable White Fixtures)**

## 5.1 Curve Definition

A color curve includes:

* Warm channel CCT (Kelvin)
* Cool channel CCT (Kelvin)
* Linear interpolation between endpoints
* Perceptual correction (gamma-like curve)

## 5.2 Curve Assignment

Color curves can be assigned:

* Globally
* To a group
* To an individual fixture

Lower-level assignment overrides higher-level.

---

# **6. Dimming Curves**

## 6.1 Curve Types (V1)

* Linear
* Logarithmic

## 6.2 Curve Assignment

Users may define named curves and assign them:

* Globally
* Per group
* Per fixture

Lower-level overrides higher-level.

---

# **7. Groups**

## 7.1 Structure

* Arbitrary number of groups
* Groups may contain fixtures or other groups
* Up to 4 levels of nesting allowed

## 7.2 Group Behavior

* Turning a group ON:

  * Either restores **last known state** OR
  * Applies **default brightness/CCT** (configurable per group)
* Turning a group OFF sends OFF state to all members
* Group-level dimming and CCT controls must propagate to fixtures

---

# **8. Scenes**

## 8.1 Definition

A scene includes:

* Name
* Target: a fixture or a group
* For each fixture within scope:

  * Brightness
  * CCT (if applicable)

## 8.2 Behavior

* Invoking a scene sets all associated fixture states
* No fade times in V1
* System tracks how far the current state deviates from the scene definition

## 8.3 Scene Deviation Indicator

Displayed both at **fixture** and **group** level.
Qualitative deviation levels (with default thresholds):

* Slight difference
* Moderate difference
* Major difference

Displayed as color-intensity fade levels (UI responsibility).

---

# **9. Circadian Rhythms**

## 9.1 Definition

A circadian profile applies to **groups** and defines:

* Multiple phases across the day (e.g., Wake, Day, Evening, Night)
* Brightness and CCT behavior within each phase
* Smooth continuous interpolation between phase values

## 9.2 System Behavior

* Circadian output continuously updates lights in assigned groups
* Manual user adjustments **suspend** circadian operation for that group/fixture
* UI provides **Play/Pause** control for circadian per group
* Only the interacted-with group is suspended; others continue normally

---

# **10. System State & Persistence**

## 10.1 Logical State

The system must maintain high-level logical state for:

* Brightness
* CCT
* Curve assignments
* Scenes
* Groups & nesting
* Inputs & their configuration
* Circadian enable/disable state

## 10.2 Persistence

* Logical state persists across reboot
* DMX output is *not* persisted (stateless)
* Storage format is left to implementation (JSON, SQLite, etc.)

---

# **11. Error Handling & Logging**

## 11.1 Hardware Faults

If the system detects:

* OLA daemon failure → attempt restart; alert if restart fails
* USB DMX interface removed → alert user; wait for reconnection
* LabJack disconnected → alert user; continue software control; poll for reconnection

## 11.2 Logging

* Log all system events and user actions
* Maintain **7 days** of logs, automatically pruned
* Logs are available in the UI and downloadable

## 11.3 Alerts

Two types:

1. **Critical alerts (blocking):**

   * Dismissible popup or banner
   * Required when hardware required for operation is missing or malfunctioning
2. **Non-critical warnings:**

   * Colored status bar (“soap bar”)

---

# **12. Web User Interface (UI)**

## 12.1 General Requirements

* No authentication in V1
* Modern minimal UI
* Supports light/dark mode
* Responsive on desktop, tablet, and mobile
* Optional **Developer Mode** for diagnostics (DMX values, raw inputs, etc.)

## 12.2 Default Screen

Shows all groups:

* Group ON/OFF toggle
* Group scenes
* Expand to view fixtures

## 12.3 Fixture Controls

* Standard fixture: ON/OFF
* Dimmable fixture: ON/OFF + brightness slider
* Tunable white: brightness slider + CCT slider
* Sliders update continuously
* Display real-time target values as indicators above/within sliders

## 12.4 Device Discovery

* UI includes link to OLA-provided RDM/DMX device discovery page
* Local device discovery UI will be implemented in phase 2

---

# **13. Phase 2 Features (Not Included in V1)**

Document placeholders, not required now:

* Spline-based multi-point CCT curves
* Automatic RDM polling
* Multi-universe DMX support
* Advanced scene transitions (fade times, curves)
* Per-fixture circadian profiles
* Custom dim/CCT curve editor

---

