import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tau.logic.scenes import SceneEngine
from tau.models.fixtures import FixtureModel, Fixture
from tau.models.groups import Group, GroupFixture
from tau.models.scenes import SceneValue
import tau.database as db_module


@pytest_asyncio.fixture
async def scene_engine(async_engine, state_manager, monkeypatch):
    test_session_maker = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    monkeypatch.setattr(db_module, "async_session_maker", test_session_maker)
    return SceneEngine(state_manager)


async def _seed_scene_fixtures(db_session):
    model = FixtureModel(
        id=1,
        manufacturer="TestCo",
        model="Model A",
        type="simple_dimmable",
        dmx_footprint=1,
    )
    fixtures = [
        Fixture(id=1, name="Fixture 1", fixture_model_id=1, dmx_channel_start=1),
        Fixture(id=2, name="Fixture 2", fixture_model_id=1, dmx_channel_start=2),
        Fixture(id=3, name="Fixture 3", fixture_model_id=1, dmx_channel_start=3),
    ]
    groups = [
        Group(id=1, name="Group 1"),
        Group(id=2, name="Group 2"),
    ]
    group_fixtures = [
        GroupFixture(group_id=1, fixture_id=1),
        GroupFixture(group_id=1, fixture_id=2),
        GroupFixture(group_id=2, fixture_id=3),
    ]

    db_session.add(model)
    db_session.add_all(fixtures)
    db_session.add_all(groups)
    db_session.add_all(group_fixtures)
    await db_session.commit()


def _seed_state_manager(state_manager):
    for fixture_id, brightness, cct in [
        (1, 0.2, 2700),
        (2, 0.5, 3000),
        (3, 0.8, 3500),
    ]:
        state_manager.register_fixture(fixture_id)
        fixture_state = state_manager.fixtures[fixture_id]
        fixture_state.goal_brightness = brightness
        fixture_state.current_brightness = brightness
        fixture_state.goal_color_temp = cct
        fixture_state.current_color_temp = cct


@pytest.mark.asyncio
async def test_capture_scene_includes_and_excludes(db_session, scene_engine, state_manager):
    await _seed_scene_fixtures(db_session)
    _seed_state_manager(state_manager)

    scene_id = await scene_engine.capture_scene(
        name="Include Group 1 + Fixture 3",
        fixture_ids=[3],
        include_group_ids=[1],
        exclude_fixture_ids=[2],
    )

    assert scene_id is not None

    result = await db_session.execute(
        SceneValue.__table__.select().where(SceneValue.scene_id == scene_id)
    )
    fixture_ids = {row.fixture_id for row in result.fetchall()}
    assert fixture_ids == {1, 3}


@pytest.mark.asyncio
async def test_capture_scene_excluded_group_wins(db_session, scene_engine, state_manager):
    await _seed_scene_fixtures(db_session)
    _seed_state_manager(state_manager)

    scene_id = await scene_engine.capture_scene(
        name="Exclude Group 1",
        fixture_ids=[3],
        include_group_ids=[1],
        exclude_group_ids=[1],
    )

    assert scene_id is not None

    result = await db_session.execute(
        SceneValue.__table__.select().where(SceneValue.scene_id == scene_id)
    )
    fixture_ids = {row.fixture_id for row in result.fetchall()}
    assert fixture_ids == {3}


@pytest.mark.asyncio
async def test_capture_scene_default_all_minus_excludes(db_session, scene_engine, state_manager):
    await _seed_scene_fixtures(db_session)
    _seed_state_manager(state_manager)

    scene_id = await scene_engine.capture_scene(
        name="Exclude Group 2",
        exclude_group_ids=[2],
    )

    assert scene_id is not None

    result = await db_session.execute(
        SceneValue.__table__.select().where(SceneValue.scene_id == scene_id)
    )
    fixture_ids = {row.fixture_id for row in result.fetchall()}
    assert fixture_ids == {1, 2}
