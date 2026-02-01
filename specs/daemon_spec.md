Control Daemon Specification (v1)

Hardware + real-time control layer

This document specifies the functionality and external interface for the Control Daemon. The daemon is responsible for:
	•	Reading physical inputs via LabJack U3-HV
	•	Running input state machines (tap/hold/double-tap/etc.)
	•	Maintaining and persisting logical runtime state (fixtures/groups)
	•	Streaming DMX output continuously via OLA
	•	Providing a local HTTP API for coordination with the Next.js web app
	•	Logging events and exposing health/status

The daemon is intended to be implemented in Python.

⸻

1. Scope and Non-Goals

In scope
	•	Input polling, debouncing, and state machines
	•	Applying control actions (set fixture/group, activate scene, circadian pause/resume)
	•	Persisting logical state (fixture_state, group_state) and ensuring it survives restart
	•	DMX output generation and streaming via OLA
	•	Dependency monitoring and user-visible alerts/events
	•	Local HTTP API for the web app

Out of scope (v1)
	•	Building a user-facing discovery UX (use OLA UI link)
	•	Multi-universe DMX
	•	Automatic RDM polling (phase 2)
	•	RGB/RGBW fixture math
	•	Authentication/authorization (daemon listens on localhost only)

⸻

2. Runtime Model

2.1 Process
	•	Single long-running daemon process, started on boot (e.g., systemd).

2.2 Primary loops (conceptual)
	1.	Input Loop
	•	Poll LabJack inputs at a fixed cadence
	•	Debounce and derive events (press/release/tap/double-tap/triple-tap/hold)
	•	Map events to actions (fixture/group control; scene activation)
	2.	State/Command Loop
	•	Apply control commands from the local HTTP API
	•	Update DB state tables immediately
	3.	DMX Output Loop
	•	Continuously compute DMX channel values from current logical state
	•	Send updates via OLA (refresh rate: OLA default; allow config override)
	4.	Health/Watchdog Loop
	•	Detect LabJack disconnect/reconnect
	•	Detect OLA down/restart attempts
	•	Detect USB-DMX adapter missing
	•	Emit alert events + log entries

⸻

3. Configuration

3.1 Config sources
	•	Environment variables and/or a config file on disk.
	•	Daemon exposes current effective config via API.

3.2 Required config keys
	•	HTTP_LISTEN_ADDR (default 127.0.0.1)
	•	HTTP_PORT (default 8787)
	•	DB_URL (SQLite/Postgres; implementation choice)
	•	OLA_UNIVERSE (default 1)
	•	DMX_REFRESH_OVERRIDE_HZ (optional; if unset, use OLA default)
	•	INPUT_POLL_HZ (default e.g., 100 Hz)
	•	LOG_RETENTION_DAYS (fixed to 7)

⸻

4. Dependencies

4.1 OLA
	•	Daemon uses OLA client library (Python) to send DMX.
	•	Daemon must detect OLA failure:
	•	Attempt restart (how is implementation-defined)
	•	If restart fails, surface a blocking alert

4.2 LabJack U3-HV
	•	Daemon reads configured pins (analog and/or digital) for each switch instance.
	•	LabJack connection is optional - daemon starts successfully even if not connected.
	•	On disconnect or initial startup without hardware:
	•	Surface alert
	•	Continue software control via API
	•	Automatically poll for (re)connect every 10 seconds via health check loop
	•	When device is connected, automatically initialize and resume hardware control
	•	Note: Requires LabJack Exodriver library and tau user in 'adm' group for USB access

4.3 USB-to-DMX adapter
	•	Treated as an OLA dependency.
	•	OLA connection is optional - daemon starts successfully even if not connected.
	•	If missing or on initial startup without hardware:
	•	Surface alert instructing user to reconnect
	•	Continue accepting software commands and updating state
	•	Automatically poll for (re)connect every 10 seconds via health check loop
	•	When OLA/ENTTEC device is connected, automatically initialize and resume DMX output

4.4 Raspberry Pi GPIO

**Platform Detection:**
	•	On startup, daemon checks `/proc/cpuinfo` and `/sys/firmware/devicetree/base/model`
	•	Supported models: Raspberry Pi 4 Model B, Raspberry Pi 5
	•	Detection result is cached and exposed via `/api/gpio/platform` endpoint

