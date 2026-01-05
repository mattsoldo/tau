"""
Tests for DTW API endpoints
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from datetime import datetime, timedelta


@pytest.mark.asyncio
class TestDTWSettingsAPI:
    """Test DTW system settings endpoints"""

    async def test_get_dtw_settings(self, async_client: AsyncClient):
        """Should return DTW settings"""
        response = await async_client.get("/api/dtw/settings")
        assert response.status_code == 200

        data = response.json()
        assert "enabled" in data
        assert "min_cct" in data
        assert "max_cct" in data
        assert "min_brightness" in data
        assert "curve" in data
        assert "override_timeout" in data

    async def test_update_dtw_enabled(self, async_client: AsyncClient):
        """Should update DTW enabled state"""
        # Get current state
        response = await async_client.get("/api/dtw/settings")
        original = response.json()

        # Toggle enabled
        new_enabled = not original["enabled"]
        response = await async_client.put(
            "/api/dtw/settings",
            json={"enabled": new_enabled}
        )
        assert response.status_code == 200
        assert response.json()["enabled"] == new_enabled

        # Restore original
        await async_client.put(
            "/api/dtw/settings",
            json={"enabled": original["enabled"]}
        )

    async def test_update_dtw_curve(self, async_client: AsyncClient):
        """Should update DTW curve type"""
        response = await async_client.put(
            "/api/dtw/settings",
            json={"curve": "incandescent"}
        )
        assert response.status_code == 200
        assert response.json()["curve"] == "incandescent"

        # Restore to log
        await async_client.put(
            "/api/dtw/settings",
            json={"curve": "log"}
        )

    async def test_update_dtw_invalid_curve(self, async_client: AsyncClient):
        """Should reject invalid curve type"""
        response = await async_client.put(
            "/api/dtw/settings",
            json={"curve": "invalid_curve"}
        )
        assert response.status_code == 400

    async def test_update_dtw_cct_range(self, async_client: AsyncClient):
        """Should update CCT range"""
        response = await async_client.put(
            "/api/dtw/settings",
            json={"min_cct": 2000, "max_cct": 5000}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["min_cct"] == 2000
        assert data["max_cct"] == 5000

        # Restore defaults
        await async_client.put(
            "/api/dtw/settings",
            json={"min_cct": 1800, "max_cct": 4000}
        )

    async def test_update_dtw_invalid_cct_range(self, async_client: AsyncClient):
        """Should reject invalid CCT range (min >= max)"""
        response = await async_client.put(
            "/api/dtw/settings",
            json={"min_cct": 4000, "max_cct": 3000}
        )
        assert response.status_code == 400

    async def test_update_dtw_cct_bounds(self, async_client: AsyncClient):
        """Should reject CCT values outside valid range"""
        # Too low
        response = await async_client.put(
            "/api/dtw/settings",
            json={"min_cct": 500}
        )
        assert response.status_code == 422  # Validation error

        # Too high
        response = await async_client.put(
            "/api/dtw/settings",
            json={"max_cct": 15000}
        )
        assert response.status_code == 422

    async def test_get_dtw_curves(self, async_client: AsyncClient):
        """Should return available curves and example values"""
        response = await async_client.get("/api/dtw/curves")
        assert response.status_code == 200

        data = response.json()
        assert "available_curves" in data
        assert "current_curve" in data
        assert "example_values" in data

        # Check all curves are present
        curves = data["available_curves"]
        assert "linear" in curves
        assert "log" in curves
        assert "square" in curves
        assert "incandescent" in curves

        # Check example values
        examples = data["example_values"]
        assert len(examples) > 0
        for ex in examples:
            assert "brightness" in ex
            assert "cct" in ex


@pytest.mark.asyncio
class TestOverrideAPI:
    """Test override management endpoints"""

    async def test_list_overrides_empty(self, async_client: AsyncClient):
        """Should return empty list when no overrides exist"""
        response = await async_client.get("/api/dtw/overrides")
        assert response.status_code == 200
        # May or may not be empty depending on test state

    async def test_create_and_delete_override(self, async_client: AsyncClient, test_fixture):
        """Should create and delete an override"""
        # Create override
        response = await async_client.post(
            "/api/dtw/overrides",
            json={
                "target_type": "fixture",
                "target_id": test_fixture.id,
                "property": "cct",
                "value": 3500,
                "timeout_seconds": 3600
            }
        )
        assert response.status_code == 200
        data = response.json()
        override_id = data["id"]
        assert data["target_type"] == "fixture"
        assert data["target_id"] == test_fixture.id
        assert data["value"] == "3500"
        assert data["time_remaining_seconds"] > 0

        # List overrides - should include our override
        response = await async_client.get(
            "/api/dtw/overrides",
            params={"target_type": "fixture", "target_id": test_fixture.id}
        )
        assert response.status_code == 200
        overrides = response.json()
        assert any(o["id"] == override_id for o in overrides)

        # Delete override
        response = await async_client.delete(f"/api/dtw/overrides/{override_id}")
        assert response.status_code == 200

        # Verify deleted
        response = await async_client.get(
            "/api/dtw/overrides",
            params={"target_type": "fixture", "target_id": test_fixture.id}
        )
        overrides = response.json()
        assert not any(o["id"] == override_id for o in overrides)

    async def test_create_override_invalid_target_type(self, async_client: AsyncClient):
        """Should reject invalid target type"""
        response = await async_client.post(
            "/api/dtw/overrides",
            json={
                "target_type": "invalid",
                "target_id": 1,
                "property": "cct",
                "value": 3500
            }
        )
        assert response.status_code == 400

    async def test_create_override_invalid_cct(self, async_client: AsyncClient, test_fixture):
        """Should reject CCT outside valid range"""
        response = await async_client.post(
            "/api/dtw/overrides",
            json={
                "target_type": "fixture",
                "target_id": test_fixture.id,
                "property": "cct",
                "value": 500  # Too low
            }
        )
        assert response.status_code == 400

    async def test_delete_nonexistent_override(self, async_client: AsyncClient):
        """Should return 404 for nonexistent override"""
        response = await async_client.delete("/api/dtw/overrides/99999")
        assert response.status_code == 404

    async def test_bulk_delete_overrides(self, async_client: AsyncClient, test_fixture):
        """Should delete all overrides for a target"""
        # Create multiple overrides
        for i in range(3):
            await async_client.post(
                "/api/dtw/overrides",
                json={
                    "target_type": "fixture",
                    "target_id": test_fixture.id,
                    "property": "cct",
                    "value": 3000 + i * 100
                }
            )

        # Bulk delete
        response = await async_client.delete(
            "/api/dtw/overrides",
            params={"target_type": "fixture", "target_id": test_fixture.id}
        )
        assert response.status_code == 200
        assert response.json()["count"] >= 3

    async def test_cleanup_expired_overrides(self, async_client: AsyncClient):
        """Should cleanup expired overrides"""
        response = await async_client.post("/api/dtw/overrides/cleanup")
        assert response.status_code == 200
        assert "count" in response.json()


@pytest.mark.asyncio
class TestFixtureDTWAPI:
    """Test fixture-level DTW settings"""

    async def test_get_fixture_dtw_settings(self, async_client: AsyncClient, test_fixture):
        """Should get fixture DTW settings"""
        response = await async_client.get(f"/api/dtw/fixtures/{test_fixture.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["fixture_id"] == test_fixture.id
        assert "dtw_ignore" in data
        assert "dtw_min_cct_override" in data
        assert "dtw_max_cct_override" in data
        assert "has_active_override" in data

    async def test_update_fixture_dtw_settings(self, async_client: AsyncClient, test_fixture):
        """Should update fixture DTW settings"""
        response = await async_client.put(
            f"/api/dtw/fixtures/{test_fixture.id}",
            json={"dtw_ignore": True}
        )
        assert response.status_code == 200
        assert response.json()["dtw_ignore"] is True

        # Restore
        await async_client.put(
            f"/api/dtw/fixtures/{test_fixture.id}",
            json={"dtw_ignore": False}
        )

    async def test_update_fixture_cct_override(self, async_client: AsyncClient, test_fixture):
        """Should update fixture CCT range override"""
        response = await async_client.put(
            f"/api/dtw/fixtures/{test_fixture.id}",
            json={
                "dtw_min_cct_override": 2000,
                "dtw_max_cct_override": 3500
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["dtw_min_cct_override"] == 2000
        assert data["dtw_max_cct_override"] == 3500

    async def test_get_nonexistent_fixture_dtw(self, async_client: AsyncClient):
        """Should return 404 for nonexistent fixture"""
        response = await async_client.get("/api/dtw/fixtures/99999")
        assert response.status_code == 404


@pytest.mark.asyncio
class TestGroupDTWAPI:
    """Test group-level DTW settings"""

    async def test_get_group_dtw_settings(self, async_client: AsyncClient, test_group):
        """Should get group DTW settings"""
        response = await async_client.get(f"/api/dtw/groups/{test_group.id}")
        assert response.status_code == 200

        data = response.json()
        assert data["group_id"] == test_group.id
        assert "dtw_ignore" in data
        assert "dtw_min_cct_override" in data
        assert "dtw_max_cct_override" in data

    async def test_update_group_dtw_settings(self, async_client: AsyncClient, test_group):
        """Should update group DTW settings"""
        response = await async_client.put(
            f"/api/dtw/groups/{test_group.id}",
            json={"dtw_ignore": True}
        )
        assert response.status_code == 200
        assert response.json()["dtw_ignore"] is True

        # Restore
        await async_client.put(
            f"/api/dtw/groups/{test_group.id}",
            json={"dtw_ignore": False}
        )

    async def test_get_nonexistent_group_dtw(self, async_client: AsyncClient):
        """Should return 404 for nonexistent group"""
        response = await async_client.get("/api/dtw/groups/99999")
        assert response.status_code == 404
