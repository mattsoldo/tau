"""
Unit tests for Backup Manager service.

Tests backup creation, verification, restoration, and pruning.
"""
import pytest
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from tau.services.backup_manager import (
    BackupManager,
    BackupInfo,
    BackupManifest,
    BackupError,
    InsufficientSpaceError,
    BackupNotFoundError,
    RestoreError,
)


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    backup_dir = tempfile.mkdtemp(prefix="test_backup_")
    app_dir = tempfile.mkdtemp(prefix="test_app_")
    yield {"backup": backup_dir, "app": app_dir}
    shutil.rmtree(backup_dir, ignore_errors=True)
    shutil.rmtree(app_dir, ignore_errors=True)


@pytest.fixture
def backup_manager(temp_dirs):
    """Create BackupManager with temporary directories."""
    return BackupManager(
        backup_location=temp_dirs["backup"],
        app_root=temp_dirs["app"],
        max_backups=3,
        min_free_space_mb=10,
    )


@pytest.fixture
def sample_app_structure(temp_dirs):
    """Create sample application structure."""
    app_root = Path(temp_dirs["app"])

    # Create daemon structure
    daemon_src = app_root / "daemon" / "src"
    daemon_src.mkdir(parents=True)
    (daemon_src / "main.py").write_text("print('hello')")

    # Create requirements file
    (app_root / "daemon" / "requirements.txt").write_text("fastapi==0.100.0\n")

    # Create frontend structure
    frontend_src = app_root / "frontend" / "src"
    frontend_src.mkdir(parents=True)
    (frontend_src / "App.tsx").write_text("export default App;")

    return app_root


class TestBackupManagerInit:
    """Tests for BackupManager initialization."""

    def test_init_with_defaults(self):
        """BackupManager initializes with default values."""
        manager = BackupManager()
        assert manager.backup_location == Path("/opt/tau-backups")
        assert manager.app_root == Path("/opt/tau-daemon")
        assert manager.max_backups == 3
        assert manager.min_free_space_mb == 500

    def test_init_with_custom_values(self, temp_dirs):
        """BackupManager initializes with custom values."""
        manager = BackupManager(
            backup_location=temp_dirs["backup"],
            app_root=temp_dirs["app"],
            max_backups=5,
            min_free_space_mb=100,
        )
        assert str(manager.backup_location) == temp_dirs["backup"]
        assert str(manager.app_root) == temp_dirs["app"]
        assert manager.max_backups == 5
        assert manager.min_free_space_mb == 100


class TestBackupDirNaming:
    """Tests for backup directory naming."""

    def test_get_backup_dir_format(self, backup_manager):
        """Backup directory follows expected naming format."""
        backup_dir = backup_manager._get_backup_dir("1.2.3")
        assert "1.2.3_" in str(backup_dir)
        # Should contain timestamp pattern
        assert backup_dir.parent == backup_manager.backup_location

    def test_get_backup_dir_sanitizes_version(self, backup_manager):
        """Special characters in version are sanitized."""
        backup_dir = backup_manager._get_backup_dir("1.2.3/beta")
        assert "/" not in backup_dir.name
        assert "1.2.3_beta_" in str(backup_dir)


class TestChecksumCalculation:
    """Tests for file checksum calculation."""

    def test_calculate_checksum(self, backup_manager, temp_dirs):
        """Checksum is calculated correctly."""
        test_file = Path(temp_dirs["app"]) / "test.txt"
        test_file.write_text("test content")

        checksum = backup_manager._calculate_checksum(test_file)

        # SHA256 of "test content" is known
        assert len(checksum) == 64
        assert all(c in "0123456789abcdef" for c in checksum)

    def test_checksums_differ_for_different_content(self, backup_manager, temp_dirs):
        """Different files have different checksums."""
        file1 = Path(temp_dirs["app"]) / "file1.txt"
        file2 = Path(temp_dirs["app"]) / "file2.txt"
        file1.write_text("content1")
        file2.write_text("content2")

        checksum1 = backup_manager._calculate_checksum(file1)
        checksum2 = backup_manager._calculate_checksum(file2)

        assert checksum1 != checksum2


