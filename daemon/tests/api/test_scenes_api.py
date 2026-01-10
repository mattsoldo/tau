"""
API tests for scenes endpoints.
"""
from types import SimpleNamespace

import pytest

from tau.api import get_daemon_instance
from tau.logic.scenes import SceneEngine
from tau.models.scenes import Scene, SceneValue
from tau.models.state import GroupState


@pytest.fixture
def scene_engine_controller(test_app):
    """Attach a SceneEngine to the daemon for scene API tests."""
    daemon = get_daemon_instance()
    previous = daemon.lighting_controller
    daemon.lighting_controller = SimpleNamespace(
        scenes=SceneEngine(daemon.state_manager)
    )
    yield daemon.lighting_controller.scenes
    daemon.lighting_controller = previous


@pytest.mark.asyncio
async def test_capture_scene_snapshots_and_filters(
    async_client,
    test_group,
    test_fixtures_in_group,
    test_fixture,
    scene_engine_controller,
):
    daemon = get_daemon_instance()

    brightness_map = {
        test_fixtures_in_group[0].id: 0.2,
        test_fixtures_in_group[1].id: 0.5,
        test_fixtures_in_group[2].id: 0.8,
        test_fixture.id: 0.35,
    }
    cct_map = {
        test_fixtures_in_group[0].id: 2700,
        test_fixtures_in_group[1].id: 3000,
        test_fixtures_in_group[2].id: 3500,
        test_fixture.id: 2800,
    }

    for fixture_id, brightness in brightness_map.items():
        state = daemon.state_manager.fixtures[fixture_id]
        state.current_brightness = brightness
        state.current_color_temp = cct_map[fixture_id]

    excluded_fixture = test_fixtures_in_group[1]

    response = await async_client.post(
        "/api/scenes/capture",
        json={
            "name": "Snapshot Scene",
            "include_group_ids": [test_group.id],
            "fixture_ids": [test_fixture.id],
            "exclude_fixture_ids": [excluded_fixture.id],
        },
    )

    assert response.status_code == 201
    data = response.json()

    fixture_ids = {value["fixture_id"] for value in data["values"]}
    expected_ids = {
        test_fixtures_in_group[0].id,
        test_fixtures_in_group[2].id,
        test_fixture.id,
    }
    assert fixture_ids == expected_ids

    values_by_fixture = {value["fixture_id"]: value for value in data["values"]}
    included_fixture = test_fixtures_in_group[0].id
    assert values_by_fixture[included_fixture]["target_brightness"] == int(
        brightness_map[included_fixture] * 1000
    )
    assert values_by_fixture[included_fixture]["target_cct_kelvin"] == cct_map[included_fixture]


@pytest.mark.asyncio
async def test_recall_scene_updates_fixture_and_group_state(
    async_client,
    db_session,
    test_group,
    test_fixtures_in_group,
    scene_engine_controller,
):
    daemon = get_daemon_instance()
    fixture = test_fixtures_in_group[0]

    scene = Scene(
        name="Evening Scene",
        scope_group_id=test_group.id,
    )
    db_session.add(scene)
    await db_session.commit()
    await db_session.refresh(scene)

    db_session.add(
        SceneValue(
            scene_id=scene.id,
            fixture_id=fixture.id,
            target_brightness=420,
            target_cct_kelvin=3000,
        )
    )
    await db_session.commit()

    state = daemon.state_manager.fixtures[fixture.id]
    state.current_brightness = 0.0
    state.current_color_temp = 2700

    response = await async_client.post(
        "/api/scenes/recall",
        json={"scene_id": scene.id},
    )

    assert response.status_code == 200

    assert daemon.state_manager.fixtures[fixture.id].goal_brightness == 0.42
    assert daemon.state_manager.fixtures[fixture.id].goal_color_temp == 3000

    group_state = await db_session.get(GroupState, test_group.id)
    assert group_state is not None
    assert group_state.last_active_scene_id == scene.id