**Library:**
	•	Uses `gpiozero` library for hardware abstraction
	•	`gpiozero` handles differences between Pi 4 (BCM2711) and Pi 5 (RP1 chip) automatically

**Initialization:**
	•	GPIO pins are configured on daemon startup based on switch definitions
	•	Each pin configured as input with specified pull resistor
	•	Edge detection enabled for interrupt-based input (vs polling)

**Pin Numbering:**
	•	Internal storage uses BCM numbering (e.g., GPIO17 = BCM 17)
	•	API accepts and returns BCM numbers
	•	UI displays both physical pin number and BCM number

**Available GPIO Pins (BCM):**

The following BCM pins are available for switch input:
	•	4, 5, 6, 12, 13, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27

**Disabled Pins (Special Functions):**

| BCM | Function | Reason |
|-----|----------|--------|
| 0, 1 | I2C (ID EEPROM) | Reserved for HAT detection |
| 2, 3 | I2C1 (SDA/SCL) | Common peripheral bus |
| 7, 8, 9, 10, 11 | SPI0 | SPI peripheral |
| 14, 15 | UART | Serial console |

**Mock Mode:**
	•	When `GPIO_MOCK=true` or not running on Pi, GPIO inputs are simulated
	•	Mock mode useful for development and testing on non-Pi systems

⸻

5. DB Interaction (Schema-aligned)

The daemon is responsible for keeping the following tables current:
	•	fixture_state
	•	group_state

The daemon may read configuration data from:
	•	fixture_models, fixtures
	•	groups, group_fixtures, group_hierarchy
	•	switch_models, switches
	•	scenes, scene_values
	•	circadian_profiles

5.1 Startup behavior

On startup:
	1.	Load fixtures, models, groups, hierarchy, switches, scenes, circadian profiles.
	2.	Load persisted runtime state from fixture_state / group_state.
	3.	If state rows are missing for known fixtures/groups, create defaults.
	4.	Begin loops.

5.2 Persistence guarantees
	•	Any state change applied via input or API must be persisted immediately.

5.3 Group Sleep Lock Configuration

Groups may have sleep lock settings configured:
	•	`sleep_lock_enabled` (boolean): Whether sleep lock is active for this group
	•	`sleep_lock_start_time` (string, HH:MM): Start of lock period
	•	`sleep_lock_end_time` (string, HH:MM): End of lock period
	•	`sleep_lock_unlock_duration_minutes` (integer, 0-60): How long controls stay unlocked after gesture

The daemon computes `sleep_lock_active` dynamically based on current server time and configured time window. This is returned in group API responses but not stored.

⸻

6. Lighting Math and DMX Output Rules

6.1 Common
	•	Brightness is represented as percent (0–100) in API; stored as integer in fixture_state.current_brightness.
	•	CCT is represented as Kelvin; stored as integer in fixture_state.current_cct.
	•	DMX values are 0–255 per channel.

6.2 Fixture types

The fixture behavior is dictated by fixture_models.type and dmx_footprint.

6.2.1 simple_dimmable / dim_to_warm (1 channel)
	•	Output DMX value derived from brightness.
	•	If is_on=false, output must be 0.

6.2.2 tunable_white (2 channels: warm + cool)
	•	Inputs: brightness percent + target CCT Kelvin.
	•	Clamp target CCT to model [cct_min_kelvin, cct_max_kelvin].
	•	Convert (brightness, CCT) → (warm_intensity, cool_intensity) using mixing_type.
	•	Apply perceptual correction if mixing type implies it.
	•	If is_on=false, both channels output 0.

6.3 Mixing type behavior
	•	linear: linear blend based on CCT position in range.
	•	perceptual: blend uses gamma/perceptual curve (exact gamma is implementation-defined but must be consistent).
	•	logarithmic: blend uses log-like curve.
	•	custom: placeholder for phase 2.

6.4 DMX addressing
	•	Each fixture has dmx_channel_start and a model dmx_footprint.
	•	The daemon maps computed values to absolute channels:
	•	1-channel fixtures write start
	•	2-channel fixtures write start and start+1

⸻

7. Group Resolution

