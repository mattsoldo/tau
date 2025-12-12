# Product Requirements Document (PRD)
## Lighting Control Software – v1

---

## 1. Overview

This document defines the functional requirements for a lighting control system running on a Linux-based NUC.  
The system reads physical inputs via a **LabJack U3-HV**, maintains high-level logical lighting state, and outputs **DMX512** via **OLA** and a USB-to-DMX adapter.

The system supports:
- Standard dimmable, dim-to-warm, and tunable white fixtures
- Physical switches and dimmers mapped to fixtures or groups
- Scenes and circadian lighting programs
- A modern web-based user interface
- Persistent state across restarts

This document describes **what the system does**, not how it is implemented.

---

## 2. Core Concepts

### 2.1 Fixture Models vs Fixtures

- **Fixture Models** define the electrical and photometric behavior of a light.
- **Fixtures** are physical instances of a fixture model installed in the system.

Fixture models define:
- Fixture type
- DMX footprint
- CCT limits
- Mixing behavior

Fixtures:
- Reference a single fixture model
- Define only name and DMX channel start
- Do **not** override model behavior

All fixtures inherit behavior exclusively from their fixture model.

---

## 3. Hardware & Protocol Interfaces

### 3.1 DMX / OLA

- The system controls **one DMX universe**.
- DMX output uses OLA’s default refresh rate.
- A configuration option allows overriding the refresh rate.
- RDM discovery is initiated only by user action via a link to the OLA web interface.
- Automatic or periodic RDM polling is out of scope for v1.

### 3.2 USB-to-DMX Adapter

- The system must detect presence of the DMX adapter.
- If disconnected:
  - A blocking alert is shown
  - The system waits and retries until reconnection

### 3.3 LabJack U3-UV

- The system supports an arbitrary number of inputs.
- If the LabJack disconnects:
  - The system alerts the user
  - Software-based control remains available
  - The system polls for reconnection

---

## 4. Fixture Models

### 4.1 Supported Fixture Types

Fixture models define one of the following types:

1. **Simple Dimmable**
   - 1 DMX channel
   - Brightness only

2. **Dim-to-Warm**
   - 1 DMX channel
   - Brightness only
   - Warm shift behavior is intrinsic to the fixture hardware

3. **Tunable White**
   - 2 DMX channels (warm, cool)
   - Software controls brightness and CCT

4. **Non-Dimmable**
   - On/off only

### 4.2 DMX Footprint

- Each fixture model defines a DMX footprint.
- The system must prevent overlapping DMX channel assignments.
- Fixture creation must validate channel availability based on footprint.

### 4.3 Mixing Type

Fixture models define a **mixing type**:
- Linear
- Perceptual
- Logarithmic
- Custom

Mixing type determines how warm and cool channel intensities are combined perceptually.  
Mixing type is fixed at the model level.

---

## 5. Fixtures

Each fixture defines:
- Name
- Fixture model reference
- DMX starting channel

Fixtures do not override:
- Mixing behavior
- Dimming behavior
- CCT limits

---

## 6. Color and Dimming Curves

### 6.1 Dimming Curves

- Users define named dimming curves.
- Supported curve types in v1:
  - Linear
  - Logarithmic
- Curves may be assigned:
  - Globally
  - Per group
  - Per fixture
- Lower-level assignments override higher-level ones.

### 6.2 Color Curves (Tunable White)

Color curves define how brightness and CCT are translated into warm/cool channel values.

Each color curve includes:
- Warm channel CCT (Kelvin)
- Cool channel CCT (Kelvin)
- Linear interpolation between endpoints
- Perceptual correction

Color curves may be assigned:
- Globally
- Per group
- Per fixture

Lower-level assignments override higher-level ones.

---

## 7. Groups

### 7.1 Structure

- Groups may contain fixtures and/or other groups.
- Group nesting is supported up to **4 levels**.
- A fixture may belong to multiple groups.

### 7.2 Group Behavior

- Turning a group ON:
  - Restores last known state, or
  - Applies a configured default brightness and CCT
