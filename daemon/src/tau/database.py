"""
Tau Database Connection and ORM Setup
"""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

logger = structlog.get_logger(__name__)

# Create declarative base for ORM models
Base = declarative_base()

# Import all models to register them with Base.metadata
# This must happen after Base is defined but before any database operations
def _import_models():
    """Import all ORM models to register them with Base.metadata"""
    try:
        from tau.models import (
            FixtureModel,
            Fixture,
            SwitchModel,
            Switch,
            Group,
            GroupFixture,
            GroupHierarchy,
            CircadianProfile,
            Scene,
            SceneValue,
            FixtureState,
            GroupState,
            SystemSetting,
            UpdateLog,
            UpdateStatus,
            Installation,
            VersionHistory,
            AvailableRelease,
            UpdateCheck,
            UpdateConfig,
            Override,
            TargetType,
            OverrideType,
            OverrideSource,
        )
        logger.debug("orm_models_imported")
    except ImportError as e:
        logger.warning("failed_to_import_models", error=str(e))

# Global engine and session maker
engine = None
async_session_maker = None


async def init_database(database_url: str):
    """Initialize database connection and create tables"""
    global engine, async_session_maker

    # Import models first to register them with Base.metadata
    _import_models()

    logger.info("connecting_to_database", url=database_url)

    # Convert database_url to string if it's a Pydantic URL object
    database_url_str = str(database_url)

    # Convert postgres:// to postgresql+asyncpg://
    if database_url_str.startswith("postgres://"):
        database_url_str = database_url_str.replace("postgres://", "postgresql+asyncpg://", 1)
    elif database_url_str.startswith("postgresql://"):
        database_url_str = database_url_str.replace("postgresql://", "postgresql+asyncpg://", 1)

    # Create async engine
    engine = create_async_engine(
        database_url_str,
        echo=False,  # Set to True for SQL query logging
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
    )

    # Create session maker
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Create tables (in production, use Alembic migrations instead)
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.create_all)

    logger.info("database_initialized")


async def close_database():
    """Close database connections"""
    global engine

    if engine:
        logger.info("closing_database_connections")
        await engine.dispose()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get an async database session for FastAPI dependency injection.

    This is an async generator that FastAPI's Depends() will handle automatically.
    Do NOT use @asynccontextmanager decorator here as FastAPI expects a plain async generator.
    """
    if async_session_maker is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get an async database session as a context manager for use in application code.

    Use this function with 'async with' in your application code:
        async with get_db_session() as session:
            # use session here

    For FastAPI dependency injection, use get_session() instead (without @asynccontextmanager).
    """
    if async_session_maker is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")

    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
