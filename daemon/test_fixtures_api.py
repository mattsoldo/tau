"""
Fixtures API Integration Tests

Tests fixture CRUD operations, model updates, and merge/unmerge functionality.
Runs against a live daemon instance.

Requirements:
- Daemon must be running on localhost:8000
- Tests create and delete their own test data
"""
import pytest
import requests
import uuid
from typing import Optional

# API Base URL
API_URL = "http://localhost:8000"

def unique_id() -> str:
    """Generate a short unique ID for test data"""
    return str(uuid.uuid4())[:8]


def api_get(path: str) -> requests.Response:
    """GET request with trailing slash normalization"""
    url = f"{API_URL}{path}"
    if not url.endswith('/') and '?' not in path:
        url += '/'
    return requests.get(url)


def api_post(path: str, json: Optional[dict] = None) -> requests.Response:
    """POST request"""
    return requests.post(f"{API_URL}{path}", json=json)


def api_patch(path: str, json: dict) -> requests.Response:
    """PATCH request"""
    return requests.patch(f"{API_URL}{path}", json=json)


def api_delete(path: str) -> requests.Response:
    """DELETE request"""
    return requests.delete(f"{API_URL}{path}")


@pytest.fixture(scope="session")
def check_daemon():
    """Verify daemon is running before tests"""
    try:
        response = requests.get(f"{API_URL}/health", timeout=2)
        if response.status_code != 200:
            pytest.skip("Daemon is not running or unhealthy")
    except requests.exceptions.ConnectionError:
        pytest.skip("Daemon is not running on localhost:8000")


@pytest.fixture
def test_model(check_daemon):
    """Create a test fixture model and clean up after"""
    uid = unique_id()
    response = api_post("/api/fixtures/models", json={
        "manufacturer": "PyTest",
        "model": f"Test Model {uid}",
        "type": "simple_dimmable",
        "dmx_footprint": 1,
        "cct_min_kelvin": 2700,
        "cct_max_kelvin": 6500,
        "mixing_type": "linear"
    })
    assert response.status_code == 201, f"Failed to create test model: {response.text}"
    model = response.json()
    yield model
    # Cleanup
    api_delete(f"/api/fixtures/models/{model['id']}")


@pytest.fixture
def tunable_model(check_daemon):
    """Create a tunable white test model and clean up after"""
    uid = unique_id()
    response = api_post("/api/fixtures/models", json={
        "manufacturer": "PyTest",
        "model": f"Tunable White Test {uid}",
        "type": "tunable_white",
        "dmx_footprint": 2,
        "cct_min_kelvin": 2700,
        "cct_max_kelvin": 6500,
        "mixing_type": "perceptual"
    })
    assert response.status_code == 201, f"Failed to create tunable model: {response.text}"
    model = response.json()
    yield model
    # Cleanup
    api_delete(f"/api/fixtures/models/{model['id']}")


@pytest.fixture
def test_fixture(check_daemon, test_model):
    """Create a test fixture and clean up after"""
    # Find an available DMX channel
    fixtures_response = api_get("/api/fixtures")
    existing = fixtures_response.json() if fixtures_response.status_code == 200 else []
    used_channels = {f["dmx_channel_start"] for f in existing}
    used_channels.update({f["secondary_dmx_channel"] for f in existing if f.get("secondary_dmx_channel")})

    # Find unused channel starting from 200
    dmx_channel = 200
    while dmx_channel in used_channels:
        dmx_channel += 1

    response = api_post("/api/fixtures/", json={
        "name": "PyTest Fixture",
        "fixture_model_id": test_model["id"],
        "dmx_channel_start": dmx_channel
    })
    assert response.status_code == 201, f"Failed to create test fixture: {response.text}"
    fixture = response.json()
    yield fixture
    # Cleanup
    api_delete(f"/api/fixtures/{fixture['id']}")


