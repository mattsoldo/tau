"""
Tau Lighting Control API
"""
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uuid

from tau.config import Settings
from tau.api.websocket import connection_manager

# Global reference to daemon (set by main.py)
_daemon_instance: Optional[object] = None


def set_daemon_instance(daemon):
    """Set the global daemon instance for API access"""
    global _daemon_instance
    _daemon_instance = daemon


def get_daemon_instance():
    """Get the global daemon instance"""
    return _daemon_instance


def create_app(settings: Settings) -> FastAPI:
    """Create and configure FastAPI application"""

    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description="""
# Tau Lighting Control API

A comprehensive REST API for controlling smart lighting systems with:

- **Fixtures** - Individual light fixtures with brightness and color temperature control
- **Groups** - Logical grouping of fixtures for synchronized control
- **Scenes** - Capture and recall lighting presets
- **Circadian Rhythms** - Automatic daylight simulation with customizable profiles
- **Real-Time Control** - Direct control of fixtures and groups
- **WebSocket** - Real-time state updates via WebSocket at `/ws`

## Features

- 🎨 Tunable white lighting (brightness + CCT)
- ⏰ Circadian rhythm automation
- 🎬 Scene management (capture/recall)
- 📊 Group-based control
- ⚡ Real-time WebSocket updates
- 🔧 Mock hardware mode for testing

## Getting Started

1. **Create fixture models** - Define your light fixture types
2. **Create fixtures** - Add individual fixture instances
3. **Create groups** (optional) - Group fixtures for coordinated control
4. **Create circadian profiles** (optional) - Define daylight curves
5. **Create scenes** (optional) - Capture lighting presets
6. **Control** - Use `/api/control/*` endpoints to control lighting

## WebSocket

Connect to `/ws` for real-time updates on fixture states, scene recalls, and more.

```javascript
const ws = new WebSocket('ws://localhost:8000/ws');
ws.onmessage = (event) => console.log(JSON.parse(event.data));
```

See the `/ws` endpoint documentation for subscription management.
        """,
        docs_url="/docs" if settings.api_docs_enabled else None,
        redoc_url="/redoc" if settings.api_docs_enabled else None,
        openapi_tags=[
            {
                "name": "system",
                "description": "System health and status endpoints. Use `/health` for monitoring and `/status` for detailed system statistics.",
            },
            {
                "name": "websocket",
                "description": "WebSocket connections for real-time updates. Connect to `/ws` to receive live notifications about fixture states, scenes, and more.",
            },
            {
                "name": "fixtures",
                "description": "Manage light fixtures and fixture models. Fixtures represent individual physical lights with DMX channel assignments.",
            },
            {
                "name": "groups",
                "description": "Manage groups of fixtures. Groups allow coordinated control and circadian rhythm automation across multiple fixtures.",
            },
            {
                "name": "scenes",
                "description": "Capture and recall lighting presets. Scenes store specific brightness/CCT values for fixtures and can be recalled instantly.",
            },
            {
                "name": "circadian",
                "description": "Manage circadian rhythm profiles. Profiles define time-based lighting curves that simulate natural daylight.",
            },
            {
                "name": "control",
                "description": "Direct control of fixtures and groups. Set brightness, color temperature, and manage circadian automation.",
            },
        ],
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # TODO: Configure properly for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check endpoint
    @app.get(
        "/health",
        summary="Health Check",
        description="Check if the daemon is running and healthy. Use this endpoint for monitoring and health probes.",
        tags=["system"],
    )
    async def health_check():
        """Health check endpoint for monitoring"""
        return {
            "status": "healthy",
            "version": settings.api_version,
            "service": "tau-daemon",
        }

    # Status endpoint with event loop statistics
    @app.get(
        "/status",
        summary="System Status",
        description="""
Get comprehensive system status including:
- Event loop performance (Hz, iteration time)
- State manager statistics (fixtures, groups)
- Hardware connection status (LabJack, OLA/DMX)
- Lighting controller statistics

Use this endpoint to monitor system performance and debug issues.
        """,
        tags=["system"],
    )
    async def get_status():
        """Get daemon status including event loop and state management statistics"""
        daemon = get_daemon_instance()

        response = {
            "status": "running",
            "version": settings.api_version,
            "service": "tau-daemon",
        }

        if daemon and daemon.event_loop:
            response["event_loop"] = daemon.event_loop.get_statistics()

        if daemon and daemon.scheduler:
            response["scheduled_tasks"] = daemon.scheduler.get_statistics()

        if daemon and daemon.state_manager:
            response["state_manager"] = daemon.state_manager.get_statistics()

        if daemon and daemon.persistence:
            response["persistence"] = daemon.persistence.get_statistics()

        if daemon and daemon.hardware_manager:
            response["hardware"] = daemon.hardware_manager.get_statistics()

        if daemon and daemon.lighting_controller:
            response["lighting"] = daemon.lighting_controller.get_statistics()

        return response

    # WebSocket endpoint
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """
        WebSocket endpoint for real-time updates

        ## Connection

        Connect to `ws://localhost:8000/ws` to receive real-time events.

        ## Subscription Management

        After connecting, send JSON messages to subscribe to specific event types:

        ```json
        {"action": "subscribe", "event_types": ["fixture_state_changed", "scene_recalled"]}
        ```

        To receive all events, subscribe with an empty list:

        ```json
        {"action": "subscribe", "event_types": []}
        ```

        ## Event Types

        - `fixture_state_changed` - Fixture brightness/CCT changed
        - `group_state_changed` - Group state changed
        - `scene_recalled` - Scene was recalled
        - `scene_captured` - New scene captured
        - `circadian_changed` - Circadian profile modified
        - `hardware_status` - Hardware connection status changed
        - `system_status` - System health status changed

        ## Keepalive

        Send periodic ping messages to keep the connection alive:

        ```json
        {"action": "ping"}
        ```

        The server will respond with:

        ```json
        {"type": "pong"}
        ```

        ## Example (JavaScript)

        ```javascript
        const ws = new WebSocket('ws://localhost:8000/ws');

        ws.onopen = () => {
            // Subscribe to events
            ws.send(JSON.stringify({
                action: 'subscribe',
                event_types: ['fixture_state_changed', 'scene_recalled']
            }));
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            console.log('Event:', data.event_type, data);
        };

        // Keepalive
        setInterval(() => {
            ws.send(JSON.stringify({action: 'ping'}));
        }, 30000);
        ```
        """
        connection_id = str(uuid.uuid4())
        await connection_manager.connect(websocket, connection_id)

        try:
            while True:
                # Receive messages from client (for subscription management, etc.)
                data = await websocket.receive_json()

                # Handle subscription requests
                if data.get("action") == "subscribe":
                    event_types = data.get("event_types", [])
                    connection_manager.subscribe(connection_id, event_types)
                    await connection_manager.send_personal_message(
                        {
                            "type": "subscription",
                            "status": "subscribed",
                            "event_types": event_types
                        },
                        connection_id
                    )

                elif data.get("action") == "unsubscribe":
                    event_types = data.get("event_types", [])
                    connection_manager.unsubscribe(connection_id, event_types)
                    await connection_manager.send_personal_message(
                        {
                            "type": "subscription",
                            "status": "unsubscribed",
                            "event_types": event_types
                        },
                        connection_id
                    )

                elif data.get("action") == "ping":
                    # Respond to ping with pong
                    await connection_manager.send_personal_message(
                        {"type": "pong"},
                        connection_id
                    )

        except WebSocketDisconnect:
            connection_manager.disconnect(connection_id)

    # WebSocket statistics endpoint
    @app.get(
        "/ws/stats",
        summary="WebSocket Statistics",
        description="Get WebSocket connection statistics including active connections, subscriptions, and message counts.",
        tags=["websocket"],
    )
    async def websocket_stats():
        """Get WebSocket connection statistics"""
        return connection_manager.get_statistics()

    # Register API routers
    from tau.api.routes import fixtures, groups, scenes, control, circadian, labjack

    app.include_router(fixtures.router, prefix="/api/fixtures", tags=["fixtures"])
    app.include_router(groups.router, prefix="/api/groups", tags=["groups"])
    app.include_router(scenes.router, prefix="/api/scenes", tags=["scenes"])
    app.include_router(control.router, prefix="/api/control", tags=["control"])
    app.include_router(circadian.router, prefix="/api/circadian", tags=["circadian"])
    app.include_router(labjack.router, prefix="/api/labjack", tags=["hardware"])

    return app
