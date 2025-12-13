# Tau Lighting Control - API Reference

Complete reference for all REST API endpoints and WebSocket communication.

## Base URL

```
http://localhost:8000
```

Change the host/port based on your deployment configuration.

---

## Interactive Documentation

When the daemon is running, access the interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

---

## System Endpoints

### `GET /health`

Health check endpoint for monitoring and load balancers.

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "service": "tau-daemon"
}
```

### `GET /status`

Comprehensive system status with performance metrics.

**Response:**
```json
{
  "status": "running",
  "version": "0.1.0",
  "service": "tau-daemon",
  "event_loop": {
    "running": true,
    "frequency_hz": 30.0,
    "actual_hz": 29.98,
    "avg_iteration_ms": 0.42,
    "total_iterations": 1234567
  },
  "state_manager": {
    "fixtures_count": 10,
    "groups_count": 3,
    "fixtures_on": 7
  },
  "hardware": {
    "labjack": "connected",
    "ola": "connected"
  },
  "lighting": {
    "circadian_groups_active": 2,
    "scenes_recalled": 15
  }
}
```

---

## WebSocket

### `WS /ws`

Real-time bidirectional communication for live updates.

#### Connection

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');
```

#### Subscribe to Events

```javascript
ws.send(JSON.stringify({
  action: 'subscribe',
  event_types: ['fixture_state_changed', 'scene_recalled']
}));
```

To receive all events:

```javascript
ws.send(JSON.stringify({
  action: 'subscribe',
  event_types: []
}));
```

#### Unsubscribe

```javascript
ws.send(JSON.stringify({
  action: 'unsubscribe',
  event_types: ['fixture_state_changed']
}));
```

#### Keepalive (Ping/Pong)

```javascript
ws.send(JSON.stringify({action: 'ping'}));
// Server responds with: {"type": "pong"}
```

#### Event Types

- `fixture_state_changed` - Fixture brightness/CCT changed
- `group_state_changed` - Group state changed
- `scene_recalled` - Scene was recalled
- `scene_captured` - New scene was captured
- `circadian_changed` - Circadian profile modified
- `hardware_status` - Hardware connection status changed
- `system_status` - System health status changed

#### Example Events

**Fixture State Changed:**
```json
{
  "event_type": "fixture_state_changed",
  "fixture_id": 1,
  "brightness": 0.8,
  "color_temp": 3000,
  "is_on": true,
  "timestamp": "2025-01-15T10:30:00Z"
}
```

**Scene Recalled:**
```json
{
  "event_type": "scene_recalled",
  "scene_id": 5,
  "scene_name": "Movie Time",
  "fixtures_affected": 3,
  "timestamp": "2025-01-15T10:30:00Z"
}
```

### `GET /ws/stats`

Get WebSocket connection statistics.

**Response:**
```json
{
  "active_connections": 3,
  "total_subscriptions": 15,
  "messages_sent": 45678
}
```

---

## Fixture Models

Fixture models define types of light fixtures (e.g., "Phillips Hue White Ambiance").

### `GET /api/fixtures/models`

List all fixture models.

**Response:**
```json
[
  {
    "id": 1,
    "manufacturer": "Phillips",
    "model": "Hue White Ambiance",
    "type": "tunable_white",
    "dmx_footprint": 2,
    "cct_min_kelvin": 2200,
    "cct_max_kelvin": 6500,
    "mixing_type": "perceptual"
  }
]
```

### `POST /api/fixtures/models`

Create a new fixture model.

**Request:**
```json
{
  "manufacturer": "Generic",
  "model": "LED Strip 12V",
  "type": "simple_dimmable",
  "dmx_footprint": 1,
  "mixing_type": "linear"
}
```

**Response:** `201 Created` with created model

### `GET /api/fixtures/models/{model_id}`

Get a specific fixture model.

### `DELETE /api/fixtures/models/{model_id}`

Delete a fixture model (only if no fixtures use it).

---

## Fixtures

Fixtures are individual light instances with DMX channel assignments.

### `GET /api/fixtures/`

List all fixtures.

**Response:**
```json
[
  {
    "id": 1,
    "name": "Living Room Ceiling 1",
    "fixture_model_id": 1,
    "dmx_channel_start": 10,
    "created_at": "2025-01-15T10:00:00Z"
  }
]
```

### `POST /api/fixtures/`

Create a new fixture.

**Request:**
```json
{
  "name": "Kitchen Counter LEDs",
  "fixture_model_id": 2,
  "dmx_channel_start": 20
}
```

**Response:** `201 Created` with fixture

### `GET /api/fixtures/{fixture_id}`

Get a specific fixture.

### `PATCH /api/fixtures/{fixture_id}`

Update fixture properties.

**Request:**
```json
{
  "name": "Kitchen Counter LEDs - Updated"
}
```

### `DELETE /api/fixtures/{fixture_id}`

Delete a fixture.

### `GET /api/fixtures/{fixture_id}/state`

