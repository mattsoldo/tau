"""
Integration tests for group-StateManager synchronization.

These tests verify that when groups are created, fixtures are added/removed
from groups, or groups are deleted via the API, the StateManager's in-memory
cache is properly updated. This ensures that:

1. Newly created groups can be controlled immediately via dashboard or switches
2. Fixtures added to groups respond to group controls immediately
3. Fixtures removed from groups no longer respond to group controls
4. Deleted groups don't leave stale entries in the cache
"""
import pytest
import pytest_asyncio
from unittest.mock import MagicMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tau.control.state_manager import StateManager
from tau.database import get_session
from tau.config import Settings
from tau.api import create_app, set_daemon_instance, get_daemon_instance


@pytest_asyncio.fixture
async def state_manager_with_api(async_engine, test_settings):
    """Create a FastAPI test application with StateManager integration."""
    import tau.database as db_module

    # Create state manager
    state_manager = StateManager()

    # Create mock daemon with state manager
    mock_daemon = MagicMock()
    mock_daemon.state_manager = state_manager

    # Set the daemon instance
    set_daemon_instance(mock_daemon)

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
    async def override_get_session():
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

    yield app, state_manager

    # Cleanup
    set_daemon_instance(None)
    db_module.async_session_maker = original_session_maker


@pytest_asyncio.fixture
async def client_with_state_manager(state_manager_with_api):
    """Create async client and return both client and state_manager."""
    app, state_manager = state_manager_with_api
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client, state_manager


class TestGroupCreationSync:
    """Tests for group creation -> StateManager sync."""

    @pytest.mark.asyncio
    async def test_create_group_registers_in_state_manager(self, client_with_state_manager):
        """Test that creating a group via API registers it in StateManager."""
        client, state_manager = client_with_state_manager

        # State manager should be empty
        assert len(state_manager.groups) == 0

        # Create a group via API
        response = await client.post(
            "/api/groups/",
            json={"name": "Test Group", "circadian_enabled": True}
        )

        assert response.status_code == 201
        group_id = response.json()["id"]

        # Group should now be registered in StateManager
        assert group_id in state_manager.groups
        assert state_manager.groups[group_id].circadian_enabled is True

    @pytest.mark.asyncio
    async def test_create_group_can_be_controlled_immediately(self, client_with_state_manager, sample_fixture_model_data):
        """Test that a newly created group can receive control commands."""
        client, state_manager = client_with_state_manager

        # Create fixture model and fixture
        model_response = await client.post("/api/fixtures/models", json=sample_fixture_model_data)
        model_id = model_response.json()["id"]

        fixture_response = await client.post(
            "/api/fixtures/",
            json={"name": "Test Fixture", "fixture_model_id": model_id, "dmx_channel_start": 1}
        )
        fixture_id = fixture_response.json()["id"]

        # Register fixture in state manager (simulating what config_loader does)
        state_manager.register_fixture(fixture_id)

        # Create a group
        group_response = await client.post(
            "/api/groups/",
            json={"name": "New Group"}
        )
        group_id = group_response.json()["id"]

        # Add fixture to group
        await client.post(
            f"/api/groups/{group_id}/fixtures",
            json={"fixture_id": fixture_id}
        )

        # Now try to control the group - should work
        control_response = await client.post(
            f"/api/control/groups/{group_id}",
            json={"brightness": 0.75}
        )

        # Should succeed (status 200)
        assert control_response.status_code == 200

        # Fixture brightness should be updated
        assert state_manager.fixtures[fixture_id].goal_brightness == 0.75


