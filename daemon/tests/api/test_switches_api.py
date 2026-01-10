"""
API tests for switches endpoints, including double-tap scene configuration.
"""
import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def switch_dependencies(async_client, sample_fixture_model_data):
    model_response = await async_client.post(
        "/api/switches/models",
        json={
            "manufacturer": "TestCo",
            "model": "SW-1",
            "input_type": "retractive",
            "requires_digital_pin": True,
        },
    )
    assert model_response.status_code == 201

    fixture_model_response = await async_client.post(
        "/api/fixtures/models",
        json=sample_fixture_model_data,
    )
    assert fixture_model_response.status_code == 201
    fixture_model_id = fixture_model_response.json()["id"]

    fixture_response = await async_client.post(
        "/api/fixtures/",
        json={
            "name": "Switch Fixture",
            "fixture_model_id": fixture_model_id,
            "dmx_channel_start": 1,
        },
    )
    assert fixture_response.status_code == 201

    scene_response = await async_client.post(
        "/api/scenes/",
        json={"name": "Movie Night"},
    )
    assert scene_response.status_code == 201

    return {
        "switch_model": model_response.json(),
        "fixture": fixture_response.json(),
        "scene": scene_response.json(),
    }


@pytest.mark.asyncio
async def test_create_switch_with_double_tap_scene(async_client, switch_dependencies):
    response = await async_client.post(
        "/api/switches/",
        json={
            "name": "Living Room Switch",
            "switch_model_id": switch_dependencies["switch_model"]["id"],
            "labjack_digital_pin": 2,
            "switch_type": "normally-closed",
            "invert_reading": False,
            "target_fixture_id": switch_dependencies["fixture"]["id"],
            "double_tap_scene_id": switch_dependencies["scene"]["id"],
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["double_tap_scene_id"] == switch_dependencies["scene"]["id"]


@pytest.mark.asyncio
async def test_update_switch_rejects_unknown_scene(async_client, switch_dependencies):
    create_response = await async_client.post(
        "/api/switches/",
        json={
            "name": "Entry Switch",
            "switch_model_id": switch_dependencies["switch_model"]["id"],
            "labjack_digital_pin": 3,
            "switch_type": "normally-closed",
            "invert_reading": False,
            "target_fixture_id": switch_dependencies["fixture"]["id"],
        },
    )
    assert create_response.status_code == 201
    switch_id = create_response.json()["id"]

    response = await async_client.patch(
        f"/api/switches/{switch_id}",
        json={"double_tap_scene_id": 99999},
    )

    assert response.status_code == 404