class TestFixtureModelUpdate:
    """Test fixture model update persistence"""

    def test_update_fixture_model_id(self, test_fixture, tunable_model):
        """Test that changing fixture_model_id persists"""
        original_model_id = test_fixture["fixture_model_id"]
        new_model_id = tunable_model["id"]

        # Update the fixture model
        response = api_patch(f"/api/fixtures/{test_fixture['id']}", json={
            "fixture_model_id": new_model_id
        })
        assert response.status_code == 200, f"PATCH failed: {response.text}"

        # Verify the response shows the new model
        updated = response.json()
        assert updated["fixture_model_id"] == new_model_id, \
            f"Response should show new model {new_model_id}, got {updated['fixture_model_id']}"

        # Verify persistence by fetching again
        response = api_get(f"/api/fixtures/{test_fixture['id']}")
        assert response.status_code == 200
        fetched = response.json()
        assert fetched["fixture_model_id"] == new_model_id, \
            f"GET should return new model {new_model_id}, got {fetched['fixture_model_id']}"

        # Restore original model for cleanup
        api_patch(f"/api/fixtures/{test_fixture['id']}", json={
            "fixture_model_id": original_model_id
        })

    def test_update_fixture_name(self, test_fixture):
        """Test that changing fixture name persists"""
        original_name = test_fixture["name"]
        new_name = "Updated PyTest Fixture Name"

        response = api_patch(f"/api/fixtures/{test_fixture['id']}", json={
            "name": new_name
        })
        assert response.status_code == 200
        assert response.json()["name"] == new_name

        # Verify persistence
        response = api_get(f"/api/fixtures/{test_fixture['id']}")
        assert response.json()["name"] == new_name

        # Restore original name
        api_patch(f"/api/fixtures/{test_fixture['id']}", json={
            "name": original_name
        })

    def test_update_nonexistent_model_fails(self, test_fixture):
        """Test that updating to a nonexistent model fails"""
        response = api_patch(f"/api/fixtures/{test_fixture['id']}", json={
            "fixture_model_id": 99999
        })
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestFixtureMerge:
    """Test fixture merge/unmerge functionality"""

    def _find_unused_channels(self, count: int = 2, start: int = 300) -> list[int]:
        """Find unused DMX channels"""
        fixtures_response = api_get("/api/fixtures")
        existing = fixtures_response.json() if fixtures_response.status_code == 200 else []
        used = {f["dmx_channel_start"] for f in existing}
        used.update({f["secondary_dmx_channel"] for f in existing if f.get("secondary_dmx_channel")})

        channels = []
        channel = start
        while len(channels) < count:
            if channel not in used:
                channels.append(channel)
            channel += 1
        return channels

    def test_merge_two_fixtures(self, test_model, tunable_model):
        """Test merging two fixtures creates a dual-channel fixture"""
        channels = self._find_unused_channels(2)

        # Create two fixtures
        response1 = api_post("/api/fixtures/", json={
            "name": "PyTest Warm Channel",
            "fixture_model_id": test_model["id"],
            "dmx_channel_start": channels[0]
        })
        assert response1.status_code == 201
        fixture1 = response1.json()

        response2 = api_post("/api/fixtures/", json={
            "name": "PyTest Cool Channel",
            "fixture_model_id": test_model["id"],
            "dmx_channel_start": channels[1]
        })
        assert response2.status_code == 201
        fixture2 = response2.json()

        try:
            # Merge fixtures
            response = api_post("/api/fixtures/merge", json={
                "primary_fixture_id": fixture1["id"],
                "secondary_fixture_id": fixture2["id"],
                "target_model_id": tunable_model["id"]
            })
            assert response.status_code == 200, f"Merge failed: {response.text}"

            merged = response.json()
            assert merged["id"] == fixture1["id"], "Primary fixture should be kept"
            assert merged["name"] == fixture1["name"], "Primary fixture name should be kept"
            assert merged["dmx_channel_start"] == channels[0], "Primary DMX channel should be kept"
            assert merged["secondary_dmx_channel"] == channels[1], "Secondary DMX channel should be set"
            assert merged["fixture_model_id"] == tunable_model["id"], "Model should be updated"

            # Verify secondary fixture was deleted
            response = api_get(f"/api/fixtures/{fixture2['id']}")
            assert response.status_code == 404, "Secondary fixture should be deleted"
        finally:
            # Cleanup - delete primary fixture
            api_delete(f"/api/fixtures/{fixture1['id']}")

    def test_merge_already_merged_fails(self, test_model):
        """Test that merging an already merged fixture fails"""
        channels = self._find_unused_channels(3, start=400)

        # Create three fixtures
        fixtures = []
        for i, ch in enumerate(channels):
            response = api_post("/api/fixtures/", json={
                "name": f"PyTest Fixture {i}",
                "fixture_model_id": test_model["id"],
                "dmx_channel_start": ch
            })
            assert response.status_code == 201
            fixtures.append(response.json())

        try:
            # First merge
            response = api_post("/api/fixtures/merge", json={
                "primary_fixture_id": fixtures[0]["id"],
                "secondary_fixture_id": fixtures[1]["id"]
            })
            assert response.status_code == 200

            # Try to merge again with the already merged fixture
            response = api_post("/api/fixtures/merge", json={
                "primary_fixture_id": fixtures[0]["id"],
                "secondary_fixture_id": fixtures[2]["id"]
            })
            assert response.status_code == 400
            assert "already has a secondary" in response.json()["detail"].lower()
        finally:
            # Cleanup
            api_delete(f"/api/fixtures/{fixtures[0]['id']}")
            api_delete(f"/api/fixtures/{fixtures[2]['id']}")

    def test_unmerge_fixture(self, test_model):
        """Test unmerging removes the secondary channel"""
        channels = self._find_unused_channels(2, start=500)

        # Create and merge two fixtures
        response1 = api_post("/api/fixtures/", json={
            "name": "PyTest Primary",
            "fixture_model_id": test_model["id"],
            "dmx_channel_start": channels[0]
        })
        fixture1 = response1.json()

        response2 = api_post("/api/fixtures/", json={
            "name": "PyTest Secondary",
            "fixture_model_id": test_model["id"],
            "dmx_channel_start": channels[1]
        })
        fixture2 = response2.json()

        try:
            # Merge
            api_post("/api/fixtures/merge", json={
                "primary_fixture_id": fixture1["id"],
                "secondary_fixture_id": fixture2["id"]
            })

            # Unmerge
            response = api_post(f"/api/fixtures/{fixture1['id']}/unmerge")
            assert response.status_code == 200

            unmerged = response.json()
            assert unmerged["secondary_dmx_channel"] is None, "Secondary channel should be removed"

            # Verify persistence
            response = api_get(f"/api/fixtures/{fixture1['id']}")
            assert response.json()["secondary_dmx_channel"] is None
        finally:
            # Cleanup
            api_delete(f"/api/fixtures/{fixture1['id']}")

    def test_unmerge_not_merged_fails(self, test_fixture):
        """Test that unmerging a non-merged fixture fails"""
        response = api_post(f"/api/fixtures/{test_fixture['id']}/unmerge")
        assert response.status_code == 400
        assert "no secondary channel" in response.json()["detail"].lower()


