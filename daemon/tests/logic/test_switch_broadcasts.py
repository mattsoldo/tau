"""
Tests for switch broadcast integration.

Tests cover:
- Broadcast calls during switch actions (momentary, latching, retractive)
- Broadcast throttling during hold events
- Error handling in broadcast methods
- Broadcast behavior for both fixture and group targets
"""
import sys
from pathlib import Path

# Add src directory to path for imports
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, call
from tau.logic.switches import SwitchHandler, SwitchState
from tau.models.switches import Switch, SwitchModel


@pytest.fixture
def mock_state_manager():
    """Mock state manager for testing."""
    manager = Mock()
    manager.get_fixture_state = Mock(return_value=Mock(
        brightness=0.5,
        goal_brightness=0.5,
        color_temp=3000,
        goal_color_temp=3000
    ))
    manager.get_group_state = Mock(return_value=Mock(
        brightness=0.5,
        circadian_enabled=False,
        circadian_color_temp=None
    ))
    manager.set_fixture_brightness = Mock()
    manager.set_group_brightness = Mock()
    manager.fixture_group_memberships = {}
    return manager


@pytest.fixture
def mock_hardware_manager():
    """Mock hardware manager for testing."""
    return Mock()


@pytest.fixture
def switch_handler(mock_state_manager, mock_hardware_manager):
    """Create a switch handler instance with mocked dependencies."""
    handler = SwitchHandler(
        state_manager=mock_state_manager,
        hardware_manager=mock_hardware_manager,
        hold_threshold=0.5
    )
    # Manually set dim_speed_ms if needed (for backwards compatibility)
    handler.dim_speed_ms = 700
    return handler


@pytest.fixture
def momentary_fixture_switch():
    """Mock momentary switch targeting a fixture."""
    switch = Mock(spec=Switch)
    switch.id = 1
    switch.target_fixture_id = 10
    switch.target_group_id = None
    return switch


@pytest.fixture
def momentary_group_switch():
    """Mock momentary switch targeting a group."""
    switch = Mock(spec=Switch)
    switch.id = 2
    switch.target_fixture_id = None
    switch.target_group_id = 20
    return switch


@pytest.fixture
def retractive_switch():
    """Mock retractive switch for dimming tests."""
    switch = Mock(spec=Switch)
    switch.id = 3
    switch.target_fixture_id = 30
    switch.target_group_id = None
    return switch


@pytest.fixture
def switch_model():
    """Mock switch model."""
    model = Mock(spec=SwitchModel)
    model.debounce_ms = 50
    model.dimming_curve = "linear"
    return model


class TestBroadcastIntegration:
    """Tests for broadcast calls during switch actions."""

    @pytest.mark.asyncio
    async def test_momentary_fixture_broadcast(
        self,
        switch_handler,
        momentary_fixture_switch,
        switch_model
    ):
        """Test that momentary switch press broadcasts fixture state."""
        with patch('tau.logic.switches.broadcast_fixture_state_change') as mock_broadcast:
            mock_broadcast.return_value = asyncio.Future()
            mock_broadcast.return_value.set_result(None)

            # Trigger momentary press (toggle)
            await switch_handler._broadcast_fixture_state(
                momentary_fixture_switch.target_fixture_id
            )

            # Verify broadcast was called
            mock_broadcast.assert_called_once()
            call_kwargs = mock_broadcast.call_args[1]
            assert call_kwargs['fixture_id'] == 10

    @pytest.mark.asyncio
    async def test_momentary_group_broadcast(
        self,
        switch_handler,
        momentary_group_switch
    ):
        """Test that momentary switch press broadcasts group state."""
        with patch('tau.logic.switches.broadcast_group_state_change') as mock_broadcast:
            mock_broadcast.return_value = asyncio.Future()
            mock_broadcast.return_value.set_result(None)

            # Trigger group broadcast
            await switch_handler._broadcast_group_state(
                momentary_group_switch.target_group_id
            )

            # Verify broadcast was called
            mock_broadcast.assert_called_once()
            call_kwargs = mock_broadcast.call_args[1]
            assert call_kwargs['group_id'] == 20

    @pytest.mark.asyncio
    async def test_broadcast_throttling_during_dimming(
        self,
        switch_handler,
        retractive_switch,
        mock_state_manager
    ):
        """Test that broadcasts are throttled during hold events."""
        with patch('tau.logic.switches.broadcast_fixture_state_change') as mock_broadcast:
            mock_broadcast.return_value = asyncio.Future()
            mock_broadcast.return_value.set_result(None)

            # Simulate rapid dimming updates (every 10ms)
            base_time = 1000.0
            for i in range(10):
                current_time = base_time + (i * 0.01)  # 10ms intervals
                await switch_handler._broadcast_fixture_state_throttled(
                    retractive_switch.target_fixture_id,
                    current_time
                )

            # With 100ms throttle, only 1 or 2 broadcasts should have occurred
            # (depends on timing, but definitely not all 10)
            assert mock_broadcast.call_count <= 2

    @pytest.mark.asyncio
    async def test_throttling_allows_broadcast_after_delay(
        self,
        switch_handler,
        retractive_switch
    ):
        """Test that throttling allows broadcasts after sufficient delay."""
        with patch('tau.logic.switches.broadcast_fixture_state_change') as mock_broadcast:
            mock_broadcast.return_value = asyncio.Future()
            mock_broadcast.return_value.set_result(None)

            # First broadcast at t=0
            await switch_handler._broadcast_fixture_state_throttled(
                retractive_switch.target_fixture_id,
                0.0
            )
            assert mock_broadcast.call_count == 1

            # Second broadcast at t=0.05s (50ms) - should be throttled
            await switch_handler._broadcast_fixture_state_throttled(
                retractive_switch.target_fixture_id,
                0.05
            )
            assert mock_broadcast.call_count == 1  # Still 1

            # Third broadcast at t=0.15s (150ms) - should succeed
            await switch_handler._broadcast_fixture_state_throttled(
                retractive_switch.target_fixture_id,
                0.15
            )
            assert mock_broadcast.call_count == 2  # Now 2

    @pytest.mark.asyncio
    async def test_throttling_independent_per_target(
        self,
        switch_handler
    ):
        """Test that throttling is independent for different fixtures."""
        with patch('tau.logic.switches.broadcast_fixture_state_change') as mock_broadcast:
            mock_broadcast.return_value = asyncio.Future()
            mock_broadcast.return_value.set_result(None)

            base_time = 1000.0

            # Broadcast for fixture 1
            await switch_handler._broadcast_fixture_state_throttled(1, base_time)
            # Broadcast for fixture 2 immediately after
            await switch_handler._broadcast_fixture_state_throttled(2, base_time)

            # Both should broadcast (different targets)
            assert mock_broadcast.call_count == 2