class TestAddFixtureToGroupSync:
    """Tests for adding fixture to group -> StateManager sync."""

    @pytest.mark.asyncio
    async def test_add_fixture_updates_state_manager_memberships(self, client_with_state_manager, sample_fixture_model_data):
        """Test that adding fixture to group updates StateManager's membership cache."""
        client, state_manager = client_with_state_manager

        # Create fixture model
        model_response = await client.post("/api/fixtures/models", json=sample_fixture_model_data)
        model_id = model_response.json()["id"]

        # Create fixtures
        fixture1_response = await client.post(
            "/api/fixtures/",
            json={"name": "Fixture 1", "fixture_model_id": model_id, "dmx_channel_start": 1}
        )
        fixture1_id = fixture1_response.json()["id"]

        fixture2_response = await client.post(
            "/api/fixtures/",
            json={"name": "Fixture 2", "fixture_model_id": model_id, "dmx_channel_start": 10}
        )
        fixture2_id = fixture2_response.json()["id"]

        # Register fixtures in state manager
        state_manager.register_fixture(fixture1_id)
        state_manager.register_fixture(fixture2_id)

        # Create group
        group_response = await client.post(
            "/api/groups/",
            json={"name": "Test Group"}
        )
        group_id = group_response.json()["id"]

        # Add fixture1 to group
        add_response = await client.post(
            f"/api/groups/{group_id}/fixtures",
            json={"fixture_id": fixture1_id}
        )
        assert add_response.status_code == 201

        # Verify StateManager membership is updated
        assert group_id in state_manager.fixture_group_memberships[fixture1_id]
        assert group_id not in state_manager.fixture_group_memberships[fixture2_id]

    @pytest.mark.asyncio
    async def test_added_fixture_responds_to_group_control(self, client_with_state_manager, sample_fixture_model_data):
        """Test that after adding fixture to group, it responds to group control."""
        client, state_manager = client_with_state_manager

        # Create fixture model and fixture
        model_response = await client.post("/api/fixtures/models", json=sample_fixture_model_data)
        model_id = model_response.json()["id"]

        fixture_response = await client.post(
            "/api/fixtures/",
            json={"name": "Test Fixture", "fixture_model_id": model_id, "dmx_channel_start": 1}
        )
        fixture_id = fixture_response.json()["id"]

        # Register fixture in state manager
        state_manager.register_fixture(fixture_id)
        state_manager.set_fixture_brightness(fixture_id, 0.0)

        # Create group
        group_response = await client.post(
            "/api/groups/",
            json={"name": "Test Group"}
        )
        group_id = group_response.json()["id"]

        # Before adding: control group should update 0 fixtures
        count_before = state_manager.set_group_brightness(group_id, 0.5)
        assert count_before == 0
        assert state_manager.fixtures[fixture_id].goal_brightness == 0.0

        # Add fixture to group via API
        await client.post(
            f"/api/groups/{group_id}/fixtures",
            json={"fixture_id": fixture_id}
        )

        # After adding: control group should update the fixture
        count_after = state_manager.set_group_brightness(group_id, 0.8)
        assert count_after == 1
        assert state_manager.fixtures[fixture_id].goal_brightness == 0.8