Get current state of a fixture.

**Response:**
```json
{
  "fixture_id": 1,
  "brightness": 0.75,
  "color_temp": 3200,
  "is_on": true,
  "circadian_active": true,
  "last_updated": "2025-01-15T10:30:00Z"
}
```

---

## Groups

Groups allow coordinated control of multiple fixtures.

### `GET /api/groups/`

List all groups.

**Response:**
```json
[
  {
    "id": 1,
    "name": "Living Room",
    "description": "All living room fixtures",
    "circadian_enabled": true,
    "circadian_profile_id": 1,
    "created_at": "2025-01-15T10:00:00Z"
  }
]
```

### `POST /api/groups/`

Create a new group.

**Request:**
```json
{
  "name": "Kitchen",
  "description": "Kitchen task lighting",
  "circadian_enabled": false
}
```

### `GET /api/groups/{group_id}`

Get a specific group.

### `PATCH /api/groups/{group_id}`

Update group properties.

**Request:**
```json
{
  "circadian_enabled": true,
  "circadian_profile_id": 2
}
```

### `DELETE /api/groups/{group_id}`

Delete a group.

### `GET /api/groups/{group_id}/fixtures`

List fixtures in a group.

**Response:**
```json
[
  {
    "fixture_id": 1,
    "fixture_name": "Living Room Ceiling 1"
  },
  {
    "fixture_id": 2,
    "fixture_name": "Living Room Ceiling 2"
  }
]
```

### `POST /api/groups/{group_id}/fixtures`

Add a fixture to a group.

**Request:**
```json
{
  "fixture_id": 3
}
```

### `DELETE /api/groups/{group_id}/fixtures/{fixture_id}`

Remove a fixture from a group.

### `GET /api/groups/{group_id}/state`

Get current state of a group.

**Response:**
```json
{
  "group_id": 1,
  "circadian_suspended": false,
  "last_scene_id": 5,
  "fixtures_on": 2,
  "fixtures_total": 2
}
```

---

## Scenes

Scenes capture and recall lighting presets.

### `GET /api/scenes/`

List all scenes.

**Response:**
```json
[
  {
    "id": 1,
    "name": "Movie Time",
    "scope_group_id": 1,
    "created_at": "2025-01-15T10:00:00Z"
  }
]
```

### `POST /api/scenes/`

Create a scene manually.

**Request:**
```json
{
  "name": "Reading Mode",
  "scope_group_id": 2
}
```

### `POST /api/scenes/capture`

Capture current fixture states as a new scene.

**Request:**
```json
{
  "name": "Cozy Evening",
  "fixture_ids": [1, 2, 3],
  "scope_group_id": 1
}
```

**Response:** `201 Created` with scene

### `POST /api/scenes/recall`

Recall a scene by ID.

**Request:**
```json
{
  "scene_id": 1
}
```

**Response:** `200 OK` - Fixtures updated immediately

### `GET /api/scenes/{scene_id}`

Get scene details including all fixture values.

**Response:**
```json
{
  "id": 1,
  "name": "Movie Time",
  "scope_group_id": 1,
  "values": [
    {
      "fixture_id": 1,
      "target_brightness": 100,
      "target_cct_kelvin": 2200
    },
    {
      "fixture_id": 2,
      "target_brightness": 100,
      "target_cct_kelvin": 2200
    }
  ]
}
```

### `PATCH /api/scenes/{scene_id}`

Update scene properties.

**Request:**
```json
{
  "name": "Movie Night"
}
```

### `DELETE /api/scenes/{scene_id}`

Delete a scene.

---

## Circadian Profiles

Circadian profiles define time-based lighting curves for daylight simulation.

### `GET /api/circadian/`

List all circadian profiles.

**Response:**
```json
[
  {
    "id": 1,
    "name": "Standard Home",
    "description": "Natural daylight simulation",
    "keyframes": [
      {
        "time": "06:00:00",
        "brightness": 0.2,
        "cct": 2200
      },
      {
        "time": "12:00:00",
        "brightness": 1.0,
        "cct": 5500
      },
      {
        "time": "22:00:00",
        "brightness": 0.2,
        "cct": 2200
      }
    ]
  }
]
```

### `POST /api/circadian/`

Create a new circadian profile.

**Request:**
```json
{
  "name": "Work Focus",
  "description": "High CCT for alertness",
  "keyframes": [
    {"time": "07:00:00", "brightness": 0.6, "cct": 4500},
    {"time": "12:00:00", "brightness": 1.0, "cct": 6000},
    {"time": "18:00:00", "brightness": 0.5, "cct": 3500}
  ]
}
```

**Response:** `201 Created` with profile

### `GET /api/circadian/{profile_id}`

Get a specific circadian profile.

### `PATCH /api/circadian/{profile_id}`

Update circadian profile.

**Request:**
```json
{
  "description": "Updated description",
  "keyframes": [...]
}
```

