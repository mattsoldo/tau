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
        docs_url="/docs" if settings.api_docs_enabled else None,
        redoc_url="/redoc" if settings.api_docs_enabled else None,
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
    @app.get("/health")
    async def health_check():
        """Health check endpoint"""
        return {
            "status": "healthy",
            "version": settings.api_version,
            "service": "tau-daemon",
        }

    # Status endpoint with event loop statistics
    @app.get("/status")
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

        Clients can connect to receive real-time notifications about:
        - Fixture state changes
        - Group state changes
        - Scene recalls
        - Circadian adjustments
        - System status updates
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
    @app.get("/ws/stats")
    async def websocket_stats():
        """Get WebSocket connection statistics"""
        return connection_manager.get_statistics()

    # Register API routers
    from tau.api.routes import fixtures, groups, scenes, control, circadian

    app.include_router(fixtures.router, prefix="/api/fixtures", tags=["fixtures"])
    app.include_router(groups.router, prefix="/api/groups", tags=["groups"])
    app.include_router(scenes.router, prefix="/api/scenes", tags=["scenes"])
    app.include_router(control.router, prefix="/api/control", tags=["control"])
    app.include_router(circadian.router, prefix="/api/circadian", tags=["circadian"])

    return app