- Turning a group OFF turns off all member fixtures.
- Group-level controls propagate to member fixtures.

---

## 8. Scenes

### 8.1 Definition

A scene:
- Has a name
- May be scoped to a group
- Defines per-fixture target values:
  - Brightness
  - CCT (if applicable)

Scenes do not store group-level values.

### 8.2 Behavior

- Activating a scene sets all defined fixture values.
- Scenes do not include fade times in v1.

### 8.3 Scene Deviation Tracking

- The system tracks how far current fixture state differs from the active scene.
- Deviation is displayed:
  - At the fixture level
  - At the group level
- Deviation is qualitative:
  - Slight difference
  - Moderate difference
  - Major difference
- UI uses visual intensity or color fade to represent deviation.

---

## 9. Input Devices

### 9.1 Switch Models vs Switches

- **Switch Models** define hardware behavior.
- **Switches** are physical instances wired to LabJack pins.

Switch model properties (non-overridable):
- Input type
- Debounce timing
- Default dimming curve
- Required pin type (analog/digital)

Switch instances define:
- Physical LabJack pin mapping
- Target fixture or group

Each switch targets **exactly one** fixture or group.

### 9.2 Supported Input Types

- Retractive switch
- Absolute rotary (0–10V)
- Relative rotary (infinite encoder)
- Decora-style paddle dimmer (0–10V)
- Simple on/off switch

Users may upload a reference photo per switch.

---

## 10. Input Behavior

### 10.1 Retractive Switch Default Mode

- Light OFF:
  - Tap → ON at full brightness
  - Hold → ramp up from 0%
- Light ON:
  - Hold → ramp down to 0%
  - Tap → OFF

### 10.2 Tap Detection

- Default tap window: 500 ms
- User-configurable range: 200–900 ms
- Supports single, double, and triple tap actions

### 10.3 Dimming Speed

- Defined as time (seconds) to transition from 100% → 0%.

---

## 11. Circadian Lighting

### 11.1 Circadian Profiles

Circadian profiles:
- Define brightness and CCT over time
- Use time-based curve points
- Support interpolation types (e.g., linear, cosine, step)

### 11.2 Assignment & Behavior

- Circadian profiles are assigned **per group**.
- Lighting updates continuously.
- Manual user interaction suspends circadian control:
  - Only for the affected fixture or group
- UI provides play/pause control per group.

---

## 12. Runtime State & Persistence

### 12.1 Logical State

The system maintains logical state for:
- Fixture brightness, CCT, and on/off status
- Group circadian suspension
- Last active scene per group

### 12.2 Persistence

- Logical state is persisted to disk.
- State is restored on startup.
- DMX output values themselves are not persisted.

---

## 13. Error Handling & Logging

### 13.1 Error Conditions

- LabJack disconnected
- USB-DMX adapter removed
- OLA daemon stopped

System behavior:
- Attempt automatic recovery where possible
- Display alerts to the user
- Continue operating where safe

### 13.2 Alerts

- Blocking alerts: dismissible notifications
- Non-blocking warnings: colored status bar

### 13.3 Logging

- Log all system events and user actions
- Retain logs for 7 days
- Logs are viewable and downloadable via the UI

---

## 14. Web User Interface

### 14.1 General

- No authentication in v1
- Modern, minimal design
- Light and dark modes
- Responsive on desktop, tablet, and mobile

### 14.2 Default View

- Displays all groups
- Group on/off control
- Scene selection
- Expandable to show fixtures

### 14.3 Fixture Controls

- Non-dimmable: on/off
- Dimmable: on/off + brightness slider
- Tunable white: brightness + CCT sliders
- Sliders update continuously
- Value indicators show current targets

### 14.4 Developer Mode

- Optional
- Exposes diagnostics such as DMX values and input state

---

## 15. Out of Scope (Phase 2)

- Multi-universe DMX
- Spline-based color curves
- Automatic RDM polling
- Scene transitions with fade timing
- RGB / RGBW fixtures
- Authentication and user roles

---

## End of Document
