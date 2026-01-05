"""
Unit tests for Software Update Service.

Tests version comparison, configuration helpers, and update workflow.
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from tau.services.software_update_service import (
    SoftwareUpdateService,
    UpdateError,
    ChecksumMismatchError,
    InstallationError,
    RollbackError,
    UPDATE_STATES,
    SERVICES,
)


class TestVersionComparison:
    """Tests for semantic version comparison."""

    @pytest.fixture
    def service(self):
        """Create service with mocked session."""
        mock_session = AsyncMock(spec=AsyncSession)
        return SoftwareUpdateService(db_session=mock_session)

    def test_compare_versions_less_than(self, service):
        """v1 < v2 returns -1."""
        assert service._compare_versions("1.0.0", "1.0.1") == -1
        assert service._compare_versions("1.0.0", "1.1.0") == -1
        assert service._compare_versions("1.0.0", "2.0.0") == -1

    def test_compare_versions_equal(self, service):
        """v1 == v2 returns 0."""
        assert service._compare_versions("1.0.0", "1.0.0") == 0
        assert service._compare_versions("2.3.4", "2.3.4") == 0

    def test_compare_versions_greater_than(self, service):
        """v1 > v2 returns 1."""
        assert service._compare_versions("1.0.1", "1.0.0") == 1
        assert service._compare_versions("1.1.0", "1.0.0") == 1
        assert service._compare_versions("2.0.0", "1.0.0") == 1

    def test_compare_versions_prerelease(self, service):
        """Pre-release versions compare correctly."""
        # Pre-release is less than release
        assert service._compare_versions("1.0.0-beta.1", "1.0.0") == -1
        assert service._compare_versions("1.0.0-alpha", "1.0.0-beta") == -1

    def test_compare_versions_complex(self, service):
        """Complex version strings compare correctly."""
        assert service._compare_versions("1.0.0-rc.1", "1.0.0-rc.2") == -1
        assert service._compare_versions("2.0.0-beta.10", "2.0.0-beta.9") == 1


class TestConfigHelpers:
    """Tests for configuration helper methods."""

    @pytest.fixture
    def service(self):
        """Create service with mocked session."""
        mock_session = AsyncMock(spec=AsyncSession)
        return SoftwareUpdateService(db_session=mock_session)

    @pytest.mark.asyncio
    async def test_get_config_bool_true_values(self, service):
        """Boolean config returns True for true-ish values."""
        # Test various true-ish values
        for value in ["true", "True", "TRUE", "1", "yes", "on"]:
            with patch.object(service, "_get_config", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = value
                result = await service._get_config_bool("test_key")
                assert result is True, f"Expected True for '{value}'"

    @pytest.mark.asyncio
    async def test_get_config_bool_false_values(self, service):
        """Boolean config returns False for false-ish values."""
        # Test various false-ish values
        for value in ["false", "False", "FALSE", "0", "no", "off", "hello", ""]:
            with patch.object(service, "_get_config", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = value
                result = await service._get_config_bool("test_key")
                assert result is False, f"Expected False for '{value}'"

    @pytest.mark.asyncio
    async def test_get_config_int_valid(self, service):
        """Integer config parses valid integers."""
        with patch.object(service, "_get_config", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = "42"
            value = await service._get_config_int("test_int")
            assert value == 42

    @pytest.mark.asyncio
    async def test_get_config_int_invalid_returns_default(self, service):
        """Integer config returns default for invalid values."""
        with patch.object(service, "_get_config", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = "not_a_number"
            value = await service._get_config_int("test_int_invalid", default=99)
            assert value == 99

    @pytest.mark.asyncio
    async def test_get_config_int_missing_returns_default(self, service):
        """Integer config returns default for missing keys."""
        with patch.object(service, "_get_config", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = ""
            value = await service._get_config_int("nonexistent_key", default=123)
            assert value == 123


class TestUpdateStates:
    """Tests for update state machine."""

    def test_all_states_defined(self):
        """All expected states are defined."""
        expected_states = [
            "idle",
            "checking",
            "downloading",
            "verifying",
            "backing_up",
            "stopping_services",
            "installing",
            "migrating",
            "starting_services",
            "verifying_install",
            "complete",
            "failed",
            "rolling_back",
        ]
        for state in expected_states:
            assert state in UPDATE_STATES


class TestServiceConfiguration:
    """Tests for service configuration."""

    def test_services_list_contains_only_tau_daemon(self):
        """Only tau-daemon is in the services list."""
        assert SERVICES == ["tau-daemon"]
        assert "tau-frontend" not in SERVICES


class TestInstallationRecord:
    """Tests for installation record management."""

    @pytest.mark.asyncio
    async def test_get_installation_creates_if_missing(self):
        """Installation record is created if missing."""
        mock_session = AsyncMock(spec=AsyncSession)

        # Mock execute to return None (no existing record)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        service = SoftwareUpdateService(db_session=mock_session)

        installation = await service._get_installation()

        assert installation is not None
        assert installation.id == 1
        assert installation.current_version == "0.0.0"
        assert installation.install_method == "fresh"
        # Verify it was added to session
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_current_version(self):
        """Current version is retrieved correctly."""
        mock_session = AsyncMock(spec=AsyncSession)

        # Mock installation record
        mock_installation = MagicMock()
        mock_installation.current_version = "1.2.3"
        mock_installation.install_method = "update"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_installation
        mock_session.execute.return_value = mock_result

        service = SoftwareUpdateService(db_session=mock_session)

        version = await service.get_current_version()
        assert version == "1.2.3"


class TestGitHubClientCreation:
    """Tests for GitHub client initialization."""

    @pytest.mark.asyncio
    async def test_get_github_client_raises_if_not_configured(self):
        """Error raised if GitHub repo not configured."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        service = SoftwareUpdateService(db_session=mock_session)

        with pytest.raises(UpdateError, match="GitHub repository not configured"):
            await service._get_github_client()


