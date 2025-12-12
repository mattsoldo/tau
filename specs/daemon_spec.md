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
	•	On disconnect:
	•	Surface alert
	•	Continue software control via API
	•	Poll for reconnect

4.3 USB-to-DMX adapter
	•	Treated as an OLA dependency.
	•	If missing:
	•	Surface alert instructing user to reconnect
	•	Continue accepting software commands and updating state

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

⸻

9. Input Handling

9.1 Switch targeting
	•	Each switch targets exactly one of:
	•	target_group_id
	•	target_fixture_id

9.2 Polling
	•	Poll analog and digital pins required by each switch model.

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

10.5 Activate scene

POST /control/scenes/:id/activate
Behavior:
	•	Apply scene_values
	•	Update fixture_state
	•	Update group_state.last_active_scene_id (scope group)
	•	Output DMX

10.6 Circadian pause/resume

POST /groups/:id/circadian/pause
Sets group_state.circadian_suspended=true and timestamp.

POST /groups/:id/circadian/resume
Sets group_state.circadian_suspended=false.

10.7 Configuration view

GET /config
Returns effective daemon configuration.

10.8 Event stream (recommended)

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