class TestRemoveFixtureFromGroupSync:
    """Tests for removing fixture from group -> StateManager sync."""

    @pytest.mark.asyncio
    async def test_remove_fixture_updates_state_manager_memberships(self, client_with_state_manager, sample_fixture_model_data):
        """Test that removing fixture from group updates StateManager's membership cache."""
        client, state_manager = client_with_state_manager

        # Create fixture model
        model_response = await client.post("/api/fixtures/models", json=sample_fixture_model_data)
        model_id = model_response.json()["id"]

        # Create fixture
        fixture_response = await client.post(
            "/api/fixtures/",
            json={"name": "Test Fixture", "fixture_model_id": model_id, "dmx_channel_start": 1}
        )
        fixture_id = fixture_response.json()["id"]

        # Register fixture in state manager
        state_manager.register_fixture(fixture_id)

        # Create group
        group_response = await client.post(
            "/api/groups/",
            json={"name": "Test Group"}
        )
        group_id = group_response.json()["id"]

        # Add fixture to group
        await client.post(
            f"/api/groups/{group_id}/fixtures",
            json={"fixture_id": fixture_id}
        )

        # Verify fixture is in group
        assert group_id in state_manager.fixture_group_memberships[fixture_id]

        # Remove fixture from group
        remove_response = await client.delete(
            f"/api/groups/{group_id}/fixtures/{fixture_id}"
        )
        assert remove_response.status_code == 204

        # Verify StateManager membership is updated
        assert group_id not in state_manager.fixture_group_memberships[fixture_id]

    @pytest.mark.asyncio
    async def test_removed_fixture_does_not_respond_to_group_control(self, client_with_state_manager, sample_fixture_model_data):
        """Test that removed fixture no longer responds to group control (the main bug fix)."""
        client, state_manager = client_with_state_manager

        # Create fixture model
        model_response = await client.post("/api/fixtures/models", json=sample_fixture_model_data)
        model_id = model_response.json()["id"]

        # Create two fixtures
        fixture1_response = await client.post(
            "/api/fixtures/",
            json={"name": "Fixture 1", "fixture_model_id": model_id, "dmx_channel_start": 1}
        )
        fixture1_id = fixture1_response.json()["id"]

        fixture2_response = await client.post(
            "/api/fixtures/",
            json={"name": "Fixture 2", "fixture_model_id": model_id, "dmx_channel_start": 10}
        )
        fixture2_id = fixture2_response.json()["id"]

        # Register fixtures in state manager
        state_manager.register_fixture(fixture1_id)
        state_manager.register_fixture(fixture2_id)
        state_manager.set_fixture_brightness(fixture1_id, 0.0)
        state_manager.set_fixture_brightness(fixture2_id, 0.0)

        # Create group
        group_response = await client.post(
            "/api/groups/",
            json={"name": "Test Group"}
        )
        group_id = group_response.json()["id"]

        # Add both fixtures to group
        await client.post(f"/api/groups/{group_id}/fixtures", json={"fixture_id": fixture1_id})
        await client.post(f"/api/groups/{group_id}/fixtures", json={"fixture_id": fixture2_id})

        # Remove fixture1 from group
        await client.delete(f"/api/groups/{group_id}/fixtures/{fixture1_id}")

        # Control the group
        state_manager.set_group_brightness(group_id, 1.0)

        # Fixture1 should NOT have changed (was removed)
        assert state_manager.fixtures[fixture1_id].goal_brightness == 0.0

        # Fixture2 should have changed (still in group)
        assert state_manager.fixtures[fixture2_id].goal_brightness == 1.0


class TestDeleteGroupSync:
    """Tests for group deletion -> StateManager sync."""

    @pytest.mark.asyncio
    async def test_delete_group_unregisters_from_state_manager(self, client_with_state_manager):
        """Test that deleting a group unregisters it from StateManager."""
        client, state_manager = client_with_state_manager

        # Create a group
        response = await client.post(
            "/api/groups/",
            json={"name": "Test Group"}
        )
        group_id = response.json()["id"]

        # Verify group is in StateManager
        assert group_id in state_manager.groups

        # Delete the group
        delete_response = await client.delete(f"/api/groups/{group_id}")
        assert delete_response.status_code == 204

        # Verify group is removed from StateManager
        assert group_id not in state_manager.groups

    @pytest.mark.asyncio
    async def test_delete_group_removes_all_memberships(self, client_with_state_manager, sample_fixture_model_data):
        """Test that deleting a group removes it from all fixture memberships."""
        client, state_manager = client_with_state_manager

        # Create fixture model
        model_response = await client.post("/api/fixtures/models", json=sample_fixture_model_data)
        model_id = model_response.json()["id"]

        # Create fixtures
        fixtures = []
        for i in range(3):
            fixture_response = await client.post(
                "/api/fixtures/",
                json={"name": f"Fixture {i+1}", "fixture_model_id": model_id, "dmx_channel_start": (i+1)*10}
            )
            fixture_id = fixture_response.json()["id"]
            fixtures.append(fixture_id)
            state_manager.register_fixture(fixture_id)

        # Create group
        group_response = await client.post(
            "/api/groups/",
            json={"name": "Test Group"}
        )
        group_id = group_response.json()["id"]

        # Add all fixtures to group
        for fixture_id in fixtures:
            await client.post(
                f"/api/groups/{group_id}/fixtures",
                json={"fixture_id": fixture_id}
            )

        # Verify all fixtures have the group membership
        for fixture_id in fixtures:
            assert group_id in state_manager.fixture_group_memberships[fixture_id]

        # Delete the group
        await client.delete(f"/api/groups/{group_id}")

        # Verify group is removed from all fixture memberships
        for fixture_id in fixtures:
            assert group_id not in state_manager.fixture_group_memberships[fixture_id]


