"""
Tau Lighting Control API
"""
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tau.config import Settings

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

    # TODO: Register API routers in Phase 5
    # from tau.api.routes import fixtures, groups, scenes, control
    # app.include_router(fixtures.router, prefix="/api/fixtures", tags=["fixtures"])
    # app.include_router(groups.router, prefix="/api/groups", tags=["groups"])
    # app.include_router(scenes.router, prefix="/api/scenes", tags=["scenes"])
    # app.include_router(control.router, prefix="/api/control", tags=["control"])

    return app