class TestBroadcastErrorHandling:
    """Tests for error handling in broadcast methods."""

    @pytest.mark.asyncio
    async def test_fixture_broadcast_error_handling(
        self,
        switch_handler,
        mock_state_manager
    ):
        """Test that broadcast errors don't crash the switch handler."""
        mock_state_manager.get_fixture_state.return_value = Mock(
            goal_brightness=0.75,
            goal_color_temp=4000
        )

        with patch('tau.logic.switches.broadcast_fixture_state_change') as mock_broadcast:
            # Simulate broadcast error
            mock_broadcast.side_effect = Exception("WebSocket error")

            # Should not raise exception
            await switch_handler._broadcast_fixture_state(10)

            # Broadcast was attempted
            mock_broadcast.assert_called_once()

    @pytest.mark.asyncio
    async def test_group_broadcast_error_handling(
        self,
        switch_handler,
        mock_state_manager
    ):
        """Test that group broadcast errors don't crash the switch handler."""
        mock_state_manager.get_group_state.return_value = Mock(
            brightness=0.5,
            circadian_enabled=True,
            circadian_color_temp=3500
        )

        with patch('tau.logic.switches.broadcast_group_state_change') as mock_broadcast:
            # Simulate broadcast error
            mock_broadcast.side_effect = Exception("Connection error")

            # Should not raise exception
            await switch_handler._broadcast_group_state(20)

            # Broadcast was attempted
            mock_broadcast.assert_called_once()

    @pytest.mark.asyncio
    async def test_broadcast_with_missing_state(
        self,
        switch_handler,
        mock_state_manager
    ):
        """Test broadcast handles missing state gracefully."""
        # State manager returns None (fixture doesn't exist)
        mock_state_manager.get_fixture_state.return_value = None

        with patch('tau.logic.switches.broadcast_fixture_state_change') as mock_broadcast:
            # Should not raise exception and should not broadcast
            await switch_handler._broadcast_fixture_state(999)

            # No broadcast should occur for missing state
            mock_broadcast.assert_not_called()


class TestBroadcastValues:
    """Tests for correctness of broadcast values."""

    @pytest.mark.asyncio
    async def test_fixture_broadcast_sends_correct_values(
        self,
        switch_handler,
        mock_state_manager
    ):
        """Test that fixture broadcast sends correct brightness and CCT."""
        mock_state_manager.get_fixture_state.return_value = Mock(
            goal_brightness=0.75,
            goal_color_temp=3500
        )

        with patch('tau.logic.switches.broadcast_fixture_state_change') as mock_broadcast:
            mock_broadcast.return_value = asyncio.Future()
            mock_broadcast.return_value.set_result(None)

            await switch_handler._broadcast_fixture_state(10)

            # Verify correct values were broadcast
            call_kwargs = mock_broadcast.call_args[1]
            assert call_kwargs['fixture_id'] == 10
            assert call_kwargs['brightness'] == 0.75
            assert call_kwargs['color_temp'] == 3500

    @pytest.mark.asyncio
    async def test_group_broadcast_sends_correct_values(
        self,
        switch_handler,
        mock_state_manager
    ):
        """Test that group broadcast sends correct brightness and CCT."""
        mock_state_manager.get_group_state.return_value = Mock(
            brightness=0.6,
            circadian_enabled=True,
            circadian_color_temp=4200
        )

        with patch('tau.logic.switches.broadcast_group_state_change') as mock_broadcast:
            mock_broadcast.return_value = asyncio.Future()
            mock_broadcast.return_value.set_result(None)

            await switch_handler._broadcast_group_state(20)

            # Verify correct values were broadcast
            call_kwargs = mock_broadcast.call_args[1]
            assert call_kwargs['group_id'] == 20
            assert call_kwargs['brightness'] == 0.6
            assert call_kwargs['color_temp'] == 4200

    @pytest.mark.asyncio
    async def test_group_broadcast_without_circadian(
        self,
        switch_handler,
        mock_state_manager
    ):
        """Test group broadcast when circadian is disabled."""
        mock_state_manager.get_group_state.return_value = Mock(
            brightness=0.8,
            circadian_enabled=False,
            circadian_color_temp=None
        )

        with patch('tau.logic.switches.broadcast_group_state_change') as mock_broadcast:
            mock_broadcast.return_value = asyncio.Future()
            mock_broadcast.return_value.set_result(None)

            await switch_handler._broadcast_group_state(20)

            # CCT should be None when circadian is disabled
            call_kwargs = mock_broadcast.call_args[1]
            assert call_kwargs['color_temp'] is None