class TestBulkOperations:
    """Test bulk update operations"""

    def test_bulk_model_update(self, test_model, tunable_model):
        """Test updating multiple fixtures' models"""
        uid = unique_id()
        # Find unused channels
        fixtures_response = api_get("/api/fixtures")
        existing = fixtures_response.json() if fixtures_response.status_code == 200 else []
        used = {f["dmx_channel_start"] for f in existing}
        used.update({f["secondary_dmx_channel"] for f in existing if f.get("secondary_dmx_channel")})

        channels = []
        ch = 450
        while len(channels) < 3 and ch <= 512:
            if ch not in used:
                channels.append(ch)
            ch += 1
        assert len(channels) == 3, f"Could not find 3 unused DMX channels (max 512)"

        # Create multiple fixtures
        fixture_ids = []
        for i, ch in enumerate(channels):
            response = api_post("/api/fixtures/", json={
                "name": f"PyTest Bulk {uid} {i}",
                "fixture_model_id": test_model["id"],
                "dmx_channel_start": ch
            })
            assert response.status_code == 201, f"Failed to create fixture: {response.text}"
            fixture_ids.append(response.json()["id"])

        try:
            # Update each fixture's model
            for fid in fixture_ids:
                response = api_patch(f"/api/fixtures/{fid}", json={
                    "fixture_model_id": tunable_model["id"]
                })
                assert response.status_code == 200
                assert response.json()["fixture_model_id"] == tunable_model["id"]

            # Verify all updates persisted
            for fid in fixture_ids:
                response = api_get(f"/api/fixtures/{fid}")
                assert response.json()["fixture_model_id"] == tunable_model["id"]
        finally:
            # Cleanup
            for fid in fixture_ids:
                api_delete(f"/api/fixtures/{fid}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