### `DELETE /api/circadian/{profile_id}`

Delete a circadian profile (only if no groups use it).

---

## Control

Direct control of fixtures and groups.

### `POST /api/control/fixtures/{fixture_id}`

Control a specific fixture.

**Request:**
```json
{
  "brightness": 0.8,
  "color_temp": 3000
}
```

**Response:** `200 OK` - Fixture updated immediately

Set only brightness:
```json
{
  "brightness": 0.5
}
```

Set only color temperature:
```json
{
  "color_temp": 2700
}
```

### `POST /api/control/groups/{group_id}`

Control all fixtures in a group.

**Request:**
```json
{
  "brightness": 0.7,
  "color_temp": 3500
}
```

### `POST /api/control/groups/{group_id}/circadian`

Control circadian automation for a group.

**Suspend circadian:**
```json
{
  "action": "suspend"
}
```

**Resume circadian:**
```json
{
  "action": "resume"
}
```

### `POST /api/control/all-off`

Turn all fixtures off immediately.

**Response:** `200 OK` - All fixtures set to 0% brightness

### `POST /api/control/panic`

Emergency panic mode - turn all fixtures to 100% brightness.

**Response:** `200 OK` - All fixtures set to 100% brightness

---

## Value Ranges

### Brightness

- **API/Database**: 0-1000 (integer)
- **Internal/State**: 0.0-1.0 (float)
- **DMX Output**: 0-255 (8-bit)

### Color Temperature (CCT)

- **Range**: 1000-10000 Kelvin
- **Typical**: 2000-6500K
- **Warm white**: 2000-3000K
- **Neutral white**: 3000-4500K
- **Cool white**: 4500-6500K

### DMX Channels

- **Range**: 1-512 per universe
- **Note**: Fixtures must not have overlapping channel ranges

---

## Error Responses

### `400 Bad Request`

Invalid request data (validation error).

```json
{
  "detail": [
    {
      "loc": ["body", "brightness"],
      "msg": "ensure this value is less than or equal to 1.0",
      "type": "value_error"
    }
  ]
}
```

### `404 Not Found`

Resource not found.

```json
{
  "detail": "Fixture not found"
}
```

### `409 Conflict`

Resource conflict (e.g., DMX channel already in use).

```json
{
  "detail": "DMX channel 10 already in use by fixture 'Living Room Ceiling 1'"
}
```

### `500 Internal Server Error`

Server error - check daemon logs.

```json
{
  "detail": "Internal server error"
}
```

---

## Rate Limiting

No rate limiting is currently implemented. For production deployments, consider adding rate limiting via a reverse proxy (nginx, Caddy, etc.).

---

## Authentication

No authentication is currently implemented. This API is designed for trusted local networks. For internet-facing deployments, add authentication via:

- API keys
- OAuth 2.0
- JWT tokens
- HTTP Basic Auth (behind HTTPS)

---

## Examples

### Python

```python
import requests

# Control a fixture
response = requests.post(
    'http://localhost:8000/api/control/fixtures/1',
    json={'brightness': 0.8, 'color_temp': 3000}
)
print(response.json())

# Recall a scene
response = requests.post(
    'http://localhost:8000/api/scenes/recall',
    json={'scene_id': 1}
)
print(response.json())

# Get system status
response = requests.get('http://localhost:8000/status')
print(response.json())
```

### cURL

```bash
# Control a fixture
curl -X POST http://localhost:8000/api/control/fixtures/1 \
  -H "Content-Type: application/json" \
  -d '{"brightness": 0.8, "color_temp": 3000}'

# List all scenes
curl http://localhost:8000/api/scenes/

# Capture a scene
curl -X POST http://localhost:8000/api/scenes/capture \
  -H "Content-Type: application/json" \
  -d '{"name": "Cozy Evening", "fixture_ids": [1, 2, 3]}'

# All off
curl -X POST http://localhost:8000/api/control/all-off
```

### JavaScript/TypeScript

```typescript
// Control fixture
const response = await fetch('http://localhost:8000/api/control/fixtures/1', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({brightness: 0.8, color_temp: 3000})
});
const data = await response.json();

// WebSocket connection
const ws = new WebSocket('ws://localhost:8000/ws');

ws.onopen = () => {
  // Subscribe to all events
  ws.send(JSON.stringify({
    action: 'subscribe',
    event_types: []
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Event:', data.event_type, data);

  if (data.event_type === 'fixture_state_changed') {
    console.log(`Fixture ${data.fixture_id} brightness: ${data.brightness}`);
  }
};

// Keepalive
setInterval(() => {
  ws.send(JSON.stringify({action: 'ping'}));
}, 30000);
```

---

## Support

- **Interactive Docs**: http://localhost:8000/docs
- **GitHub Issues**: https://github.com/yourusername/tau-daemon/issues
- **Deployment Guide**: See `deployment/DEPLOYMENT.md`
- **Configuration Guide**: See `examples/README.md`
