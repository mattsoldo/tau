"""
Shared test fixtures for Tau daemon tests.

Provides fixtures for:
- Database sessions (async)
- API client (FastAPI TestClient)
- State manager instances
- Mock hardware interfaces
- Sample data
"""
import asyncio
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from tau.database import Base, get_session
from tau.config import Settings
from tau.api import create_app
from tau.control.state_manager import StateManager, FixtureStateData, GroupStateData
from tau.control.scheduler import Scheduler
from tau.hardware.labjack_mock import LabJackMock as MockLabJackInterface
from tau.hardware.ola_mock import OLAMock as MockOLAInterface


# ============================================================================
# Event Loop Fixture
# ============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================================
# Database Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def async_engine():
    """Create an async SQLite engine for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    # Import all models to register them with Base
    from tau.models import (
        FixtureModel, Fixture, SwitchModel, Switch,
        Group, GroupFixture, GroupHierarchy,
        CircadianProfile, Scene, SceneValue,
        FixtureState, GroupState,
    )
    from tau.models.software_update import (
        Installation, VersionHistory, AvailableRelease,
        UpdateCheck, UpdateConfig,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create an async database session for testing."""
    async_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        yield session


# ============================================================================
# Settings and App Fixtures
# ============================================================================

@pytest.fixture
def test_settings() -> Settings:
    """Create test settings."""
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        log_level="DEBUG",
        api_docs_enabled=True,
        cors_origins=["*"],
    )


@pytest_asyncio.fixture
async def test_app(async_engine, test_settings):
    """Create a FastAPI test application with in-memory database."""
    from tau.database import async_session_maker as global_session_maker
    import tau.database as db_module

    # Create session maker for our test engine
    test_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    # Override the database module's session maker
    original_session_maker = db_module.async_session_maker
    db_module.async_session_maker = test_session_maker

    app = create_app(test_settings)

    # Override the get_session dependency
    async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
        async with test_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    app.dependency_overrides[get_session] = override_get_session

    yield app

    # Restore original session maker
    db_module.async_session_maker = original_session_maker


@pytest_asyncio.fixture
async def async_client(test_app) -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for API testing."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://test"
    ) as client:
        yield client


# ============================================================================
# State Manager Fixtures
# ============================================================================

@pytest.fixture
def state_manager() -> StateManager:
    """Create a fresh StateManager instance."""
    manager = StateManager()
    yield manager
    manager.clear()


@pytest.fixture
def populated_state_manager(state_manager: StateManager) -> StateManager:
    """Create a StateManager with sample fixtures and groups."""
    # Register fixtures
    for i in range(1, 4):
        state_manager.register_fixture(i)
        fixture = state_manager.fixtures[i]
        fixture.dmx_channel_start = i * 10
        fixture.dmx_universe = 0
        fixture.cct_min = 2700
        fixture.cct_max = 6500

    # Register groups
    for i in range(1, 3):
        state_manager.register_group(i)

    # Add fixtures to groups
    state_manager.add_fixture_to_group(1, 1)
    state_manager.add_fixture_to_group(2, 1)
    state_manager.add_fixture_to_group(3, 2)

    return state_manager


# ============================================================================
# Scheduler Fixtures
# ============================================================================

@pytest.fixture
def scheduler() -> Scheduler:
    """Create a fresh Scheduler instance."""
    sched = Scheduler()
    yield sched
    sched.clear()


# ============================================================================
# Hardware Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_labjack() -> MockLabJackInterface:
    """Create a mock LabJack interface."""
    return MockLabJackInterface()


@pytest.fixture
def mock_ola() -> MockOLAInterface:
    """Create a mock OLA interface."""
    return MockOLAInterface()


# ============================================================================
# Sample Data Fixtures
# ============================================================================

@pytest.fixture
def sample_fixture_model_data() -> dict:
    """Sample fixture model data for testing."""
    return {
        "manufacturer": "Test Manufacturer",
        "model": "TW-100",
        "description": "Test tunable white fixture",
        "type": "tunable_white",
        "dmx_footprint": 2,
        "cct_min_kelvin": 2700,
        "cct_max_kelvin": 6500,
        "warm_xy_x": 0.5268,
        "warm_xy_y": 0.4133,
        "cool_xy_x": 0.3135,
        "cool_xy_y": 0.3237,
        "warm_lumens": 800,
        "cool_lumens": 900,
        "gamma": 2.2,
    }


