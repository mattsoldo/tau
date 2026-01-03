"""
Integration tests for control API endpoints.

These tests verify that:
1. Fixture control commands are properly processed
2. Group control commands apply to all fixtures in the group
3. Control loop handles commands without errors
4. Overrides are created with proper expiration times
"""
import pytest
from httpx import AsyncClient
from datetime import datetime, timedelta

from tau.models.fixtures import Fixture
from tau.models.groups import Group
from tau.models.fixture_group_membership import FixtureGroupMembership
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_fixture_control_creates_override(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_fixture: Fixture,
):
    """Test that fixture control creates an override with expiration"""
    # Send control command
    response = await async_client.post(
        f"/api/control/fixtures/{test_fixture.id}",
        json={"brightness": 0.7},
    )

    assert response.status_code == 200
    data = response.json()

    # Verify response
    assert data["goal_brightness"] == 0.7
    assert data["override_active"] is True
    assert "override_expires_at" in data

    # Verify expiration is ~8 hours in the future
    expires_at = data["override_expires_at"]
    now = datetime.now().timestamp()
    time_until_expiry = expires_at - now

    # Should be approximately 8 hours (28800 seconds), allow 60s tolerance
    assert 28700 < time_until_expiry < 28900


@pytest.mark.asyncio
async def test_fixture_control_with_cct(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_tunable_fixture: Fixture,
):
    """Test fixture control with color temperature"""
    # Send control command with both brightness and CCT
    response = await client.post(
        f"/api/control/fixtures/{test_tunable_fixture.id}",
        json={
            "brightness": 0.5,
            "color_temp": 4000,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["goal_brightness"] == 0.5
    assert data["goal_color_temp"] == 4000
    assert data["override_active"] is True


@pytest.mark.asyncio
async def test_group_control_applies_to_all_fixtures(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_group: Group,
    test_fixtures_in_group: list[Fixture],
):
    """Test that group control applies to all fixtures in the group"""
    # Send group control command
    response = await client.post(
        f"/api/control/groups/{test_group.id}",
        json={"brightness": 0.8},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Group control applied successfully"

    # Verify all fixtures in group have the new brightness
    for fixture in test_fixtures_in_group:
        state_response = await client.get(f"/api/fixtures/{fixture.id}/state")
        assert state_response.status_code == 200
        state_data = state_response.json()

        # Goal brightness should be set to 0.8 (or 80% in 0-100 scale if using that)
        assert state_data["goal_brightness"] == 0.8 or state_data["goal_brightness"] == 80


@pytest.mark.asyncio
async def test_group_control_clears_overrides(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_group: Group,
    test_fixtures_in_group: list[Fixture],
):
    """Test that group control clears individual fixture overrides"""
    # First, set individual fixture overrides
    for fixture in test_fixtures_in_group:
        await async_client.post(
            f"/api/control/fixtures/{fixture.id}",
            json={"brightness": 0.3},
        )

    # Then apply group control
    response = await client.post(
        f"/api/control/groups/{test_group.id}",
        json={"brightness": 0.9},
    )

    assert response.status_code == 200
    data = response.json()

    # Should report that overrides were cleared
    assert "overrides_cleared" in data
    assert data["overrides_cleared"] >= len(test_fixtures_in_group)


@pytest.mark.asyncio
async def test_control_nonexistent_fixture_returns_404(
    async_client: AsyncClient,
):
    """Test that controlling a non-existent fixture returns 404"""
    response = await client.post(
        "/api/control/fixtures/99999",
        json={"brightness": 0.5},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_control_nonexistent_group_returns_404(
    async_client: AsyncClient,
):
    """Test that controlling a non-existent group returns 404"""
    response = await client.post(
        "/api/control/groups/99999",
        json={"brightness": 0.5},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_all_off_command(
    async_client: AsyncClient,
    test_fixtures_in_group: list[Fixture],
):
    """Test the all-off panic command"""
    # First set fixtures to on
    for fixture in test_fixtures_in_group:
        await async_client.post(
            f"/api/control/fixtures/{fixture.id}",
            json={"brightness": 0.8},
        )

    # Send all-off command
    response = await client.post("/api/control/all-off")
    assert response.status_code == 200

    # Verify all fixtures are off (goal_brightness = 0)
    for fixture in test_fixtures_in_group:
        state_response = await client.get(f"/api/fixtures/{fixture.id}/state")
        state_data = state_response.json()
        assert state_data["goal_brightness"] == 0


@pytest.mark.asyncio
async def test_panic_all_on_command(
    async_client: AsyncClient,
    test_fixtures_in_group: list[Fixture],
):
    """Test the panic all-on command"""
    # First set fixtures to off
    await async_client.post("/api/control/all-off")

    # Send panic (all-on) command
    response = await client.post("/api/control/panic")
    assert response.status_code == 200

    # Verify all fixtures are on (goal_brightness = 1.0 or 100)
    for fixture in test_fixtures_in_group:
        state_response = await client.get(f"/api/fixtures/{fixture.id}/state")
        state_data = state_response.json()
        assert state_data["goal_brightness"] > 0.9 or state_data["goal_brightness"] >= 90
