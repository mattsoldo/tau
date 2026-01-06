"""
API tests for system configuration endpoints.

Tests for system settings management including dim_speed_ms hot-reload functionality.
Uses mocking to avoid JSONB/SQLite compatibility issues.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from tau.api.routes.system_config import (
    update_system_setting,
    SystemSettingUpdateRequest,
)


class TestDimSpeedValidation:
    """Tests for dim_speed_ms validation logic."""

    @pytest.mark.asyncio
    async def test_dim_speed_zero_rejected(self):
        """Test that dim_speed_ms of 0 is rejected."""
        from fastapi import HTTPException

        mock_session = AsyncMock()
        mock_setting = MagicMock()
        mock_setting.key = "dim_speed_ms"
        mock_setting.value = "2000"
        mock_setting.value_type = "int"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_setting
        mock_session.execute.return_value = mock_result

        with patch("tau.api.routes.system_config.get_db_session") as mock_get_session:
            mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await update_system_setting("dim_speed_ms", SystemSettingUpdateRequest(value="0"))

            assert exc_info.value.status_code == 400
            assert "positive" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_dim_speed_negative_rejected(self):
        """Test that negative dim_speed_ms is rejected."""
        from fastapi import HTTPException

        mock_session = AsyncMock()
        mock_setting = MagicMock()
        mock_setting.key = "dim_speed_ms"
        mock_setting.value = "2000"
        mock_setting.value_type = "int"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_setting
        mock_session.execute.return_value = mock_result

        with patch("tau.api.routes.system_config.get_db_session") as mock_get_session:
            mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await update_system_setting("dim_speed_ms", SystemSettingUpdateRequest(value="-100"))

            assert exc_info.value.status_code == 400
            assert "positive" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_dim_speed_non_integer_rejected(self):
        """Test that non-integer dim_speed_ms is rejected."""
        from fastapi import HTTPException

        mock_session = AsyncMock()
        mock_setting = MagicMock()
        mock_setting.key = "dim_speed_ms"
        mock_setting.value = "2000"
        mock_setting.value_type = "int"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_setting
        mock_session.execute.return_value = mock_result

        with patch("tau.api.routes.system_config.get_db_session") as mock_get_session:
            mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            with pytest.raises(HTTPException) as exc_info:
                await update_system_setting("dim_speed_ms", SystemSettingUpdateRequest(value="not_a_number"))

            assert exc_info.value.status_code == 400
            assert "invalid" in exc_info.value.detail.lower()


class TestDimSpeedHotReload:
    """Tests for dim_speed_ms hot-reload functionality."""

    @pytest.mark.asyncio
    async def test_hot_reload_called_on_update(self):
        """Test that updating dim_speed_ms triggers hot-reload."""
        mock_session = AsyncMock()
        mock_setting = MagicMock()
        mock_setting.id = 1
        mock_setting.key = "dim_speed_ms"
        mock_setting.value = "2000"
        mock_setting.value_type = "int"
        mock_setting.description = "Time in milliseconds for dimming"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_setting
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_controller = MagicMock()
        mock_daemon = MagicMock()
        mock_daemon.lighting_controller = mock_controller

        with patch("tau.api.routes.system_config.get_db_session") as mock_get_session, \
             patch("tau.api.routes.system_config.get_daemon_instance", return_value=mock_daemon):
            mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            await update_system_setting("dim_speed_ms", SystemSettingUpdateRequest(value="5000"))

            mock_controller.set_dim_speed_ms.assert_called_once_with(5000)

    @pytest.mark.asyncio
    async def test_no_hot_reload_when_daemon_unavailable(self):
        """Test that missing daemon doesn't break the update."""
        mock_session = AsyncMock()
        mock_setting = MagicMock()
        mock_setting.id = 1
        mock_setting.key = "dim_speed_ms"
        mock_setting.value = "2000"
        mock_setting.value_type = "int"
        mock_setting.description = "Time in milliseconds for dimming"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_setting
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        with patch("tau.api.routes.system_config.get_db_session") as mock_get_session, \
             patch("tau.api.routes.system_config.get_daemon_instance", return_value=None):
            mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            # Should not raise - just skip hot reload
            result = await update_system_setting("dim_speed_ms", SystemSettingUpdateRequest(value="4000"))

            assert mock_setting.value == "4000"

    @pytest.mark.asyncio
    async def test_hot_reload_error_does_not_fail_request(self):
        """Test that hot-reload errors don't fail the API request."""
        mock_session = AsyncMock()
        mock_setting = MagicMock()
        mock_setting.id = 1
        mock_setting.key = "dim_speed_ms"
        mock_setting.value = "2000"
        mock_setting.value_type = "int"
        mock_setting.description = "Time in milliseconds for dimming"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_setting
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_controller = MagicMock()
        mock_controller.set_dim_speed_ms.side_effect = RuntimeError("Hardware error")
        mock_daemon = MagicMock()
        mock_daemon.lighting_controller = mock_controller

        with patch("tau.api.routes.system_config.get_db_session") as mock_get_session, \
             patch("tau.api.routes.system_config.get_daemon_instance", return_value=mock_daemon):
            mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            # Should not raise - just log the error
            result = await update_system_setting("dim_speed_ms", SystemSettingUpdateRequest(value="6000"))

            # Setting should still be updated
            assert mock_setting.value == "6000"

    @pytest.mark.asyncio
    async def test_no_hot_reload_when_controller_unavailable(self):
        """Test that missing lighting_controller doesn't break the update."""
        mock_session = AsyncMock()
        mock_setting = MagicMock()
        mock_setting.id = 1
        mock_setting.key = "dim_speed_ms"
        mock_setting.value = "2000"
        mock_setting.value_type = "int"
        mock_setting.description = "Time in milliseconds for dimming"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_setting
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_daemon = MagicMock()
        mock_daemon.lighting_controller = None

        with patch("tau.api.routes.system_config.get_db_session") as mock_get_session, \
             patch("tau.api.routes.system_config.get_daemon_instance", return_value=mock_daemon):
            mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            # Should not raise - just skip hot reload
            result = await update_system_setting("dim_speed_ms", SystemSettingUpdateRequest(value="3500"))

            assert mock_setting.value == "3500"


class TestOtherSettingsNotHotReloaded:
    """Tests to ensure only dim_speed_ms triggers hot-reload."""

    @pytest.mark.asyncio
    async def test_other_settings_do_not_trigger_hot_reload(self):
        """Test that other settings don't trigger hot-reload."""
        mock_session = AsyncMock()
        mock_setting = MagicMock()
        mock_setting.id = 2
        mock_setting.key = "some_other_setting"
        mock_setting.value = "old_value"
        mock_setting.value_type = "str"
        mock_setting.description = "Some other setting"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_setting
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_controller = MagicMock()
        mock_daemon = MagicMock()
        mock_daemon.lighting_controller = mock_controller

        with patch("tau.api.routes.system_config.get_db_session") as mock_get_session, \
             patch("tau.api.routes.system_config.get_daemon_instance", return_value=mock_daemon):
            mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_get_session.return_value.__aexit__ = AsyncMock(return_value=None)

            await update_system_setting("some_other_setting", SystemSettingUpdateRequest(value="new_value"))

            # set_dim_speed_ms should NOT be called for other settings
            mock_controller.set_dim_speed_ms.assert_not_called()
