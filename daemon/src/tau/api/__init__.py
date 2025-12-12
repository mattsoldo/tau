"""
Tau Lighting Control API
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tau.config import Settings


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

    # TODO: Register API routers in Phase 5
    # from tau.api.routes import fixtures, groups, scenes, control
    # app.include_router(fixtures.router, prefix="/api/fixtures", tags=["fixtures"])
    # app.include_router(groups.router, prefix="/api/groups", tags=["groups"])
    # app.include_router(scenes.router, prefix="/api/scenes", tags=["scenes"])
    # app.include_router(control.router, prefix="/api/control", tags=["control"])

    return app
