"""
API tests for fixtures endpoints.

Tests CRUD operations for fixture models and fixtures.
"""
import pytest
import pytest_asyncio


class TestFixtureModelsAPI:
    """Tests for /api/fixtures/models endpoints."""

    @pytest.mark.asyncio
    async def test_list_fixture_models_empty(self, async_client):
        """Test listing fixture models when none exist."""
        response = await async_client.get("/api/fixtures/models")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_create_fixture_model(self, async_client, sample_fixture_model_data):
        """Test creating a fixture model."""
        response = await async_client.post(
            "/api/fixtures/models",
            json=sample_fixture_model_data
        )

        assert response.status_code == 201
        data = response.json()
        assert data["manufacturer"] == sample_fixture_model_data["manufacturer"]
        assert data["model"] == sample_fixture_model_data["model"]
        assert data["type"] == sample_fixture_model_data["type"]
        assert data["id"] is not None

    @pytest.mark.asyncio
    async def test_list_fixture_models(self, async_client, sample_fixture_model_data):
        """Test listing fixture models after creating one."""
        # Create a model
        await async_client.post("/api/fixtures/models", json=sample_fixture_model_data)

        # List models
        response = await async_client.get("/api/fixtures/models")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["manufacturer"] == sample_fixture_model_data["manufacturer"]

    @pytest.mark.asyncio
    async def test_get_fixture_model(self, async_client, sample_fixture_model_data):
        """Test getting a specific fixture model."""
        # Create a model
        create_response = await async_client.post(
            "/api/fixtures/models",
            json=sample_fixture_model_data
        )
        model_id = create_response.json()["id"]

        # Get the model
        response = await async_client.get(f"/api/fixtures/models/{model_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == model_id
        assert data["manufacturer"] == sample_fixture_model_data["manufacturer"]

    @pytest.mark.asyncio
    async def test_get_fixture_model_not_found(self, async_client):
        """Test getting a non-existent fixture model."""
        response = await async_client.get("/api/fixtures/models/99999")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_update_fixture_model(self, async_client, sample_fixture_model_data):
        """Test updating a fixture model."""
        # Create a model
        create_response = await async_client.post(
            "/api/fixtures/models",
            json=sample_fixture_model_data
        )
        model_id = create_response.json()["id"]

        # Update the model
        update_data = {"description": "Updated description"}
        response = await async_client.patch(
            f"/api/fixtures/models/{model_id}",
            json=update_data
        )

        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "Updated description"
        assert data["manufacturer"] == sample_fixture_model_data["manufacturer"]

    @pytest.mark.asyncio
    async def test_delete_fixture_model(self, async_client, sample_fixture_model_data):
        """Test deleting a fixture model."""
        # Create a model
        create_response = await async_client.post(
            "/api/fixtures/models",
            json=sample_fixture_model_data
        )
        model_id = create_response.json()["id"]

        # Delete the model
        response = await async_client.delete(f"/api/fixtures/models/{model_id}")

        assert response.status_code == 204

        # Verify it's gone
        get_response = await async_client.get(f"/api/fixtures/models/{model_id}")
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_fixture_model_not_found(self, async_client):
        """Test deleting a non-existent fixture model."""
        response = await async_client.delete("/api/fixtures/models/99999")

        assert response.status_code == 404


class TestFixturesAPI:
    """Tests for /api/fixtures endpoints."""

    @pytest_asyncio.fixture
    async def created_model(self, async_client, sample_fixture_model_data):
        """Create a fixture model and return its ID."""
        response = await async_client.post(
            "/api/fixtures/models",
            json=sample_fixture_model_data
        )
        return response.json()

    @pytest.mark.asyncio
    async def test_list_fixtures_empty(self, async_client):
        """Test listing fixtures when none exist."""
        response = await async_client.get("/api/fixtures/")

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_create_fixture(self, async_client, created_model, sample_fixture_data):
        """Test creating a fixture."""
        fixture_data = {
            **sample_fixture_data,
            "fixture_model_id": created_model["id"]
        }

        response = await async_client.post("/api/fixtures/", json=fixture_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == fixture_data["name"]
        assert data["dmx_channel_start"] == fixture_data["dmx_channel_start"]
        assert data["fixture_model_id"] == created_model["id"]
        assert data["id"] is not None

    @pytest.mark.asyncio
    async def test_create_fixture_model_not_found(self, async_client, sample_fixture_data):
        """Test creating a fixture with non-existent model."""
        fixture_data = {
            **sample_fixture_data,
            "fixture_model_id": 99999
        }

        response = await async_client.post("/api/fixtures/", json=fixture_data)

        assert response.status_code == 404
        assert "model not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_fixture_duplicate_dmx_channel(
        self, async_client, created_model, sample_fixture_data
    ):
        """Test creating a fixture with duplicate DMX channel."""
        fixture_data = {
            **sample_fixture_data,
            "fixture_model_id": created_model["id"]
        }

        # Create first fixture
        await async_client.post("/api/fixtures/", json=fixture_data)

        # Try to create second fixture with same DMX channel
        fixture_data["name"] = "Duplicate Fixture"
        response = await async_client.post("/api/fixtures/", json=fixture_data)

        assert response.status_code == 409
        assert "already in use" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_list_fixtures(self, async_client, created_model, sample_fixture_data):
        """Test listing fixtures after creating one."""
        fixture_data = {
            **sample_fixture_data,
            "fixture_model_id": created_model["id"]
        }
        await async_client.post("/api/fixtures/", json=fixture_data)

        response = await async_client.get("/api/fixtures/")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == fixture_data["name"]

    @pytest.mark.asyncio
    async def test_get_fixture(self, async_client, created_model, sample_fixture_data):
        """Test getting a specific fixture."""
        fixture_data = {
            **sample_fixture_data,
            "fixture_model_id": created_model["id"]
        }
        create_response = await async_client.post("/api/fixtures/", json=fixture_data)
        fixture_id = create_response.json()["id"]

        response = await async_client.get(f"/api/fixtures/{fixture_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == fixture_id
        assert data["name"] == fixture_data["name"]

    @pytest.mark.asyncio
    async def test_get_fixture_not_found(self, async_client):
        """Test getting a non-existent fixture."""
        response = await async_client.get("/api/fixtures/99999")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_fixture(self, async_client, created_model, sample_fixture_data):
        """Test updating a fixture."""
        fixture_data = {
            **sample_fixture_data,
            "fixture_model_id": created_model["id"]
        }
        create_response = await async_client.post("/api/fixtures/", json=fixture_data)
        fixture_id = create_response.json()["id"]

        # Update the fixture
        update_data = {"name": "Updated Fixture Name", "room": "Bedroom"}
        response = await async_client.patch(f"/api/fixtures/{fixture_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Fixture Name"
        assert data["room"] == "Bedroom"

    @pytest.mark.asyncio
    async def test_delete_fixture(self, async_client, created_model, sample_fixture_data):
        """Test deleting a fixture."""
        fixture_data = {
            **sample_fixture_data,
            "fixture_model_id": created_model["id"]
        }
        create_response = await async_client.post("/api/fixtures/", json=fixture_data)
        fixture_id = create_response.json()["id"]

        # Delete the fixture
        response = await async_client.delete(f"/api/fixtures/{fixture_id}")

        assert response.status_code == 204

        # Verify it's gone
        get_response = await async_client.get(f"/api/fixtures/{fixture_id}")
        assert get_response.status_code == 404


class TestSystemEndpoints:
    """Tests for system endpoints."""

    @pytest.mark.asyncio
    async def test_health_check(self, async_client):
        """Test the health check endpoint."""
        response = await async_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert data["service"] == "tau-daemon"

    @pytest.mark.asyncio
    async def test_status_endpoint(self, async_client):
        """Test the status endpoint."""
        response = await async_client.get("/status")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["service"] == "tau-daemon"