When controlling a group, the daemon must:
	•	Resolve all member fixtures via:
	•	group_fixtures
	•	nested groups via group_hierarchy
	•	Avoid duplicates
	•	Enforce max nesting depth of 4

⸻

8. Circadian Runtime Behavior

8.1 Applicability
	•	Circadian profiles apply per group (groups.circadian_enabled, groups.circadian_profile_id).

8.2 Update behavior
	•	Circadian output is continuously computed using circadian_profiles.curve_points and interpolation_type.
	•	The daemon periodically applies circadian-derived target values to fixtures in circadian-enabled groups.

8.3 Suspension
	•	Suspension state is tracked in group_state.circadian_suspended and circadian_suspended_at.
	•	Manual control actions affecting a group or fixture should suspend circadian for the impacted group (only).
	•	The daemon must support explicit pause/resume via API.

8.4 Hot-Reload Behavior
	•	When a circadian profile is assigned or unassigned from a group, the daemon immediately reloads its in-memory mappings without requiring a restart.
	•	When a profile's keyframes are updated, the daemon reloads that specific profile in the circadian engine cache.
	•	Newly assigned profiles take effect on the next control loop iteration (~33ms at 30Hz).

⸻

9. Input Handling

9.1 Switch targeting
	•	Each switch targets exactly one of:
	•	target_group_id
	•	target_fixture_id

9.1.1 Input Source Selection

Each switch specifies an input source:
	•	`input_source`: 'labjack' | 'gpio'
	•	Source determines which hardware subsystem reads the input

**LabJack Source:**
	•	`labjack_digital_pin`: Pin identifier (e.g., 0-15)
	•	`labjack_analog_pin`: Analog pin identifier (e.g., 0-15)
	•	Supports both analog and digital inputs

**GPIO Source:**
	•	`gpio_bcm_pin`: BCM pin number (integer, e.g., 17)
	•	`gpio_pull`: 'up' | 'down' (default: 'up')
	•	Digital inputs only

9.2 Polling

**LabJack:**
	•	Poll analog and digital pins required by each switch model.

**GPIO:**
	•	Uses edge detection (interrupt-based) rather than polling
	•	Callback registered per pin via `gpiozero`
	•	Events queued and processed in input loop

9.3 Debouncing
	•	Use switch_models.debounce_ms per switch model.

9.4 Default input behaviors

The daemon must implement v1 behaviors at minimum:

9.4.1 Retractive (momentary)
	•	OFF:
	•	tap → ON to full brightness
	•	hold → ramp up from 0 until release
	•	ON:
	•	tap → OFF
	•	hold → ramp down to 0 until release
	•	Dimming speed for ramps: seconds from 100%→0%. (Source for this parameter is outside current schema; implement as daemon config default for v1.)

9.4.2 switch_simple
	•	tap toggles on/off.

9.4.3 rotary_abs (0–10V)
	•	Analog voltage maps to brightness percent (0–100).
	•	Optional future: map to CCT. (Out of scope v1 unless later specified.)

9.4.4 paddle_composite (0–10V + digital)
	•	Treat as:
	•	analog sets brightness
	•	digital provides on/off intent (implementation-defined)

9.5 Multi-tap scene triggers
	•	Support recognizing double and triple tap events.
	•	Mapping from tap patterns to scenes is not represented in schema and must be defined via configuration until schema support is added.

⸻

10. Local HTTP API (Coordination Contract)

The daemon exposes a local-only HTTP API for the Next.js web app.
	•	Listen on 127.0.0.1 by default.
	•	No auth in v1.

All endpoints use JSON.

10.1 Health

GET /health
Response:

{
  "status": "ok|degraded|down",
  "dependencies": {
    "ola": "ok|degraded|down",
    "dmx_adapter": "connected|missing|unknown",
    "labjack": "connected|missing|unknown"
  }
}

10.2 Read runtime state

GET /state/fixtures
Returns persisted runtime state for all fixtures (joins optional).

GET /state/groups
Returns persisted runtime state for all groups.

10.3 Control fixture

POST /control/fixtures/:id
Request:

{
  "is_on": true,
  "brightness_percent": 75,
  "cct_kelvin": 3000
}

Behavior:
	•	Update fixture_state
	•	Compute DMX
	•	Output via OLA
	•	If is_on=false, force output to 0

