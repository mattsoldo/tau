# API Contract (v1)

Lighting Control System
Schema-Driven API Specification

This document defines the complete HTTP API contract derived from the SQL schema (`schema.sql`).
The schema is the source of truth. This document exists to guide implementation and ensure consistent behavior between backend services and the web UI.

---

## 0. General Conventions

### Base

* Base path: `/api`
* JSON request and response bodies
* UTF-8 encoding
* All timestamps are ISO-8601 UTC strings

### IDs

* All primary keys are integers
* Foreign keys reference integer IDs

### Errors

All non-2xx responses return:

```json
{
  "error": {
    "code": "STRING",
    "message": "Human-readable explanation",
    "details": {}
  }
}
```

Common error codes:

* `VALIDATION_ERROR`
* `NOT_FOUND`
* `CONFLICT`
* `FK_RESTRICTED`
* `DMX_CHANNEL_COLLISION`
* `DEPENDENCY_DOWN`
* `UNSUPPORTED_OPERATION`
* `INTERNAL_ERROR`

### Pagination

List endpoints return:

```json
{
  "items": [],
  "total": 0,
  "limit": 50,
  "offset": 0
}
```

Query params:

* `limit` (default 50)
* `offset` (default 0)
* `q` (text search where applicable)

### Derived / computed behavior

The schema encodes some requirements that the API must enforce:

* Fixtures have a DMX footprint (from fixture model) and **must not overlap** any other fixture’s occupied DMX address range (collision detection).
* A switch targets **exactly one** of: a group OR a fixture (mutually exclusive).

---

## 1. Fixture Models (`fixture_models`)

### Object

```json
{
  "id": 1,
  "manufacturer": "string",
  "model": "string",
  "description": "string|null",
  "type": "simple_dimmable|tunable_white|dim_to_warm|non_dimmable|other",
  "dmx_footprint": 1,
  "cct_min_kelvin": 1800,
  "cct_max_kelvin": 4000,
  "mixing_type": "linear|perceptual|logarithmic|custom",
  "created_at": "2025-01-01T00:00:00Z"
}
```

### Endpoints

* `GET /api/fixture-models`
* `POST /api/fixture-models`
* `GET /api/fixture-models/:id`
* `PATCH /api/fixture-models/:id`
* `DELETE /api/fixture-models/:id`

#### GET `/api/fixture-models`

Query:

* `q` searches manufacturer/model/description
* `type` optional filter (`simple_dimmable|tunable_white|dim_to_warm|non_dimmable|other`)

#### POST `/api/fixture-models`

Request:

```json
{
  "manufacturer": "Acme",
  "model": "TW-200",
  "description": "",
  "type": "tunable_white",
  "dmx_footprint": 2,
  "cct_min_kelvin": 1800,
  "cct_max_kelvin": 4000,
  "mixing_type": "perceptual"
}
```

Optional fields with defaults:

* `dmx_footprint` (default: 1)
* `cct_min_kelvin` (default: 1800)
* `cct_max_kelvin` (default: 4000)
* `description` (default: null)

Rules:

* `(manufacturer, model)` must be unique

#### GET `/api/fixture-models/:id`

#### PATCH `/api/fixture-models/:id`

Allowed fields:

* `manufacturer`, `model`, `description`, `type`, `dmx_footprint`, `cct_min_kelvin`, `cct_max_kelvin`, `mixing_type`
  Rules:
* If `dmx_footprint` increases and creates DMX collisions with existing fixtures, reject with `DMX_CHANNEL_COLLISION`.

#### DELETE `/api/fixture-models/:id`

Rules:

* Must fail with `FK_RESTRICTED` if referenced by any fixture (`ON DELETE RESTRICT`).

---

## 2. Fixtures (`fixtures`)

### Object

```json
{
  "id": 10,
  "name": "Kitchen Downlights",
  "fixture_model_id": 1,
  "dmx_channel_start": 1,
  "created_at": "2025-01-01T00:00:00Z"
}
```

### Endpoints

