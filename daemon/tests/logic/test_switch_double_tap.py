import pytest
from unittest.mock import AsyncMock, Mock, patch

from tau.logic.switches import SwitchHandler, SwitchState


@pytest.fixture
def mock_state_manager():
    manager = Mock()
    manager.get_fixture_state = Mock(return_value=Mock(brightness=0.0))
    manager.get_group_state = Mock(return_value=Mock(brightness=0.0))
    manager.set_fixture_brightness = Mock(return_value=True)
    manager.set_group_brightness = Mock(return_value=True)
    manager.fixture_group_memberships = {}
    return manager


@pytest.fixture
def scene_engine():
    engine = AsyncMock()
    engine.recall_scene = AsyncMock(return_value=True)
    engine.get_scene = AsyncMock(return_value={"id": 7, "name": "Movie"})
    return engine


@pytest.fixture
def switch_handler(mock_state_manager, scene_engine):
    return SwitchHandler(
        state_manager=mock_state_manager,
        hardware_manager=Mock(),
        hold_threshold=0.5,
        scene_engine=scene_engine,
        tap_window_ms=200,
    )


@pytest.fixture
def retractive_switch():
    switch = Mock()
    switch.id = 1
    switch.target_fixture_id = 10
    switch.target_group_id = None
    switch.double_tap_scene_id = 7
    return switch


@pytest.mark.asyncio
async def test_double_tap_recalls_scene(
    switch_handler,
    scene_engine,
    retractive_switch,
    mock_state_manager,
):
    state = SwitchState(switch_id=retractive_switch.id)

    with patch("tau.api.websocket.broadcast_scene_recalled", AsyncMock()), \
         patch.object(switch_handler, "_broadcast_fixture_state", AsyncMock()):
        await switch_handler._handle_release_event(retractive_switch, state, 0.0)

        assert state.pending_single_tap is True
        assert scene_engine.recall_scene.await_count == 0
        assert mock_state_manager.set_fixture_brightness.call_count == 0

        await switch_handler._handle_release_event(retractive_switch, state, 0.1)

        scene_engine.recall_scene.assert_awaited_once_with(7)
        assert state.pending_single_tap is False
        assert mock_state_manager.set_fixture_brightness.call_count == 0


@pytest.mark.asyncio
async def test_single_tap_toggles_after_window(
    switch_handler,
    scene_engine,
    retractive_switch,
    mock_state_manager,
):
    state = SwitchState(switch_id=retractive_switch.id)

    with patch.object(switch_handler, "_broadcast_fixture_state", AsyncMock()):
        await switch_handler._handle_release_event(retractive_switch, state, 0.0)
        await switch_handler._flush_pending_tap(retractive_switch, state, 0.3)

    assert scene_engine.recall_scene.await_count == 0
    mock_state_manager.set_fixture_brightness.assert_called_once()