class TestNewGroupCanBeControlledImmediately:
    """
    Regression tests for the bug where newly created groups cannot be controlled.

    This was caused by the StateManager not being updated when groups are created
    via the API.
    """

    @pytest.mark.asyncio
    async def test_new_group_with_switch_control_flow(self, client_with_state_manager, sample_fixture_model_data):
        """
        Simulate the full user flow:
        1. Create a new group
        2. Add fixtures to it
        3. Assign a switch to the group (via config, not tested here)
        4. Trigger group control (simulating switch operation)

        The bug was that step 4 would fail because the group wasn't registered.
        """
        client, state_manager = client_with_state_manager

        # Step 1: Create fixture and register it
        model_response = await client.post("/api/fixtures/models", json=sample_fixture_model_data)
        model_id = model_response.json()["id"]

        fixture_response = await client.post(
            "/api/fixtures/",
            json={"name": "Test Fixture", "fixture_model_id": model_id, "dmx_channel_start": 1}
        )
        fixture_id = fixture_response.json()["id"]
        state_manager.register_fixture(fixture_id)
        state_manager.set_fixture_brightness(fixture_id, 0.0)

        # Step 2: Create a new group
        group_response = await client.post(
            "/api/groups/",
            json={"name": "Hallway", "description": "Hallway lights"}
        )
        group_id = group_response.json()["id"]

        # Step 3: Add fixture to group
        await client.post(
            f"/api/groups/{group_id}/fixtures",
            json={"fixture_id": fixture_id}
        )

        # Step 4: Simulate switch control by calling set_group_brightness
        # Before the fix, this would return 0 (group not found or no fixtures)
        updated_count = state_manager.set_group_brightness(group_id, 1.0, transition_duration=0.5)

        # After the fix, this should update 1 fixture
        assert updated_count == 1
        assert state_manager.fixtures[fixture_id].goal_brightness == 1.0

    @pytest.mark.asyncio
    async def test_dashboard_toggle_on_new_group(self, client_with_state_manager, sample_fixture_model_data):
        """
        Simulate dashboard group toggle on a newly created group.

        The bug was that toggling a new group from the dashboard would fail
        because the group wasn't registered in StateManager.
        """
        client, state_manager = client_with_state_manager

        # Create fixture
        model_response = await client.post("/api/fixtures/models", json=sample_fixture_model_data)
        model_id = model_response.json()["id"]

        fixture_response = await client.post(
            "/api/fixtures/",
            json={"name": "Living Room Light", "fixture_model_id": model_id, "dmx_channel_start": 1}
        )
        fixture_id = fixture_response.json()["id"]
        state_manager.register_fixture(fixture_id)

        # Create group
        group_response = await client.post(
            "/api/groups/",
            json={"name": "Living Room"}
        )
        group_id = group_response.json()["id"]

        # Add fixture
        await client.post(
            f"/api/groups/{group_id}/fixtures",
            json={"fixture_id": fixture_id}
        )

        # Simulate dashboard toggle ON via control API
        control_response = await client.post(
            f"/api/control/groups/{group_id}",
            json={"brightness": 1.0}
        )

        # Should succeed
        assert control_response.status_code == 200
        assert state_manager.fixtures[fixture_id].goal_brightness == 1.0

        # Simulate dashboard toggle OFF
        control_response = await client.post(
            f"/api/control/groups/{group_id}",
            json={"brightness": 0.0}
        )

        assert control_response.status_code == 200
        assert state_manager.fixtures[fixture_id].goal_brightness == 0.0