class TestUpdateStatusRetrieval:
    """Tests for update status retrieval."""

    @pytest.mark.asyncio
    async def test_get_update_status_with_available_update(self):
        """Status shows available update."""
        mock_session = AsyncMock(spec=AsyncSession)

        # Mock installation
        mock_installation = MagicMock()
        mock_installation.id = 1
        mock_installation.current_version = "1.0.0"
        mock_installation.installed_at = datetime.utcnow()
        mock_installation.install_method = "fresh"

        # Mock available release
        mock_release = MagicMock()
        mock_release.version = "1.1.0"
        mock_release.release_notes = "New features"

        # Mock update check
        mock_check = MagicMock()
        mock_check.checked_at = datetime.utcnow()

        # Configure mock_session.execute to return different results for different queries
        def mock_execute(query):
            result = MagicMock()
            # First call returns installation, second returns release, third returns check
            if hasattr(mock_execute, "call_count"):
                mock_execute.call_count += 1
            else:
                mock_execute.call_count = 1

            if mock_execute.call_count == 1:
                result.scalar_one_or_none.return_value = mock_installation
            elif mock_execute.call_count == 2:
                result.scalar_one_or_none.return_value = mock_release
            else:
                result.scalar_one_or_none.return_value = mock_check
            return result

        mock_session.execute.side_effect = mock_execute

        service = SoftwareUpdateService(db_session=mock_session)
        status = await service.get_update_status()

        assert status["current_version"] == "1.0.0"
        assert status["update_available"] is True
        assert status["available_version"] == "1.1.0"
        assert status["state"] == "idle"

    @pytest.mark.asyncio
    async def test_get_update_status_includes_last_check(self):
        """Status includes last check time."""
        mock_session = AsyncMock(spec=AsyncSession)

        # Mock installation
        mock_installation = MagicMock()
        mock_installation.current_version = "1.0.0"
        mock_installation.installed_at = datetime.utcnow()
        mock_installation.install_method = "fresh"

        # Mock no available release
        mock_check = MagicMock()
        mock_check.checked_at = datetime.utcnow()

        call_count = [0]

        def mock_execute(query):
            result = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                result.scalar_one_or_none.return_value = mock_installation
            elif call_count[0] == 2:
                result.scalar_one_or_none.return_value = None  # No release
            else:
                result.scalar_one_or_none.return_value = mock_check
            return result

        mock_session.execute.side_effect = mock_execute

        service = SoftwareUpdateService(db_session=mock_session)
        status = await service.get_update_status()

        assert status["last_check_at"] is not None


class TestConfigManagement:
    """Tests for configuration management."""

    @pytest.mark.asyncio
    async def test_get_config_returns_value(self):
        """Config value is retrieved correctly."""
        mock_session = AsyncMock(spec=AsyncSession)

        # Mock config result
        mock_config = MagicMock()
        mock_config.value = "owner/repo"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        service = SoftwareUpdateService(db_session=mock_session)

        value = await service._get_config("github_repo")
        assert value == "owner/repo"

    @pytest.mark.asyncio
    async def test_get_config_masks_token(self):
        """GitHub token is masked in config output."""
        mock_session = AsyncMock(spec=AsyncSession)

        # Create mock configs
        mock_configs = []
        for key, value in [("github_repo", "owner/repo"), ("github_token", "secret_token")]:
            mock_config = MagicMock()
            mock_config.key = key
            mock_config.value = value
            mock_configs.append(mock_config)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_configs
        mock_session.execute.return_value = mock_result

        service = SoftwareUpdateService(db_session=mock_session)
        config = await service.get_config()

        assert config["github_token"] == "***configured***"

    @pytest.mark.asyncio
    async def test_set_config_updates_existing(self):
        """Setting existing config updates the value."""
        mock_session = AsyncMock(spec=AsyncSession)

        # Mock existing config
        mock_config = MagicMock()
        mock_config.value = "old/repo"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_session.execute.return_value = mock_result

        service = SoftwareUpdateService(db_session=mock_session)
        await service._set_config("github_repo", "new/repo")

        # Verify the value was updated
        assert mock_config.value == "new/repo"

    @pytest.mark.asyncio
    async def test_update_config_clears_client_cache(self):
        """Changing repo config clears GitHub client cache."""
        mock_session = AsyncMock(spec=AsyncSession)

        # Mock existing config
        mock_config = MagicMock()
        mock_config.value = "old/repo"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_config
        mock_result.scalars.return_value.all.return_value = [mock_config]
        mock_session.execute.return_value = mock_result

        service = SoftwareUpdateService(db_session=mock_session)
        service._github_client = MagicMock()

        await service.update_config("github_repo", "different/repo")

        assert service._github_client is None


