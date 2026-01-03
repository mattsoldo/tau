"""
API tests for groups endpoints.

Tests CRUD operations for groups and fixture membership.
"""
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