* `GET /api/fixtures`
* `POST /api/fixtures`
* `GET /api/fixtures/:id`
* `PATCH /api/fixtures/:id`
* `DELETE /api/fixtures/:id`

#### GET `/api/fixtures`

Query:

* `q` searches fixture name
* `include=model` optional

If `include=model`, embed:

```json
{
  "model": { "...fixture_models fields..." }
}
```

#### POST `/api/fixtures`

Request:

```json
{
  "name": "Kitchen Downlights",
  "fixture_model_id": 1,
  "dmx_channel_start": 1
}
```

Rules:

* `dmx_channel_start` must be unique
* Must validate DMX footprint collision:

  * Occupied range = `[start, start + footprint - 1]`
  * Reject overlaps with `DMX_CHANNEL_COLLISION` and include conflicting fixtures/ranges in `details`.

#### GET `/api/fixtures/:id`

#### PATCH `/api/fixtures/:id`

Allowed fields:

* `name`
* `fixture_model_id` (requires collision re-check)
* `dmx_channel_start` (requires collision re-check)

#### DELETE `/api/fixtures/:id`

Rules:

* Cascades to fixture state and related membership/value tables via FKs.

### Helper (recommended)

#### GET `/api/dmx/collisions`

Returns detected overlaps (should be empty if validations are correct):

```json
{
  "items": [
    {
      "fixture_id_a": 10,
      "fixture_id_b": 11,
      "range_a": [1, 2],
      "range_b": [2, 3]
    }
  ]
}
```

---

## 3. Switch Models (`switch_models`)

### Object

```json
{
  "id": 1,
  "manufacturer": "string",
  "model": "string",
  "input_type": "retractive|rotary_abs|paddle_composite|switch_simple",
  "debounce_ms": 500,
  "dimming_curve": "linear|logarithmic",
  "requires_digital_pin": true,
  "requires_analog_pin": false
}
```

Notes:

* `debounce_ms` and `dimming_curve` are **locked to the model** (schema does not allow per-switch overrides).

### Endpoints

* `GET /api/switch-models`
* `POST /api/switch-models`
* `GET /api/switch-models/:id`
* `PATCH /api/switch-models/:id`
* `DELETE /api/switch-models/:id`

#### POST `/api/switch-models`

Request:

```json
{
  "manufacturer": "Torchstar",
  "model": "0-10V Paddle",
  "input_type": "paddle_composite",
  "debounce_ms": 500,
  "dimming_curve": "logarithmic",
  "requires_digital_pin": true,
  "requires_analog_pin": true
}
```

Optional fields with defaults:

* `debounce_ms` (default: 500)
* `dimming_curve` (default: 'logarithmic')
* `requires_digital_pin` (default: true)
* `requires_analog_pin` (default: false)

Rules:

* `(manufacturer, model)` must be unique

#### DELETE `/api/switch-models/:id`

Rules:

* Must fail with `FK_RESTRICTED` if referenced by any switch.

---

## 4. Switches (`switches`)

### Object

```json
{
  "id": 100,
  "name": "Kitchen Paddle",
  "switch_model_id": 1,
  "labjack_digital_pin": 4,
  "labjack_analog_pin": 0,
  "target_group_id": 10,
  "target_fixture_id": null,
  "photo_url": "string|null"
}
```

Note:

* `photo_url` is optional and can be used to display switch images in the UI.

Rules:

* Exactly one of `target_group_id` or `target_fixture_id` must be set.
* Required pins must be present according to the referenced switch model:

  * If `requires_digital_pin=true`, `labjack_digital_pin` is required
  * If `requires_analog_pin=true`, `labjack_analog_pin` is required

### Endpoints

* `GET /api/switches`
* `POST /api/switches`
* `GET /api/switches/:id`
* `PATCH /api/switches/:id`
* `DELETE /api/switches/:id`

#### GET `/api/switches`

Query:

* `q` searches switch name
* `include=model,target` optional

If `include=model`, embed:

```json
{ "model": { "...switch_models fields..." } }
```

If `include=target`, embed exactly one:

```json
{ "target": { "type": "group", "group": { "...groups fields..." } } }
```

OR

```json
{ "target": { "type": "fixture", "fixture": { "...fixtures fields..." } } }
```

#### POST `/api/switches`

Request:

```json
{
  "name": "Kitchen Paddle",
  "switch_model_id": 1,
  "labjack_digital_pin": 4,
  "labjack_analog_pin": 0,
  "target_group_id": 10,
  "target_fixture_id": null,
  "photo_url": null
}
```

Optional fields with defaults:

* `photo_url` (default: null)
* `labjack_digital_pin` (default: null, but required if switch model's `requires_digital_pin=true`)
* `labjack_analog_pin` (default: null, but required if switch model's `requires_analog_pin=true`)

---

## 5. Groups (`groups`)

### Object

```json
{
  "id": 10,
  "name": "Kitchen",
  "description": "string|null",
  "circadian_enabled": false,
  "circadian_profile_id": 1,
  "created_at": "2025-01-01T00:00:00Z"
}
```

### Endpoints

* `GET /api/groups`
* `POST /api/groups`
* `GET /api/groups/:id`
* `PATCH /api/groups/:id`
* `DELETE /api/groups/:id`

#### GET `/api/groups`

Query:

* `q` searches name/description
* `include=fixtures,children,state` optional

If `include=fixtures`, embed:

```json
{ "fixtures": [ { "...fixtures fields..." } ] }
```

If `include=children`, embed:

```json
{ "children": [ { "...groups fields..." } ] }
```

If `include=state`, embed:

```json
{ "state": { "...group_state fields..." } }
```

---

## 6. Group Membership (`group_fixtures`)

### Endpoints

* `GET /api/groups/:id/fixtures`
* `PUT /api/groups/:id/fixtures` (replace set)
* `POST /api/groups/:id/fixtures` (add one)
* `DELETE /api/groups/:id/fixtures/:fixture_id` (remove one)

#### PUT `/api/groups/:id/fixtures`

Request:

```json
{ "fixture_ids": [10, 11, 12] }
```

---

## 7. Group Nesting (`group_hierarchy`)

### Endpoints

* `GET /api/groups/:id/children`
* `POST /api/groups/:id/children`
* `DELETE /api/groups/:id/children/:child_group_id`

#### POST `/api/groups/:id/children`

Request:

```json
{ "child_group_id": 20 }
```

Rules:

* Must not allow cycles
* Must not exceed max depth of 4

---

## 8. Circadian Profiles (`circadian_profiles`)

### Object

```json
{
  "id": 1,
  "name": "Standard Day",
  "description": "string|null",
  "curve_points": [
    { "time": "06:00", "brightness": 0, "cct": 2700 },
    { "time": "08:00", "brightness": 90, "cct": 4000 }
  ],
  "interpolation_type": "linear|cosine|step",
  "created_at": "2025-01-01T00:00:00Z"
}
```

### Endpoints

* `GET /api/circadian-profiles`
* `POST /api/circadian-profiles`
* `GET /api/circadian-profiles/:id`
* `PATCH /api/circadian-profiles/:id`
* `DELETE /api/circadian-profiles/:id`

#### POST `/api/circadian-profiles`

Optional fields with defaults:

* `interpolation_type` (default: 'linear')
* `description` (default: null)

Rules:

* `name` must be unique
* Validate `curve_points`:

  * `time` in `HH:MM`
  * `brightness` in 0–1000
  * `cct` integer kelvin

---

## 9. Scenes (`scenes`)

### Object

```json
{
  "id": 1,
  "name": "Dinner",
  "scope_group_id": 10
}
```

### Endpoints

* `GET /api/scenes`
* `POST /api/scenes`
* `GET /api/scenes/:id`
* `PATCH /api/scenes/:id`
* `DELETE /api/scenes/:id`

#### POST `/api/scenes`

Request supports optional inline values:

```json
{
  "name": "Dinner",
  "scope_group_id": 10,
  "values": [
    { "fixture_id": 10, "target_brightness_percent": 30, "target_cct_kelvin": 2700 },
    { "fixture_id": 11, "target_brightness_percent": 10, "target_cct_kelvin": 2400 }
  ]
}
```

Optional fields with defaults:

* `scope_group_id` (default: null, scene applies globally if not set)
* `values` (default: empty, can be added later via scene values endpoint)

---

## 10. Scene Values (`scene_values`)

### Object

```json
{
  "scene_id": 1,
  "fixture_id": 10,
  "target_brightness_percent": 30,
  "target_cct_kelvin": 2700
}
```

### Endpoints

* `GET /api/scenes/:id/values`
* `PUT /api/scenes/:id/values` (replace set)

#### PUT `/api/scenes/:id/values`

Request:

```json
{
  "values": [
    { "fixture_id": 10, "target_brightness_percent": 30, "target_cct_kelvin": 2700 }
  ]
}
```

Rules:

* `target_brightness_percent` must be 0–100

---

## 11. Fixture Runtime State (`fixture_state`)

### Object

```json
{
  "fixture_id": 10,
  "current_brightness": 50,
  "current_cct": 3000,
  "is_on": true,
  "last_updated": "2025-01-01T00:00:00Z"
}
```

### Endpoints

* `GET /api/state/fixtures`
* `GET /api/state/fixtures/:fixture_id`

---

## 12. Group Runtime State (`group_state`)

### Object

```json
{
  "group_id": 10,
  "circadian_suspended": false,
  "circadian_suspended_at": null,
  "last_active_scene_id": 1
}
```

### Endpoints

* `GET /api/state/groups`
* `GET /api/state/groups/:group_id`

---

## 13. Control Endpoints (Logical State Changes)

These endpoints change logical state and must trigger DMX output updates.

### 13.1 Control Fixture

`POST /api/control/fixtures/:id`
Request:

```json
{
  "is_on": true,
  "brightness_percent": 75,
  "cct_kelvin": 3000
}
```

Optional fields:

* All fields are optional; only provided fields will be updated
* If `is_on` is omitted, current state is retained
* If `brightness_percent` is omitted, current brightness is retained
* If `cct_kelvin` is omitted, current CCT is retained

Rules:

* `brightness_percent` must be 0–100
* For fixtures that do not support CCT, either ignore `cct_kelvin` or reject with `VALIDATION_ERROR` (implementation must choose one behavior and keep it consistent).
* Updates `fixture_state` and DMX output.

### 13.2 Control Group

`POST /api/control/groups/:id`
Request:

```json
{
  "is_on": true,
  "brightness_percent": 50,
  "cct_kelvin": 3000
}
```

Optional fields:

* All fields are optional; only provided fields will be applied to all fixtures in the group

Rules:

* Applies to all fixtures in the group, including nested groups.
* Updates `fixture_state` for each affected fixture.

### 13.3 Activate Scene

`POST /api/control/scenes/:id/activate`
Effects:

* Applies all `scene_values`
* Updates `fixture_state` for affected fixtures
* Updates `group_state.last_active_scene_id` for the scene scope group (if any)

---

## 14. Circadian Runtime Control

### Pause

`POST /api/groups/:id/circadian/pause`
Effects:

* Sets `group_state.circadian_suspended=true`
* Sets `circadian_suspended_at=now()`

### Resume

`POST /api/groups/:id/circadian/resume`
Effects:

* Sets `group_state.circadian_suspended=false`
* Clears or retains timestamp (implementation choice; must be consistent)

---

## 15. Health, Logs, Diagnostics

### 15.1 Health

`GET /api/health`
Response:

```json
{
  "ola": "ok|degraded|down",
  "dmx_adapter": "connected|missing|unknown",
  "labjack": "connected|missing|unknown"
}
```

### 15.2 Logs

* `GET /api/logs`
* `GET /api/logs/download`

### 15.3 Developer Mode (optional)

* `GET /api/dev/labjack/inputs`
* `GET /api/dev/dmx/frame`

---

## End of Document