10.4 Control group

POST /control/groups/:id
Request:

{
  "is_on": true,
  "brightness_percent": 50,
  "cct_kelvin": 3000
}

Behavior:
	•	Resolve fixtures in group (including nested)
	•	Update each fixture_state
	•	Output DMX

10.5 Scene recall (with toggle support)

POST /api/scenes/recall
Request:
{
  "scene_id": 1,
  "fade_duration": 0.5  // Optional, seconds
}

Behavior:
	•	For idempotent scenes: Apply scene_values, update fixture_state
	•	For toggle scenes: If all fixtures are at scene level (within 5 units tolerance), turn them off instead
	•	Update group_state.last_active_scene_id (scope group)
	•	Output DMX

Response:
{
  "message": "Scene recalled successfully",
  "toggled_off": false  // true if toggle scene was turned off
}

10.5.1 Scene capture

POST /api/scenes/capture
Request:
{
  "name": "My Scene",
  "scene_type": "toggle",  // or "idempotent"
  "scope_group_id": 5,     // Optional - scopes to specific group
  "include_group_ids": [5], // Optional - only capture these groups
  "exclude_fixture_ids": [], // Optional
  "exclude_group_ids": []   // Optional
}

Behavior:
	•	Creates new scene with current fixture brightness/CCT values
	•	If include_group_ids specified, only captures fixtures in those groups
	•	Returns created scene with id

10.5.2 Scene reorder

POST /api/scenes/reorder
Request:
{
  "scene_ids": [3, 1, 2, 5]  // New order of scene IDs
}

Behavior:
	•	Sets display_order for each scene based on array position
	•	Returns updated scenes sorted by new order

10.6 Group reorder

POST /api/groups/reorder
Request:
{
  "group_ids": [3, 1, 2, 5]  // New order of group IDs
}

Behavior:
	•	Sets display_order for each group based on array position
	•	Returns updated groups sorted by new order

10.6.1 Group response format

All group endpoints return the following sleep lock fields:

```json
{
  "id": 1,
  "name": "Bedroom",
  // ... other fields ...
  "sleep_lock_enabled": true,
  "sleep_lock_start_time": "22:00",
  "sleep_lock_end_time": "07:00",
  "sleep_lock_unlock_duration_minutes": 5,
  "sleep_lock_active": true  // Computed at request time
}
```

**`sleep_lock_active` computation:**
	•	Returns `true` if sleep lock is enabled AND current server time falls within the configured window
	•	Handles overnight time ranges (e.g., 22:00 to 07:00)
	•	Returns `false` if sleep lock is disabled or times are not configured
	•	Times are interpreted as server local time

**Validation:**
	•	When `sleep_lock_enabled` is true, both `sleep_lock_start_time` and `sleep_lock_end_time` must be provided
	•	Time format must be HH:MM (24-hour format)
	•	`sleep_lock_unlock_duration_minutes` must be between 0 and 60

10.7 Circadian pause/resume

POST /groups/:id/circadian/pause
Sets group_state.circadian_suspended=true and timestamp.

POST /groups/:id/circadian/resume
Sets group_state.circadian_suspended=false.

10.8 Fixture merge/unmerge

POST /fixtures/merge
Request:

{
  "primary_fixture_id": 1,
  "secondary_fixture_id": 2,
  "target_model_id": 3  // Optional - tunable white model to apply
}

Behavior:
	•	Combines two single-channel fixtures into one dual-channel tunable white fixture
	•	Primary fixture keeps its name, secondary's DMX channel becomes secondary_dmx_channel
	•	If target_model_id provided, updates the fixture's model
	•	Secondary fixture is deleted
	•	Useful for warm+cool LED drivers that need separate DMX channels

POST /fixtures/:id/unmerge
Behavior:
	•	Removes secondary_dmx_channel from the fixture
	•	Does NOT recreate the deleted secondary fixture

10.8 Configuration view

GET /config
Returns effective daemon configuration.

10.8.1 Platform Information

GET /api/gpio/platform
Response:
```json
{
  "is_raspberry_pi": true,
  "pi_model": "Raspberry Pi 5 Model B",
  "gpio_available": true,
  "reason": null,
  "gpio_pins": {
    "available": [4, 5, 6, 12, 13, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27],
    "in_use": [17, 22],
    "disabled": [0, 1, 2, 3, 7, 8, 9, 10, 11, 14, 15]
  }
}
```

