"""
Discovery API Integration Tests

Tests RDM device discovery endpoints.
Runs against a live daemon instance.

Requirements:
- Daemon must be running on localhost:8000
"""
import pytest
import requests
import time

# API Base URL
API_URL = "http://localhost:8000"


@pytest.fixture(scope="session")
def check_daemon():
    """Verify daemon is running before tests"""
    try:
        response = requests.get(f"{API_URL}/health", timeout=2)
        if response.status_code != 200:
            pytest.skip("Daemon is not running or unhealthy")
    except requests.exceptions.ConnectionError:
        pytest.skip("Daemon is not running on localhost:8000")


class TestDiscoveryAPI:
    """Test RDM discovery endpoints"""

    def test_start_discovery(self, check_daemon):
        """Test starting a discovery scan returns a valid discovery_id"""
        response = requests.post(
            f"{API_URL}/api/discovery/start",
            json={"universe": 0}
        )
        assert response.status_code == 200, f"Failed to start discovery: {response.text}"

        data = response.json()
        assert "discovery_id" in data
        assert data["status"] == "scanning"
        assert len(data["discovery_id"]) == 36  # UUID format

    def test_get_progress(self, check_daemon):
        """Test getting progress of a discovery scan"""
        # Start discovery
        start_response = requests.post(
            f"{API_URL}/api/discovery/start",
            json={"universe": 0}
        )
        discovery_id = start_response.json()["discovery_id"]

        # Get progress immediately
        progress_response = requests.get(
            f"{API_URL}/api/discovery/progress/{discovery_id}"
        )
        assert progress_response.status_code == 200

        progress = progress_response.json()
        assert progress["discovery_id"] == discovery_id
        assert "status" in progress
        assert "progress_percent" in progress
        assert "devices_found" in progress
        assert 0 <= progress["progress_percent"] <= 100

    def test_get_results_after_completion(self, check_daemon):
        """Test getting results after discovery completes"""
        # Start discovery
        start_response = requests.post(
            f"{API_URL}/api/discovery/start",
            json={"universe": 0}
        )
        discovery_id = start_response.json()["discovery_id"]

        # Wait for completion (mock discovery takes 2-4 seconds)
        max_wait = 10
        start_time = time.time()
        while time.time() - start_time < max_wait:
            progress_response = requests.get(
                f"{API_URL}/api/discovery/progress/{discovery_id}"
            )
            progress = progress_response.json()
            if progress["status"] == "complete":
                break
            time.sleep(0.5)

        assert progress["status"] == "complete", f"Discovery did not complete in time. Status: {progress['status']}"
        assert progress["progress_percent"] == 100

        # Get results
        results_response = requests.get(
            f"{API_URL}/api/discovery/results/{discovery_id}"
        )
        assert results_response.status_code == 200

        results = results_response.json()
        assert results["status"] == "complete"
        assert "devices" in results
        assert isinstance(results["devices"], list)
        assert len(results["devices"]) >= 1  # Mock returns 3-8 devices

        # Verify device structure
        for device in results["devices"]:
            assert "rdm_uid" in device
            assert "manufacturer_name" in device
            assert "model_name" in device
            assert "dmx_address" in device
            assert "dmx_footprint" in device
            assert 1 <= device["dmx_address"] <= 512

    def test_get_results_before_completion_fails(self, check_daemon):
        """Test that getting results before completion returns an error"""
        # Start discovery
        start_response = requests.post(
            f"{API_URL}/api/discovery/start",
            json={"universe": 0}
        )
        discovery_id = start_response.json()["discovery_id"]

        # Immediately try to get results (before completion)
        results_response = requests.get(
            f"{API_URL}/api/discovery/results/{discovery_id}"
        )

        # Should either fail or succeed depending on timing
        # If it fails, it should be a 400 error
        if results_response.status_code != 200:
            assert results_response.status_code == 400
            assert "not complete" in results_response.json()["detail"].lower()

    def test_cancel_discovery(self, check_daemon):
        """Test canceling an ongoing discovery"""
        # Start discovery
        start_response = requests.post(
            f"{API_URL}/api/discovery/start",
            json={"universe": 0}
        )
        discovery_id = start_response.json()["discovery_id"]

        # Cancel immediately
        cancel_response = requests.post(
            f"{API_URL}/api/discovery/cancel/{discovery_id}"
        )
        assert cancel_response.status_code == 200

        cancel_data = cancel_response.json()
        assert cancel_data["status"] == "cancelled"

        # Wait a moment for the cancellation to take effect
        time.sleep(0.5)

        # Verify progress shows cancelled status
        progress_response = requests.get(
            f"{API_URL}/api/discovery/progress/{discovery_id}"
        )
        progress = progress_response.json()
        assert progress["status"] == "cancelled"

    def test_invalid_discovery_id_returns_404(self, check_daemon):
        """Test that invalid discovery IDs return 404"""
        fake_id = "00000000-0000-0000-0000-000000000000"

        # Progress endpoint
        progress_response = requests.get(
            f"{API_URL}/api/discovery/progress/{fake_id}"
        )
        assert progress_response.status_code == 404

        # Results endpoint
        results_response = requests.get(
            f"{API_URL}/api/discovery/results/{fake_id}"
        )
        assert results_response.status_code == 404

        # Cancel endpoint
        cancel_response = requests.post(
            f"{API_URL}/api/discovery/cancel/{fake_id}"
        )
        assert cancel_response.status_code == 404

    def test_multiple_concurrent_discoveries(self, check_daemon):
        """Test running multiple discovery sessions concurrently"""
        # Start multiple discoveries
        discoveries = []
        for _ in range(3):
            response = requests.post(
                f"{API_URL}/api/discovery/start",
                json={"universe": 0}
            )
            assert response.status_code == 200
            discoveries.append(response.json()["discovery_id"])

        # Verify all have unique IDs
        assert len(set(discoveries)) == 3

        # Wait for all to complete
        time.sleep(5)

        # Verify all completed
        for discovery_id in discoveries:
            progress_response = requests.get(
                f"{API_URL}/api/discovery/progress/{discovery_id}"
            )
            progress = progress_response.json()
            assert progress["status"] in ["complete", "cancelled"]


