"""
Tests for DMX output deduplication in the lighting controller.
"""
import sys
from pathlib import Path

# Add src directory to path for imports
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

import pytest
from unittest.mock import AsyncMock, MagicMock

from tau.control.state_manager import StateManager
from tau.logic.controller import LightingController
import tau.logic.controller as controller_module


def build_controller(dmx_dedupe_enabled: bool = True):
    """Create a controller with a single fixture and mock hardware."""
    state_manager = StateManager()
    state_manager.register_fixture(1)
    fixture_state = state_manager.fixtures[1]
    fixture_state.current_brightness = 0.5
    fixture_state.dmx_universe = 0
    fixture_state.dmx_channel_start = 1
    fixture_state.secondary_dmx_channel = None

    hardware_manager = MagicMock()
    hardware_manager.set_fixture_dmx = AsyncMock()

    controller = LightingController(
        state_manager=state_manager,
        hardware_manager=hardware_manager,
        dmx_dedupe_enabled=dmx_dedupe_enabled,
    )

    return controller, hardware_manager, state_manager


@pytest.fixture
def controller_bundle():
    return build_controller()


@pytest.mark.asyncio
async def test_dmx_output_skips_when_unchanged(controller_bundle):
    """Ensure identical output values do not trigger redundant writes."""
    controller, hardware_manager, _ = controller_bundle

    await controller._update_hardware()
    await controller._update_hardware()

    assert hardware_manager.set_fixture_dmx.call_count == 1


@pytest.mark.asyncio
async def test_dmx_output_sends_on_change(controller_bundle):
    """Ensure output changes trigger a new DMX write."""
    controller, hardware_manager, state_manager = controller_bundle

    await controller._update_hardware()

    state_manager.fixtures[1].current_brightness = 0.6
    await controller._update_hardware()

    assert hardware_manager.set_fixture_dmx.call_count == 2
    last_call = hardware_manager.set_fixture_dmx.call_args_list[-1].kwargs
    assert last_call["values"] == [153]


@pytest.mark.asyncio
async def test_dmx_output_resends_after_ttl(monkeypatch):
    """Ensure unchanged output is resent after TTL expires."""
    controller, hardware_manager, _ = build_controller()

    times = iter([0.0, 0.5, 1.2])
    monkeypatch.setattr(controller_module.time, "time", lambda: next(times))

    await controller._update_hardware()
    await controller._update_hardware()
    await controller._update_hardware()

    assert hardware_manager.set_fixture_dmx.call_count == 2


@pytest.mark.asyncio
async def test_dmx_output_dedupe_disabled_always_sends():
    """Ensure dedupe can be disabled globally."""
    controller, hardware_manager, _ = build_controller(dmx_dedupe_enabled=False)

    await controller._update_hardware()
    await controller._update_hardware()

    assert hardware_manager.set_fixture_dmx.call_count == 2