class TestSpaceChecking:
    """Tests for disk space checking."""

    @pytest.mark.asyncio
    async def test_check_space_creates_directory(self, backup_manager, temp_dirs):
        """check_space_for_backup creates backup directory if missing."""
        shutil.rmtree(temp_dirs["backup"])
        assert not Path(temp_dirs["backup"]).exists()

        await backup_manager.check_space_for_backup()

        assert Path(temp_dirs["backup"]).exists()

    @pytest.mark.asyncio
    async def test_get_free_space_returns_int(self, backup_manager, temp_dirs):
        """_get_free_space_mb returns integer value."""
        free_space = await backup_manager._get_free_space_mb(Path(temp_dirs["backup"]))
        assert isinstance(free_space, int)
        assert free_space >= 0


class TestBackupCreation:
    """Tests for backup creation."""

    @pytest.mark.asyncio
    async def test_create_backup_success(self, backup_manager, sample_app_structure):
        """Backup is created successfully."""
        backup_info = await backup_manager.create_backup(
            version="1.0.0",
            commit_sha="abc123",
        )

        assert backup_info.version == "1.0.0"
        assert Path(backup_info.backup_path).exists()
        assert backup_info.valid is True

        # Check manifest exists
        manifest_path = Path(backup_info.backup_path) / "manifest.json"
        assert manifest_path.exists()

        with open(manifest_path) as f:
            manifest = json.load(f)
        assert manifest["version"] == "1.0.0"
        assert manifest["commit_sha"] == "abc123"

    @pytest.mark.asyncio
    async def test_create_backup_with_progress_callback(self, backup_manager, sample_app_structure):
        """Progress callback is called during backup."""
        progress_calls = []

        def progress_callback(stage, percent):
            progress_calls.append((stage, percent))

        await backup_manager.create_backup(
            version="1.0.0",
            progress_callback=progress_callback,
        )

        assert len(progress_calls) > 0
        # Should start with 0 and end with 100
        stages = [call[0] for call in progress_calls]
        assert "starting" in stages or progress_calls[0][1] == 0
        assert "complete" in stages or progress_calls[-1][1] == 100

    @pytest.mark.asyncio
    async def test_create_backup_insufficient_space(self, temp_dirs, sample_app_structure):
        """InsufficientSpaceError raised when not enough space."""
        manager = BackupManager(
            backup_location=temp_dirs["backup"],
            app_root=temp_dirs["app"],
            min_free_space_mb=999999999,  # Impossible amount
        )

        with pytest.raises(InsufficientSpaceError):
            await manager.create_backup(version="1.0.0")


class TestBackupVerification:
    """Tests for backup verification."""

    @pytest.mark.asyncio
    async def test_verify_valid_backup(self, backup_manager, sample_app_structure):
        """Valid backup passes verification."""
        backup_info = await backup_manager.create_backup(version="1.0.0")

        is_valid = await backup_manager.verify_backup(backup_info.backup_path)

        assert is_valid is True

    @pytest.mark.asyncio
    async def test_verify_missing_backup(self, backup_manager):
        """Non-existent backup fails verification."""
        is_valid = await backup_manager.verify_backup("/nonexistent/path")
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_verify_corrupted_backup(self, backup_manager, sample_app_structure):
        """Corrupted backup fails verification."""
        backup_info = await backup_manager.create_backup(version="1.0.0")

        # Corrupt a file
        backup_path = Path(backup_info.backup_path)
        for file_path in backup_path.rglob("*.py"):
            file_path.write_text("corrupted content")
            break

        is_valid = await backup_manager.verify_backup(backup_info.backup_path)
        assert is_valid is False


class TestBackupListing:
    """Tests for listing backups."""

    @pytest.mark.asyncio
    async def test_list_backups_empty(self, backup_manager):
        """Empty backup directory returns empty list."""
        backups = await backup_manager.list_backups()
        assert backups == []

    @pytest.mark.asyncio
    async def test_list_backups_sorted_by_date(self, backup_manager, sample_app_structure):
        """Backups are sorted by creation date (newest first)."""
        await backup_manager.create_backup(version="1.0.0")
        await backup_manager.create_backup(version="1.1.0")
        await backup_manager.create_backup(version="1.2.0")

        backups = await backup_manager.list_backups()

        assert len(backups) == 3
        # Most recent should be first
        assert backups[0].version == "1.2.0"
        assert backups[1].version == "1.1.0"
        assert backups[2].version == "1.0.0"