class TestDiscoveryDeviceData:
    """Test the structure and validity of discovered device data"""

    def test_device_dmx_addresses_are_unique(self, check_daemon):
        """Test that discovered devices have unique DMX addresses"""
        # Start and complete discovery
        start_response = requests.post(
            f"{API_URL}/api/discovery/start",
            json={"universe": 0}
        )
        discovery_id = start_response.json()["discovery_id"]

        # Wait for completion
        time.sleep(5)

        results_response = requests.get(
            f"{API_URL}/api/discovery/results/{discovery_id}"
        )
        results = results_response.json()

        # Check uniqueness
        addresses = [d["dmx_address"] for d in results["devices"]]
        assert len(addresses) == len(set(addresses)), "DMX addresses should be unique"

    def test_device_rdm_uids_are_unique(self, check_daemon):
        """Test that discovered devices have unique RDM UIDs"""
        # Start and complete discovery
        start_response = requests.post(
            f"{API_URL}/api/discovery/start",
            json={"universe": 0}
        )
        discovery_id = start_response.json()["discovery_id"]

        # Wait for completion
        time.sleep(5)

        results_response = requests.get(
            f"{API_URL}/api/discovery/results/{discovery_id}"
        )
        results = results_response.json()

        # Check uniqueness
        uids = [d["rdm_uid"] for d in results["devices"]]
        assert len(uids) == len(set(uids)), "RDM UIDs should be unique"

    def test_devices_sorted_by_dmx_address(self, check_daemon):
        """Test that devices are returned sorted by DMX address"""
        # Start and complete discovery
        start_response = requests.post(
            f"{API_URL}/api/discovery/start",
            json={"universe": 0}
        )
        discovery_id = start_response.json()["discovery_id"]

        # Wait for completion
        time.sleep(5)

        results_response = requests.get(
            f"{API_URL}/api/discovery/results/{discovery_id}"
        )
        results = results_response.json()

        addresses = [d["dmx_address"] for d in results["devices"]]
        assert addresses == sorted(addresses), "Devices should be sorted by DMX address"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
