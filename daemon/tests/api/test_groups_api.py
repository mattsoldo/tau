"""
API tests for groups endpoints.

Tests CRUD operations for groups and fixture membership.
"""
from datetime import datetime
from unittest.mock import patch
import pytest
import pytest_asyncio


class TestGroupsAPI:
    """Tests for /api/groups endpoints."""

    @pytest.mark.asyncio
    async def test_list_groups_empty(self, async_client):
        """Test listing groups when none exist."""
        response = await async_client.get("/api/groups/")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_create_group(self, async_client, sample_group_data):
        """Test creating a group."""
        response = await async_client.post("/api/groups/", json=sample_group_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_group_data["name"]
        assert data["description"] == sample_group_data["description"]
        assert data["circadian_enabled"] == sample_group_data["circadian_enabled"]
        assert data["id"] is not None

    @pytest.mark.asyncio
    async def test_create_group_minimal(self, async_client):
        """Test creating a group with minimal data."""
        response = await async_client.post(
            "/api/groups/",
            json={"name": "Minimal Group"}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Minimal Group"
        assert data["description"] is None
        assert data["circadian_enabled"] is False

    @pytest.mark.asyncio
    async def test_list_groups(self, async_client, sample_group_data):
        """Test listing groups after creating one."""
        await async_client.post("/api/groups/", json=sample_group_data)

        response = await async_client.get("/api/groups/")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == sample_group_data["name"]

    @pytest.mark.asyncio
    async def test_get_group(self, async_client, sample_group_data):
        """Test getting a specific group."""
        create_response = await async_client.post("/api/groups/", json=sample_group_data)
        group_id = create_response.json()["id"]

        response = await async_client.get(f"/api/groups/{group_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == group_id
        assert data["name"] == sample_group_data["name"]

    @pytest.mark.asyncio
    async def test_get_group_not_found(self, async_client):
        """Test getting a non-existent group."""
        response = await async_client.get("/api/groups/99999")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_group(self, async_client, sample_group_data):
        """Test updating a group."""
        create_response = await async_client.post("/api/groups/", json=sample_group_data)
        group_id = create_response.json()["id"]

        # Update the group
        update_data = {
            "name": "Updated Group Name",
            "circadian_enabled": True
        }
        response = await async_client.patch(f"/api/groups/{group_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Group Name"
        assert data["circadian_enabled"] is True
        # Original description should be preserved
        assert data["description"] == sample_group_data["description"]

    @pytest.mark.asyncio
    async def test_delete_group(self, async_client, sample_group_data):
        """Test deleting a group."""
        create_response = await async_client.post("/api/groups/", json=sample_group_data)
        group_id = create_response.json()["id"]

        # Delete the group
        response = await async_client.delete(f"/api/groups/{group_id}")

        assert response.status_code == 204

        # Verify it's gone
        get_response = await async_client.get(f"/api/groups/{group_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_group_not_found(self, async_client):
        """Test deleting a non-existent group."""
        response = await async_client.delete("/api/groups/99999")

        assert response.status_code == 404


class TestGroupFixtureMembership:
    """Tests for group fixture membership endpoints."""

    @pytest_asyncio.fixture
    async def setup_group_and_fixtures(self, async_client, sample_fixture_model_data):
        """Set up a group with fixtures for testing membership."""
        # Create a fixture model
        model_response = await async_client.post(
            "/api/fixtures/models",
            json=sample_fixture_model_data
        )
        model_id = model_response.json()["id"]

        # Create fixtures
        fixtures = []
        for i in range(3):
            fixture_response = await async_client.post(
                "/api/fixtures/",
                json={
                    "name": f"Fixture {i+1}",
                    "fixture_model_id": model_id,
                    "dmx_channel_start": (i + 1) * 10
                }
            )
            fixtures.append(fixture_response.json())

        # Create a group
        group_response = await async_client.post(
            "/api/groups/",
            json={"name": "Test Group"}
        )
        group = group_response.json()

        return {"group": group, "fixtures": fixtures}

    @pytest.mark.asyncio
    async def test_list_group_fixtures_empty(self, async_client, sample_group_data):
        """Test listing fixtures for a group with no fixtures."""
        create_response = await async_client.post("/api/groups/", json=sample_group_data)
        group_id = create_response.json()["id"]

        response = await async_client.get(f"/api/groups/{group_id}/fixtures")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_add_fixture_to_group(self, async_client, setup_group_and_fixtures):
        """Test adding a fixture to a group."""
        data = setup_group_and_fixtures
        group_id = data["group"]["id"]
        fixture_id = data["fixtures"][0]["id"]

        response = await async_client.post(
            f"/api/groups/{group_id}/fixtures",
            json={"fixture_id": fixture_id}
        )

        assert response.status_code == 201

        # Verify fixture is in group
        list_response = await async_client.get(f"/api/groups/{group_id}/fixtures")
        fixtures = list_response.json()
        assert len(fixtures) == 1
        assert fixtures[0]["id"] == fixture_id

    @pytest.mark.asyncio
    async def test_add_fixture_to_group_already_member(self, async_client, setup_group_and_fixtures):
        """Test adding a fixture that's already in the group."""
        data = setup_group_and_fixtures
        group_id = data["group"]["id"]
        fixture_id = data["fixtures"][0]["id"]

        # Add fixture
        await async_client.post(
            f"/api/groups/{group_id}/fixtures",
            json={"fixture_id": fixture_id}
        )

        # Try to add again
        response = await async_client.post(
            f"/api/groups/{group_id}/fixtures",
            json={"fixture_id": fixture_id}
        )

        assert response.status_code == 409
        assert "already in group" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_add_fixture_to_nonexistent_group(self, async_client, setup_group_and_fixtures):
        """Test adding a fixture to a non-existent group."""
        fixture_id = setup_group_and_fixtures["fixtures"][0]["id"]

        response = await async_client.post(
            "/api/groups/99999/fixtures",
            json={"fixture_id": fixture_id}
        )

        assert response.status_code == 404
        assert "group not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_add_nonexistent_fixture_to_group(self, async_client, setup_group_and_fixtures):
        """Test adding a non-existent fixture to a group."""
        group_id = setup_group_and_fixtures["group"]["id"]

        response = await async_client.post(
            f"/api/groups/{group_id}/fixtures",
            json={"fixture_id": 99999}
        )

        assert response.status_code == 404
        assert "fixture not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_remove_fixture_from_group(self, async_client, setup_group_and_fixtures):
        """Test removing a fixture from a group."""
        data = setup_group_and_fixtures
        group_id = data["group"]["id"]
        fixture_id = data["fixtures"][0]["id"]

        # Add fixture first
        await async_client.post(
            f"/api/groups/{group_id}/fixtures",
            json={"fixture_id": fixture_id}
        )

        # Remove fixture
        response = await async_client.delete(f"/api/groups/{group_id}/fixtures/{fixture_id}")

        assert response.status_code == 204

        # Verify fixture is no longer in group
        list_response = await async_client.get(f"/api/groups/{group_id}/fixtures")
        assert list_response.json() == []

    @pytest.mark.asyncio
    async def test_remove_fixture_not_in_group(self, async_client, setup_group_and_fixtures):
        """Test removing a fixture that's not in the group."""
        data = setup_group_and_fixtures
        group_id = data["group"]["id"]
        fixture_id = data["fixtures"][0]["id"]

        response = await async_client.delete(f"/api/groups/{group_id}/fixtures/{fixture_id}")

        assert response.status_code == 404
        assert "not in group" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_list_multiple_fixtures_in_group(self, async_client, setup_group_and_fixtures):
        """Test listing multiple fixtures in a group."""
        data = setup_group_and_fixtures
        group_id = data["group"]["id"]

        # Add all fixtures to group
        for fixture in data["fixtures"]:
            await async_client.post(
                f"/api/groups/{group_id}/fixtures",
                json={"fixture_id": fixture["id"]}
            )

        # List fixtures
        response = await async_client.get(f"/api/groups/{group_id}/fixtures")

        assert response.status_code == 200
        fixtures = response.json()
        assert len(fixtures) == 3


class TestGroupSleepLock:
    """Tests for group sleep lock functionality."""

    @pytest.mark.asyncio
    async def test_create_group_with_sleep_lock(self, async_client):
        """Test creating a group with sleep lock enabled."""
        response = await async_client.post(
            "/api/groups/",
            json={
                "name": "Bedroom",
                "sleep_lock_enabled": True,
                "sleep_lock_start_time": "22:00",
                "sleep_lock_end_time": "07:00",
                "sleep_lock_unlock_duration_minutes": 5,
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Bedroom"
        assert data["sleep_lock_enabled"] is True
        assert data["sleep_lock_start_time"] == "22:00"
        assert data["sleep_lock_end_time"] == "07:00"
        assert data["sleep_lock_unlock_duration_minutes"] == 5
        # sleep_lock_active should be computed based on current time
        assert "sleep_lock_active" in data

    @pytest.mark.asyncio
    async def test_create_group_sleep_lock_missing_end_time(self, async_client):
        """Test that enabling sleep lock without end time fails validation."""
        response = await async_client.post(
            "/api/groups/",
            json={
                "name": "Invalid Group",
                "sleep_lock_enabled": True,
                "sleep_lock_start_time": "22:00",
                # Missing end time
            }
        )

        assert response.status_code == 422
        error_detail = response.json()["detail"]
        # Check that the error mentions the validation issue
        assert any("start and end times" in str(err).lower() for err in error_detail) or \
               any("value_error" in str(err).lower() for err in error_detail)

    @pytest.mark.asyncio
    async def test_create_group_sleep_lock_missing_start_time(self, async_client):
        """Test that enabling sleep lock without start time fails validation."""
        response = await async_client.post(
            "/api/groups/",
            json={
                "name": "Invalid Group",
                "sleep_lock_enabled": True,
                "sleep_lock_end_time": "07:00",
                # Missing start time
            }
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_group_sleep_lock_invalid_time_format(self, async_client):
        """Test that invalid time format fails validation."""
        response = await async_client.post(
            "/api/groups/",
            json={
                "name": "Invalid Group",
                "sleep_lock_enabled": True,
                "sleep_lock_start_time": "25:00",  # Invalid hour
                "sleep_lock_end_time": "07:00",
            }
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_group_sleep_lock_disabled_no_times_required(self, async_client):
        """Test that disabled sleep lock doesn't require times."""
        response = await async_client.post(
            "/api/groups/",
            json={
                "name": "Normal Group",
                "sleep_lock_enabled": False,
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["sleep_lock_enabled"] is False
        assert data["sleep_lock_start_time"] is None
        assert data["sleep_lock_end_time"] is None

    @pytest.mark.asyncio
    async def test_update_group_enable_sleep_lock(self, async_client, sample_group_data):
        """Test enabling sleep lock on an existing group."""
        # Create group without sleep lock
        create_response = await async_client.post("/api/groups/", json=sample_group_data)
        group_id = create_response.json()["id"]

        # Update to enable sleep lock
        response = await async_client.patch(
            f"/api/groups/{group_id}",
            json={
                "sleep_lock_enabled": True,
                "sleep_lock_start_time": "23:00",
                "sleep_lock_end_time": "06:00",
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sleep_lock_enabled"] is True
        assert data["sleep_lock_start_time"] == "23:00"
        assert data["sleep_lock_end_time"] == "06:00"

    @pytest.mark.asyncio
    async def test_update_group_enable_sleep_lock_missing_times(self, async_client, sample_group_data):
        """Test that enabling sleep lock without times fails."""
        # Create group without sleep lock
        create_response = await async_client.post("/api/groups/", json=sample_group_data)
        group_id = create_response.json()["id"]

        # Try to enable sleep lock without times
        response = await async_client.patch(
            f"/api/groups/{group_id}",
            json={
                "sleep_lock_enabled": True,
                # No times provided
            }
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_sleep_lock_active_during_lock_hours(self, async_client):
        """Test that sleep_lock_active is True during lock hours."""
        # Create group with lock from 22:00 to 07:00
        create_response = await async_client.post(
            "/api/groups/",
            json={
                "name": "Night Lock Group",
                "sleep_lock_enabled": True,
                "sleep_lock_start_time": "22:00",
                "sleep_lock_end_time": "07:00",
            }
        )
        group_id = create_response.json()["id"]

        # Mock time to be 23:00 (during lock hours)
        mock_datetime = datetime(2026, 1, 15, 23, 0, 0)
        with patch("tau.api.routes.groups.datetime") as mock_dt:
            mock_dt.now.return_value = mock_datetime

            response = await async_client.get(f"/api/groups/{group_id}")

            assert response.status_code == 200
            data = response.json()
            assert data["sleep_lock_active"] is True

    @pytest.mark.asyncio
    async def test_sleep_lock_inactive_outside_lock_hours(self, async_client):
        """Test that sleep_lock_active is False outside lock hours."""
        # Create group with lock from 22:00 to 07:00
        create_response = await async_client.post(
            "/api/groups/",
            json={
                "name": "Night Lock Group",
                "sleep_lock_enabled": True,
                "sleep_lock_start_time": "22:00",
                "sleep_lock_end_time": "07:00",
            }
        )
        group_id = create_response.json()["id"]

        # Mock time to be 12:00 (outside lock hours)
        mock_datetime = datetime(2026, 1, 15, 12, 0, 0)
        with patch("tau.api.routes.groups.datetime") as mock_dt:
            mock_dt.now.return_value = mock_datetime

            response = await async_client.get(f"/api/groups/{group_id}")

            assert response.status_code == 200
            data = response.json()
            assert data["sleep_lock_active"] is False

    @pytest.mark.asyncio
    async def test_sleep_lock_active_spans_midnight(self, async_client):
        """Test that sleep_lock_active works for time ranges spanning midnight."""
        # Create group with lock from 22:00 to 07:00
        create_response = await async_client.post(
            "/api/groups/",
            json={
                "name": "Night Lock Group",
                "sleep_lock_enabled": True,
                "sleep_lock_start_time": "22:00",
                "sleep_lock_end_time": "07:00",
            }
        )
        group_id = create_response.json()["id"]

        # Test early morning (02:00) - should be locked
        mock_datetime = datetime(2026, 1, 15, 2, 0, 0)
        with patch("tau.api.routes.groups.datetime") as mock_dt:
            mock_dt.now.return_value = mock_datetime

            response = await async_client.get(f"/api/groups/{group_id}")

            assert response.status_code == 200
            data = response.json()
            assert data["sleep_lock_active"] is True

    @pytest.mark.asyncio
    async def test_sleep_lock_active_boundary_start(self, async_client):
        """Test sleep_lock_active at exactly the start time."""
        # Create group with lock from 22:00 to 07:00
        create_response = await async_client.post(
            "/api/groups/",
            json={
                "name": "Night Lock Group",
                "sleep_lock_enabled": True,
                "sleep_lock_start_time": "22:00",
                "sleep_lock_end_time": "07:00",
            }
        )
        group_id = create_response.json()["id"]

        # Mock time to be exactly 22:00 - should be locked
        mock_datetime = datetime(2026, 1, 15, 22, 0, 0)
        with patch("tau.api.routes.groups.datetime") as mock_dt:
            mock_dt.now.return_value = mock_datetime

            response = await async_client.get(f"/api/groups/{group_id}")

            assert response.status_code == 200
            data = response.json()
            assert data["sleep_lock_active"] is True

    @pytest.mark.asyncio
    async def test_sleep_lock_active_boundary_end(self, async_client):
        """Test sleep_lock_active at exactly the end time."""
        # Create group with lock from 22:00 to 07:00
        create_response = await async_client.post(
            "/api/groups/",
            json={
                "name": "Night Lock Group",
                "sleep_lock_enabled": True,
                "sleep_lock_start_time": "22:00",
                "sleep_lock_end_time": "07:00",
            }
        )
        group_id = create_response.json()["id"]

        # Mock time to be exactly 07:00 - should NOT be locked (end time is exclusive)
        mock_datetime = datetime(2026, 1, 15, 7, 0, 0)
        with patch("tau.api.routes.groups.datetime") as mock_dt:
            mock_dt.now.return_value = mock_datetime

            response = await async_client.get(f"/api/groups/{group_id}")

            assert response.status_code == 200
            data = response.json()
            assert data["sleep_lock_active"] is False

    @pytest.mark.asyncio
    async def test_sleep_lock_daytime_range(self, async_client):
        """Test sleep_lock_active for a daytime range (not spanning midnight)."""
        # Create group with lock from 08:00 to 17:00 (daytime)
        create_response = await async_client.post(
            "/api/groups/",
            json={
                "name": "Daytime Lock Group",
                "sleep_lock_enabled": True,
                "sleep_lock_start_time": "08:00",
                "sleep_lock_end_time": "17:00",
            }
        )
        group_id = create_response.json()["id"]

        # 10:00 - should be locked
        mock_datetime = datetime(2026, 1, 15, 10, 0, 0)
        with patch("tau.api.routes.groups.datetime") as mock_dt:
            mock_dt.now.return_value = mock_datetime

            response = await async_client.get(f"/api/groups/{group_id}")

            assert response.status_code == 200
            data = response.json()
            assert data["sleep_lock_active"] is True

        # 20:00 - should NOT be locked
        mock_datetime = datetime(2026, 1, 15, 20, 0, 0)
        with patch("tau.api.routes.groups.datetime") as mock_dt:
            mock_dt.now.return_value = mock_datetime

            response = await async_client.get(f"/api/groups/{group_id}")

            assert response.status_code == 200
            data = response.json()
            assert data["sleep_lock_active"] is False

    @pytest.mark.asyncio
    async def test_sleep_lock_disabled_always_inactive(self, async_client):
        """Test that sleep_lock_active is False when sleep lock is disabled."""
        # Create group without sleep lock
        create_response = await async_client.post(
            "/api/groups/",
            json={
                "name": "Normal Group",
                "sleep_lock_enabled": False,
            }
        )
        group_id = create_response.json()["id"]

        response = await async_client.get(f"/api/groups/{group_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["sleep_lock_active"] is False

    @pytest.mark.asyncio
    async def test_sleep_lock_unlock_duration_valid_range(self, async_client):
        """Test that unlock duration must be between 0 and 60."""
        # Valid: 0 (single action)
        response = await async_client.post(
            "/api/groups/",
            json={
                "name": "Group 1",
                "sleep_lock_enabled": True,
                "sleep_lock_start_time": "22:00",
                "sleep_lock_end_time": "07:00",
                "sleep_lock_unlock_duration_minutes": 0,
            }
        )
        assert response.status_code == 201

        # Valid: 60 (max)
        response = await async_client.post(
            "/api/groups/",
            json={
                "name": "Group 2",
                "sleep_lock_enabled": True,
                "sleep_lock_start_time": "22:00",
                "sleep_lock_end_time": "07:00",
                "sleep_lock_unlock_duration_minutes": 60,
            }
        )
        assert response.status_code == 201

        # Invalid: > 60
        response = await async_client.post(
            "/api/groups/",
            json={
                "name": "Group 3",
                "sleep_lock_enabled": True,
                "sleep_lock_start_time": "22:00",
                "sleep_lock_end_time": "07:00",
                "sleep_lock_unlock_duration_minutes": 120,
            }
        )
        assert response.status_code == 422

        # Invalid: < 0
        response = await async_client.post(
            "/api/groups/",
            json={
                "name": "Group 4",
                "sleep_lock_enabled": True,
                "sleep_lock_start_time": "22:00",
                "sleep_lock_end_time": "07:00",
                "sleep_lock_unlock_duration_minutes": -5,
            }
        )
        assert response.status_code == 422