@pytest.fixture
def sample_fixture_data() -> dict:
    """Sample fixture data for testing."""
    return {
        "name": "Test Fixture",
        "dmx_channel_start": 1,
        "room": "Living Room",
        "notes": "Test fixture notes",
    }


@pytest.fixture
def sample_group_data() -> dict:
    """Sample group data for testing."""
    return {
        "name": "Test Group",
        "description": "Test group description",
        "circadian_enabled": False,
        "circadian_profile_id": None,
    }


@pytest.fixture
def sample_circadian_profile_data() -> dict:
    """Sample circadian profile data for testing."""
    return {
        "name": "Test Profile",
        "description": "Test circadian profile",
        "curve_points": {
            "06:00": {"brightness": 200, "cct": 2700},
            "12:00": {"brightness": 1000, "cct": 5000},
            "18:00": {"brightness": 500, "cct": 3500},
            "22:00": {"brightness": 100, "cct": 2700},
        },
    }


# ============================================================================
# Utility Fixtures
# ============================================================================

@pytest.fixture
def mock_time():
    """Create a controllable mock time for testing transitions."""
    import time
    current_time = 1000.0

    class MockTime:
        def __init__(self):
            self.current = current_time

        def time(self):
            return self.current

        def advance(self, seconds: float):
            self.current += seconds

    return MockTime()


# ============================================================================
# Model Instance Fixtures
# ============================================================================

@pytest_asyncio.fixture
async def test_fixture_model(db_session: AsyncSession):
    """Create a test fixture model."""
    from tau.models.fixtures import FixtureModel

    model = FixtureModel(
        manufacturer="Test Manufacturer",
        model="TW-100",
        type="tunable_white",
        dmx_footprint=2,
        cct_min_kelvin=2700,
        cct_max_kelvin=6500,
        warm_xy_x=0.5268,
        warm_xy_y=0.4133,
        cool_xy_x=0.3135,
        cool_xy_y=0.3237,
        warm_lumens=800,
        cool_lumens=900,
        gamma=2.2,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)
    return model


@pytest_asyncio.fixture
async def test_fixture(db_session: AsyncSession, test_fixture_model):
    """Create a test fixture."""
    from tau.models.fixtures import Fixture

    fixture = Fixture(
        name="Test Fixture",
        fixture_model_id=test_fixture_model.id,
        dmx_channel_start=1,
        dmx_universe=0,
        room="Living Room",
    )
    db_session.add(fixture)
    await db_session.commit()
    await db_session.refresh(fixture)
    return fixture


@pytest_asyncio.fixture
async def test_tunable_fixture(db_session: AsyncSession, test_fixture_model):
    """Create a test tunable white fixture."""
    from tau.models.fixtures import Fixture

    fixture = Fixture(
        name="Test Tunable Fixture",
        fixture_model_id=test_fixture_model.id,
        dmx_channel_start=10,
        dmx_universe=0,
        secondary_dmx_channel=11,
        room="Bedroom",
    )
    db_session.add(fixture)
    await db_session.commit()
    await db_session.refresh(fixture)
    return fixture


@pytest_asyncio.fixture
async def test_group(db_session: AsyncSession):
    """Create a test group."""
    from tau.models.groups import Group

    group = Group(
        name="Test Group",
        description="Test group for integration tests",
        is_system=False,
    )
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)
    return group


@pytest_asyncio.fixture
async def test_fixtures_in_group(db_session: AsyncSession, test_group, test_fixture_model):
    """Create multiple test fixtures in a group."""
    from tau.models.fixtures import Fixture
    from tau.models.fixture_group_membership import FixtureGroupMembership

    fixtures = []
    for i in range(3):
        fixture = Fixture(
            name=f"Test Fixture {i+1}",
            fixture_model_id=test_fixture_model.id,
            dmx_channel_start=(i+1) * 10,
            dmx_universe=0,
            room="Test Room",
        )
        db_session.add(fixture)
        await db_session.commit()
        await db_session.refresh(fixture)

        # Add to group
        membership = FixtureGroupMembership(
            fixture_id=fixture.id,
            group_id=test_group.id,
        )
        db_session.add(membership)
        fixtures.append(fixture)

    await db_session.commit()
    return fixtures
