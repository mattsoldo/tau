"""
Unit tests for dim speed hot-reload functionality.

Tests for SwitchHandler.set_dim_speed_ms and LightingController.set_dim_speed_ms methods.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock

from tau.logic.switches import SwitchHandler
from tau.logic.controller import LightingController


class TestSwitchHandlerDimSpeed:
    """Tests for SwitchHandler.set_dim_speed_ms method."""

    @pytest.fixture
    def switch_handler(self):
        """Create a SwitchHandler with mock dependencies."""
        mock_state_manager = MagicMock()
        mock_hardware_manager = MagicMock()
        return SwitchHandler(
            state_manager=mock_state_manager,
            hardware_manager=mock_hardware_manager,
            hold_threshold=1.0,
            dim_speed_ms=2000
        )

    def test_initial_dim_speed(self, switch_handler):
        """Test that initial dim_speed_ms is set correctly."""
        assert switch_handler.dim_speed_ms == 2000

    def test_set_dim_speed_updates_value(self, switch_handler):
        """Test that set_dim_speed_ms updates the stored value."""
        switch_handler.set_dim_speed_ms(3000)
        assert switch_handler.dim_speed_ms == 3000

    def test_set_dim_speed_multiple_updates(self, switch_handler):
        """Test that dim_speed_ms can be updated multiple times."""
        switch_handler.set_dim_speed_ms(3000)
        assert switch_handler.dim_speed_ms == 3000

        switch_handler.set_dim_speed_ms(500)
        assert switch_handler.dim_speed_ms == 500

        switch_handler.set_dim_speed_ms(10000)
        assert switch_handler.dim_speed_ms == 10000

    def test_set_dim_speed_boundary_value_one(self, switch_handler):
        """Test setting dim_speed_ms to minimum valid value (1ms)."""
        switch_handler.set_dim_speed_ms(1)
        assert switch_handler.dim_speed_ms == 1

    def test_set_dim_speed_large_value(self, switch_handler):
        """Test setting dim_speed_ms to a large value."""
        switch_handler.set_dim_speed_ms(60000)  # 60 seconds
        assert switch_handler.dim_speed_ms == 60000


class TestLightingControllerDimSpeed:
    """Tests for LightingController.set_dim_speed_ms method."""

    @pytest.fixture
    def lighting_controller(self):
        """Create a LightingController with mock dependencies."""
        mock_state_manager = MagicMock()
        mock_hardware_manager = MagicMock()

        # Mock hardware_manager.labjack to avoid attribute errors
        mock_hardware_manager.labjack = MagicMock()

        controller = LightingController(
            state_manager=mock_state_manager,
            hardware_manager=mock_hardware_manager,
            dim_speed_ms=2000
        )
        return controller

    def test_set_dim_speed_propagates_to_switch_handler(self, lighting_controller):
        """Test that set_dim_speed_ms propagates to the internal SwitchHandler."""
        lighting_controller.set_dim_speed_ms(4000)
        assert lighting_controller.switches.dim_speed_ms == 4000

    def test_set_dim_speed_multiple_updates(self, lighting_controller):
        """Test multiple dim_speed_ms updates through controller."""
        lighting_controller.set_dim_speed_ms(1000)
        assert lighting_controller.switches.dim_speed_ms == 1000

        lighting_controller.set_dim_speed_ms(5000)
        assert lighting_controller.switches.dim_speed_ms == 5000


class TestDimSpeedIntegration:
    """Integration tests for dim speed in dimming calculations."""

    @pytest.fixture
    def switch_handler_for_dimming(self):
        """Create a SwitchHandler configured for dimming tests."""
        mock_state_manager = MagicMock()
        mock_hardware_manager = MagicMock()
        return SwitchHandler(
            state_manager=mock_state_manager,
            hardware_manager=mock_hardware_manager,
            hold_threshold=1.0,
            dim_speed_ms=2000
        )

    def test_dim_speed_affects_brightness_calculation(self, switch_handler_for_dimming):
        """Test that dim_speed_ms value is accessible for brightness calculations."""
        # Verify initial dim_speed is used
        assert switch_handler_for_dimming.dim_speed_ms == 2000

        # Update and verify new value is accessible
        switch_handler_for_dimming.set_dim_speed_ms(4000)
        assert switch_handler_for_dimming.dim_speed_ms == 4000

        # The brightness calculation in _handle_hold_event uses:
        # brightness_change = hold_duration / (self.dim_speed_ms / 1000.0)
        # A longer dim_speed_ms means slower brightness change per second

        # With dim_speed_ms = 2000, holding for 1s = 50% change
        # With dim_speed_ms = 4000, holding for 1s = 25% change
        dim_speed_seconds = switch_handler_for_dimming.dim_speed_ms / 1000.0
        hold_duration = 1.0
        brightness_change = hold_duration / dim_speed_seconds

        assert brightness_change == 0.25  # 1.0 / 4.0 = 0.25