When not running on Raspberry Pi:
```json
{
  "is_raspberry_pi": false,
  "pi_model": null,
  "gpio_available": false,
  "reason": "Not running on a Raspberry Pi",
  "gpio_pins": null
}
```

10.8.2 GPIO Pin Layout

GET /api/gpio/layout
Response (for UI pin diagram):
```json
{
  "header_pins": [
    {"physical": 1, "type": "power", "label": "3.3V"},
    {"physical": 2, "type": "power", "label": "5V"},
    {"physical": 3, "type": "disabled", "bcm": 2, "label": "GPIO2 (SDA)", "in_use": false},
    {"physical": 7, "type": "gpio", "bcm": 4, "label": "GPIO4", "in_use": false},
    ...
  ],
  "ground_pins": [6, 9, 14, 20, 25, 30, 34, 39],
  "available_bcm_pins": [4, 5, 6, 12, 13, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27]
}
```

10.8.3 Nearest Ground Pin

GET /api/gpio/nearest-ground/{bcm_pin}
Response:
```json
{
  "selected_physical_pin": 11,
  "nearest_ground_physical": 9,
  "wiring_instruction": "Connect switch between Pin 11 (GPIO17) and Pin 9 (GND)"
}
```

10.9 Event stream (recommended)

GET /events
Server-Sent Events (SSE) stream for:
	•	alerts
	•	dependency changes
	•	input events (developer mode)
	•	state updates

Event examples:
	•	alert.critical
	•	alert.warning
	•	dependency.ola.down
	•	dependency.labjack.disconnected
	•	state.fixture.updated

10.10 WebSocket Real-Time Updates

WebSocket endpoint: /api/ws
Protocol: WebSocket (ws:// or wss://)

The daemon provides real-time state updates via WebSocket for responsive UI updates, particularly for physical switch actions.

Broadcast events:
	•	fixture_state_changed - Sent when a fixture's state changes due to physical switch input
	•	group_state_changed - Sent when a group's state changes due to physical switch input

fixture_state_changed event format:
{
  "type": "fixture_state_changed",
  "fixture_id": 10,
  "brightness": 0.75,        // 0.0-1.0 range
  "color_temp": 3500         // Kelvin (optional, null for non-tunable fixtures)
}

group_state_changed event format:
{
  "type": "group_state_changed",
  "group_id": 5,
  "brightness": 0.6,         // 0.0-1.0 range
  "color_temp": 4000         // Kelvin (optional, null if group not in circadian mode)
}

Broadcast behavior:
	•	Broadcasts are triggered by physical switch actions (momentary, latching, retractive)
	•	During dimming (hold events), broadcasts are throttled to maximum once per 100ms to prevent overwhelming clients
	•	Error handling: broadcast failures are logged but do not interrupt switch handler operation
	•	No authentication required (daemon listens on localhost only)

Client recommendations:
	•	Track pending API requests to avoid race conditions with WebSocket updates
	•	Implement early returns to skip unnecessary re-renders when state hasn't changed
	•	Use debouncing/throttling on the client side for high-frequency updates during dimming

⸻

11. Alerts and Logging

11.1 Log requirements
	•	Log all:
	•	incoming API commands
	•	derived input events
	•	dependency status changes
	•	state changes applied
	•	errors and restart attempts
	•	Retain 7 days; prune automatically.

11.2 Alert levels
	•	Critical (blocking): OLA down, DMX adapter missing
	•	Warning (non-blocking): LabJack missing

Alerts must be surfaced to the web app via:
	•	/events stream and/or
	•	health endpoint fields and log entries

⸻

12. Open Questions / Schema Gaps (explicit)

These capabilities are required by product intent but not represented in the current schema. Until schema changes are made, the daemon must treat them as configuration-only:
	•	Per-switch photo storage (photo_url)
	•	Per-switch tap thresholds (schema only has debounce_ms at model level)
	•	Per-switch mapping of single/double/triple tap to scenes
	•	Per-switch dimming speed (seconds for full dim)
	•	Global/group/fixture dimming curve assignments (not modeled)

⸻

End of Document