class TestVersionHistory:
    """Tests for version history."""

    @pytest.mark.asyncio
    async def test_get_version_history(self):
        """Version history is retrieved correctly."""
        mock_session = AsyncMock(spec=AsyncSession)

        # Mock version history entries
        mock_history = []
        for i, version in enumerate(["1.1.0", "1.0.0"]):  # Already sorted newest first
            entry = MagicMock()
            entry.version = version
            entry.installed_at = datetime(2026, 1, 2 - i)
            entry.uninstalled_at = datetime(2026, 1, 3 - i)
            entry.backup_path = f"/backup/{version}"
            entry.backup_valid = True
            entry.release_notes = None
            mock_history.append(entry)

        # Mock installation for current version check
        mock_installation = MagicMock()
        mock_installation.current_version = "1.2.0"

        call_count = [0]

        def mock_execute(query):
            result = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                result.scalars.return_value.all.return_value = mock_history
            else:
                result.scalar_one_or_none.return_value = mock_installation
            return result

        mock_session.execute.side_effect = mock_execute

        service = SoftwareUpdateService(db_session=mock_session)
        history = await service.get_version_history()

        assert len(history) == 2
        # Should be sorted newest first
        assert history[0]["version"] == "1.1.0"
        assert history[1]["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_version_history_includes_rollback_info(self):
        """Version history includes rollback capability info."""
        mock_session = AsyncMock(spec=AsyncSession)

        # Mock version history entries with valid backups
        mock_history = []
        for version in ["1.1.0", "1.0.0"]:
            entry = MagicMock()
            entry.version = version
            entry.installed_at = datetime.utcnow()
            entry.uninstalled_at = datetime.utcnow()
            entry.backup_path = f"/backup/{version}"
            entry.backup_valid = True
            entry.release_notes = None
            mock_history.append(entry)

        # Mock installation
        mock_installation = MagicMock()
        mock_installation.current_version = "1.2.0"

        call_count = [0]

        def mock_execute(query):
            result = MagicMock()
            call_count[0] += 1
            if call_count[0] == 1:
                result.scalars.return_value.all.return_value = mock_history
            else:
                result.scalar_one_or_none.return_value = mock_installation
            return result

        mock_session.execute.side_effect = mock_execute

        service = SoftwareUpdateService(db_session=mock_session)
        history = await service.get_version_history()

        for entry in history:
            assert "can_rollback" in entry
            assert entry["can_rollback"] is True  # Both have valid backups


class TestInterruptedUpdateRecovery:
    """Tests for interrupted update recovery."""

    @pytest.mark.asyncio
    async def test_recovery_when_no_interrupted_update(self):
        """Recovery returns no action when no update was interrupted."""
        mock_session = AsyncMock(spec=AsyncSession)
        service = SoftwareUpdateService(db_session=mock_session)
        service._current_state = "idle"

        result = await service.recover_from_interrupted_update()

        assert result["recovered"] is False
        assert "No interrupted update detected" in result.get("message", "")

    @pytest.mark.asyncio
    async def test_recovery_cleans_partial_downloads(self):
        """Recovery cleans up partial downloads."""
        mock_session = AsyncMock(spec=AsyncSession)
        service = SoftwareUpdateService(db_session=mock_session)
        service._current_state = "downloading"

        # Mock the backup manager
        mock_backup_manager = AsyncMock()
        mock_backup_manager.list_backups.return_value = []
        service._backup_manager = mock_backup_manager

        # Create temp download directory
        import tempfile
        import shutil
        download_dir = Path("/tmp/tau-updates")
        download_dir.mkdir(parents=True, exist_ok=True)
        (download_dir / "partial.deb").write_text("partial")

        with patch.object(service, "_verify_installation", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = True
            result = await service.recover_from_interrupted_update()

        assert result["recovered"] is True
        assert "cleaned_partial_downloads" in result.get("actions", [])

        # Cleanup
        if download_dir.exists():
            shutil.rmtree(download_dir, ignore_errors=True)


class TestExceptionTypes:
    """Tests for custom exception types."""

    def test_update_error(self):
        """UpdateError is properly raised."""
        with pytest.raises(UpdateError):
            raise UpdateError("Test error")

    def test_checksum_mismatch_error(self):
        """ChecksumMismatchError inherits from UpdateError."""
        assert issubclass(ChecksumMismatchError, UpdateError)

    def test_installation_error(self):
        """InstallationError inherits from UpdateError."""
        assert issubclass(InstallationError, UpdateError)

    def test_rollback_error(self):
        """RollbackError inherits from UpdateError."""
        assert issubclass(RollbackError, UpdateError)