class TestBackupPruning:
    """Tests for old backup pruning."""

    @pytest.mark.asyncio
    async def test_prune_removes_excess_backups(self, temp_dirs, sample_app_structure):
        """Prune removes backups exceeding max_backups."""
        manager = BackupManager(
            backup_location=temp_dirs["backup"],
            app_root=temp_dirs["app"],
            max_backups=2,
        )

        await manager.create_backup(version="1.0.0")
        await manager.create_backup(version="1.1.0")
        await manager.create_backup(version="1.2.0")

        removed_count = await manager.prune_old_backups()

        assert removed_count == 1
        backups = await manager.list_backups()
        assert len(backups) == 2

    @pytest.mark.asyncio
    async def test_prune_keeps_newest_backups(self, temp_dirs, sample_app_structure):
        """Prune keeps the newest backups."""
        manager = BackupManager(
            backup_location=temp_dirs["backup"],
            app_root=temp_dirs["app"],
            max_backups=2,
        )

        await manager.create_backup(version="1.0.0")
        await manager.create_backup(version="1.1.0")
        await manager.create_backup(version="1.2.0")

        await manager.prune_old_backups()
        backups = await manager.list_backups()

        versions = [b.version for b in backups]
        assert "1.2.0" in versions
        assert "1.1.0" in versions
        assert "1.0.0" not in versions


class TestBackupRestoration:
    """Tests for backup restoration."""

    @pytest.mark.asyncio
    async def test_restore_backup_not_found(self, backup_manager):
        """Restoring non-existent backup raises error."""
        with pytest.raises(BackupNotFoundError):
            await backup_manager.restore_backup("/nonexistent/backup")

    @pytest.mark.asyncio
    async def test_restore_missing_manifest(self, backup_manager, temp_dirs):
        """Restoring backup without manifest raises error."""
        # Create directory without manifest
        backup_dir = Path(temp_dirs["backup"]) / "invalid_backup"
        backup_dir.mkdir()

        with pytest.raises(BackupNotFoundError):
            await backup_manager.restore_backup(str(backup_dir))


class TestBackupForVersion:
    """Tests for finding backups by version."""

    @pytest.mark.asyncio
    async def test_get_backup_for_version_found(self, backup_manager, sample_app_structure):
        """Returns backup for existing version."""
        await backup_manager.create_backup(version="1.0.0")
        await backup_manager.create_backup(version="1.1.0")

        backup = await backup_manager.get_backup_for_version("1.0.0")

        assert backup is not None
        assert backup.version == "1.0.0"

    @pytest.mark.asyncio
    async def test_get_backup_for_version_not_found(self, backup_manager, sample_app_structure):
        """Returns None for non-existent version."""
        await backup_manager.create_backup(version="1.0.0")

        backup = await backup_manager.get_backup_for_version("2.0.0")

        assert backup is None


class TestBackupDeletion:
    """Tests for backup deletion."""

    @pytest.mark.asyncio
    async def test_delete_existing_backup(self, backup_manager, sample_app_structure):
        """Successfully deletes existing backup."""
        backup_info = await backup_manager.create_backup(version="1.0.0")

        result = await backup_manager.delete_backup(backup_info.backup_path)

        assert result is True
        assert not Path(backup_info.backup_path).exists()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_backup(self, backup_manager):
        """Returns False for non-existent backup."""
        result = await backup_manager.delete_backup("/nonexistent/backup")
        assert result is False


class TestTotalBackupSize:
    """Tests for total backup size calculation."""

    @pytest.mark.asyncio
    async def test_get_total_backup_size(self, backup_manager, sample_app_structure):
        """Calculates total size of all backups."""
        await backup_manager.create_backup(version="1.0.0")
        await backup_manager.create_backup(version="1.1.0")

        total_size = await backup_manager.get_total_backup_size()

        assert total_size > 0
        assert isinstance(total_size, int)
