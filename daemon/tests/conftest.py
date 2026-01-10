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
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Ensure src/ is on sys.path for direct pytest runs
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from tau.database import Base, get_session
from tau.config import Settings
from tau.api import create_app, get_daemon_instance, set_daemon_instance
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
    """Create an async Postgres engine for testing with isolated schema."""
    database_url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL for Postgres-backed tests.")

    database_url_str = str(database_url)
    if database_url_str.startswith("postgres://"):
        database_url_str = database_url_str.replace(
            "postgres://", "postgresql+asyncpg://", 1
        )
    elif database_url_str.startswith("postgresql://"):
        database_url_str = database_url_str.replace(
            "postgresql://", "postgresql+asyncpg://", 1
        )

    schema_name = f"test_{uuid.uuid4().hex}"

    admin_engine = create_async_engine(
        database_url_str,
        echo=False,
        poolclass=NullPool,
    )

    async with admin_engine.begin() as conn:
        await conn.exec_driver_sql(f'CREATE SCHEMA "{schema_name}"')

    await admin_engine.dispose()

    engine = create_async_engine(
        database_url_str,
        echo=False,
        poolclass=NullPool,
        connect_args={"server_settings": {"search_path": schema_name}},
    )

    # Import all models to register them with Base
    from tau.models import (
        FixtureModel, Fixture, SwitchModel, Switch,
        Group, GroupFixture, GroupHierarchy,
        CircadianProfile, Scene, SceneValue,
        FixtureState, GroupState,
        SystemSetting,
        Override, TargetType, OverrideType, OverrideSource,
    )
    from tau.models.software_update import (
        Installation, VersionHistory, AvailableRelease,
        UpdateCheck, UpdateConfig,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed required system settings for API tests
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with async_session_maker() as session:
        session.add_all([
            SystemSetting(
                key="dtw_enabled",
                value="true",
                value_type="bool",
                description="Enable dim-to-warm globally",
            ),
            SystemSetting(
                key="dtw_min_cct",
                value="1800",
                value_type="int",
                description="Minimum DTW color temperature",
            ),
            SystemSetting(
                key="dtw_max_cct",
                value="4000",
                value_type="int",
                description="Maximum DTW color temperature",
            ),
            SystemSetting(
                key="dtw_min_brightness",
                value="0.001",
                value_type="float",
                description="Minimum brightness floor for DTW curve",
            ),
            SystemSetting(
                key="dtw_curve",
                value="log",
                value_type="str",
                description="DTW curve type",
            ),
            SystemSetting(
                key="dtw_override_timeout",
                value="28800",
                value_type="int",
                description="DTW override timeout in seconds",
            ),
        ])
        await session.commit()

    yield engine

    async with engine.begin() as conn:
        await conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')

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
    database_url = os.getenv("TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or "postgresql+asyncpg://localhost/postgres"
    return Settings(
        database_url=database_url,
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

    state_manager = StateManager()
    daemon = SimpleNamespace(
        state_manager=state_manager,
        lighting_controller=None,
        event_loop=None,
        scheduler=None,
        persistence=None,
        hardware_manager=None,
    )
    set_daemon_instance(daemon)

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
    set_daemon_instance(None)


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
async def test_fixture(db_session: AsyncSession, test_fixture_model, test_app):
    """Create a test fixture."""
    from tau.models.fixtures import Fixture

    fixture = Fixture(
        name="Test Fixture",
        fixture_model_id=test_fixture_model.id,
        dmx_channel_start=1,
    )
    db_session.add(fixture)
    await db_session.commit()
    await db_session.refresh(fixture)

    daemon = get_daemon_instance()
    if daemon and daemon.state_manager:
        daemon.state_manager.register_fixture(fixture.id)
        state = daemon.state_manager.fixtures[fixture.id]
        state.dmx_channel_start = fixture.dmx_channel_start
        state.secondary_dmx_channel = fixture.secondary_dmx_channel
        state.dmx_universe = 0
        state.dmx_footprint = test_fixture_model.dmx_footprint
        state.fixture_model_id = test_fixture_model.id
        state.fixture_type = test_fixture_model.type
        state.cct_min = test_fixture_model.cct_min_kelvin
        state.cct_max = test_fixture_model.cct_max_kelvin
        state.warm_xy_x = test_fixture_model.warm_xy_x
        state.warm_xy_y = test_fixture_model.warm_xy_y
        state.cool_xy_x = test_fixture_model.cool_xy_x
        state.cool_xy_y = test_fixture_model.cool_xy_y
        state.warm_lumens = test_fixture_model.warm_lumens
        state.cool_lumens = test_fixture_model.cool_lumens
        state.gamma = test_fixture_model.gamma

    return fixture


@pytest_asyncio.fixture
async def test_tunable_fixture(db_session: AsyncSession, test_fixture_model, test_app):
    """Create a test tunable white fixture."""
    from tau.models.fixtures import Fixture

    fixture = Fixture(
        name="Test Tunable Fixture",
        fixture_model_id=test_fixture_model.id,
        dmx_channel_start=10,
        secondary_dmx_channel=11,
    )
    db_session.add(fixture)
    await db_session.commit()
    await db_session.refresh(fixture)

    daemon = get_daemon_instance()
    if daemon and daemon.state_manager:
        daemon.state_manager.register_fixture(fixture.id)
        state = daemon.state_manager.fixtures[fixture.id]
        state.dmx_channel_start = fixture.dmx_channel_start
        state.secondary_dmx_channel = fixture.secondary_dmx_channel
        state.dmx_universe = 0
        state.dmx_footprint = test_fixture_model.dmx_footprint
        state.fixture_model_id = test_fixture_model.id
        state.fixture_type = test_fixture_model.type
        state.cct_min = test_fixture_model.cct_min_kelvin
        state.cct_max = test_fixture_model.cct_max_kelvin
        state.warm_xy_x = test_fixture_model.warm_xy_x
        state.warm_xy_y = test_fixture_model.warm_xy_y
        state.cool_xy_x = test_fixture_model.cool_xy_x
        state.cool_xy_y = test_fixture_model.cool_xy_y
        state.warm_lumens = test_fixture_model.warm_lumens
        state.cool_lumens = test_fixture_model.cool_lumens
        state.gamma = test_fixture_model.gamma

    return fixture


@pytest_asyncio.fixture
async def test_group(db_session: AsyncSession, test_app):
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

    daemon = get_daemon_instance()
    if daemon and daemon.state_manager:
        daemon.state_manager.register_group(group.id)

    return group


@pytest_asyncio.fixture
async def test_fixtures_in_group(db_session: AsyncSession, test_group, test_fixture_model, test_app):
    """Create multiple test fixtures in a group."""
    from tau.models.fixtures import Fixture
    from tau.models.groups import GroupFixture

    fixtures = []
    for i in range(3):
        fixture = Fixture(
            name=f"Test Fixture {i+1}",
            fixture_model_id=test_fixture_model.id,
            dmx_channel_start=(i+1) * 10,
        )
        db_session.add(fixture)
        await db_session.commit()
        await db_session.refresh(fixture)

        # Add to group
        membership = GroupFixture(
            fixture_id=fixture.id,
            group_id=test_group.id,
        )
        db_session.add(membership)
        fixtures.append(fixture)

        daemon = get_daemon_instance()
        if daemon and daemon.state_manager:
            daemon.state_manager.register_fixture(fixture.id)
            state = daemon.state_manager.fixtures[fixture.id]
            state.dmx_channel_start = fixture.dmx_channel_start
            state.secondary_dmx_channel = fixture.secondary_dmx_channel
            state.dmx_universe = 0
            state.dmx_footprint = test_fixture_model.dmx_footprint
            state.fixture_model_id = test_fixture_model.id
            state.fixture_type = test_fixture_model.type
            state.cct_min = test_fixture_model.cct_min_kelvin
            state.cct_max = test_fixture_model.cct_max_kelvin
            state.warm_xy_x = test_fixture_model.warm_xy_x
            state.warm_xy_y = test_fixture_model.warm_xy_y
            state.cool_xy_x = test_fixture_model.cool_xy_x
            state.cool_xy_y = test_fixture_model.cool_xy_y
            state.warm_lumens = test_fixture_model.warm_lumens
            state.cool_lumens = test_fixture_model.cool_lumens
            state.gamma = test_fixture_model.gamma
            daemon.state_manager.add_fixture_to_group(fixture.id, test_group.id)

    await db_session.commit()
    return fixtures
