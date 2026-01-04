"""
Tests for StateManager transition functionality.

Tests cover:
- Independent brightness and CCT transitions
- Easing function application
- Proportional transition time calculation
- Transition state tracking
"""
import pytest
import time
import sys
from pathlib import Path

# Add src to path to avoid circular imports through __init__.py
src_path = Path(__file__).parent.parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

# Import transitions first (no dependencies on state_manager)
from tau.logic.transitions import (
    EasingFunction,
    TransitionConfig,
    set_transition_config,
    get_transition_config,
)

# Import state_manager directly, bypassing __init__.py
import importlib.util
state_manager_path = src_path / "tau" / "control" / "state_manager.py"
spec = importlib.util.spec_from_file_location("state_manager", state_manager_path)
state_manager_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(state_manager_module)
StateManager = state_manager_module.StateManager
FixtureStateData = state_manager_module.FixtureStateData


@pytest.fixture
def state_manager():
    """Create a fresh StateManager for each test."""
    return StateManager()


@pytest.fixture
def fixture_with_cct(state_manager):
    """Register a fixture with CCT range configured."""
    state_manager.register_fixture(1)
    fixture = state_manager.get_fixture_state(1)
    fixture.current_brightness = 0.5
    fixture.goal_brightness = 0.5
    fixture.current_color_temp = 4000
    fixture.goal_color_temp = 4000
    fixture.cct_min = 2700
    fixture.cct_max = 6500
    return fixture


@pytest.fixture
def transition_config():
    """Create a test transition config and restore original after test."""
    original = get_transition_config()
    test_config = TransitionConfig(
        brightness_transition_seconds=1.0,
        cct_transition_seconds=1.0,
        default_easing=EasingFunction.EASE_IN_OUT,
    )
    set_transition_config(test_config)
    yield test_config
    set_transition_config(original)


class TestBrightnessTransitions:
    """Tests for brightness transition functionality."""

    def test_instant_change_no_transition(self, state_manager):
        """With transition_duration=0, change should be instant."""
        state_manager.register_fixture(1)

        state_manager.set_fixture_brightness(1, 0.8, transition_duration=0)

        fixture = state_manager.get_fixture_state(1)
        assert fixture.goal_brightness == 0.8
        assert fixture.current_brightness == 0.8
        assert not fixture.is_brightness_transitioning

    def test_explicit_transition_duration(self, state_manager):
        """With explicit transition_duration, should use that value."""
        state_manager.register_fixture(1)
        state_manager.set_fixture_brightness(1, 0.5, transition_duration=0, use_proportional_time=False)

        now = time.time()
        state_manager.set_fixture_brightness(1, 1.0, transition_duration=2.0, timestamp=now)

        fixture = state_manager.get_fixture_state(1)
        assert fixture.goal_brightness == 1.0
        assert fixture.current_brightness == 0.5  # Not yet moved
        assert fixture.is_brightness_transitioning
        assert fixture.brightness_transition_duration == 2.0

    def test_proportional_time_full_range(self, state_manager, transition_config):
        """Full brightness range should use full configured time."""
        state_manager.register_fixture(1)
        state_manager.set_fixture_brightness(1, 0.0, transition_duration=0, use_proportional_time=False)

        now = time.time()
        # From 0 to 1 = full range
        state_manager.set_fixture_brightness(
            1, 1.0,
            transition_duration=None,
            use_proportional_time=True,
            timestamp=now
        )

        fixture = state_manager.get_fixture_state(1)
        assert fixture.brightness_transition_duration == pytest.approx(1.0, abs=0.01)

    def test_proportional_time_half_range(self, state_manager, transition_config):
        """Half brightness range should use half configured time."""
        state_manager.register_fixture(1)
        state_manager.set_fixture_brightness(1, 0.0, transition_duration=0, use_proportional_time=False)

        now = time.time()
        # From 0 to 0.5 = half range
        state_manager.set_fixture_brightness(
            1, 0.5,
            transition_duration=None,
            use_proportional_time=True,
            timestamp=now
        )

        fixture = state_manager.get_fixture_state(1)
        assert fixture.brightness_transition_duration == pytest.approx(0.5, abs=0.01)

    def test_easing_function_stored(self, state_manager):
        """Easing function should be stored on fixture."""
        state_manager.register_fixture(1)

        now = time.time()
        state_manager.set_fixture_brightness(
            1, 0.8,
            transition_duration=1.0,
            easing=EasingFunction.EASE_IN_CUBIC,
            timestamp=now
        )

        fixture = state_manager.get_fixture_state(1)
        assert fixture.brightness_easing == EasingFunction.EASE_IN_CUBIC


class TestCCTTransitions:
    """Tests for CCT transition functionality."""

    def test_instant_change_no_transition(self, state_manager, fixture_with_cct):
        """With transition_duration=0, CCT change should be instant."""
        state_manager.set_fixture_color_temp(1, 5000, transition_duration=0)

        fixture = state_manager.get_fixture_state(1)
        assert fixture.goal_color_temp == 5000
        assert fixture.current_color_temp == 5000
        assert not fixture.is_cct_transitioning

    def test_explicit_transition_duration(self, state_manager, fixture_with_cct):
        """With explicit transition_duration, should use that value."""
        now = time.time()
        state_manager.set_fixture_color_temp(1, 5000, transition_duration=2.0, timestamp=now)

        fixture = state_manager.get_fixture_state(1)
        assert fixture.goal_color_temp == 5000
        assert fixture.current_color_temp == 4000  # Not yet moved
        assert fixture.is_cct_transitioning
        assert fixture.cct_transition_duration == 2.0

    def test_proportional_time_full_range(self, state_manager, fixture_with_cct, transition_config):
        """Full CCT range should use full configured time."""
        # Set to min
        state_manager.set_fixture_color_temp(1, 2700, transition_duration=0, use_proportional_time=False)

        now = time.time()
        # From min to max = full range
        state_manager.set_fixture_color_temp(
            1, 6500,
            transition_duration=None,
            use_proportional_time=True,
            timestamp=now
        )

        fixture = state_manager.get_fixture_state(1)
        assert fixture.cct_transition_duration == pytest.approx(1.0, abs=0.01)

    def test_easing_function_stored(self, state_manager, fixture_with_cct):
        """Easing function should be stored on fixture."""
        now = time.time()
        state_manager.set_fixture_color_temp(
            1, 5000,
            transition_duration=1.0,
            easing=EasingFunction.EASE_OUT,
            timestamp=now
        )

        fixture = state_manager.get_fixture_state(1)
        assert fixture.cct_easing == EasingFunction.EASE_OUT


class TestIndependentTransitions:
    """Tests for independent brightness and CCT transitions."""

    def test_can_have_different_durations(self, state_manager, fixture_with_cct):
        """Brightness and CCT can have different transition durations."""
        now = time.time()

        state_manager.set_fixture_brightness(1, 1.0, transition_duration=1.0, timestamp=now)
        state_manager.set_fixture_color_temp(1, 6500, transition_duration=2.0, timestamp=now)

        fixture = state_manager.get_fixture_state(1)
        assert fixture.brightness_transition_duration == 1.0
        assert fixture.cct_transition_duration == 2.0
        assert fixture.is_brightness_transitioning
        assert fixture.is_cct_transitioning

    def test_can_have_different_easings(self, state_manager, fixture_with_cct):
        """Brightness and CCT can have different easing functions."""
        now = time.time()

        state_manager.set_fixture_brightness(
            1, 1.0,
            transition_duration=1.0,
            easing=EasingFunction.EASE_IN,
            timestamp=now
        )
        state_manager.set_fixture_color_temp(
            1, 6500,
            transition_duration=1.0,
            easing=EasingFunction.EASE_OUT,
            timestamp=now
        )

        fixture = state_manager.get_fixture_state(1)
        assert fixture.brightness_easing == EasingFunction.EASE_IN
        assert fixture.cct_easing == EasingFunction.EASE_OUT

    def test_brightness_completes_before_cct(self, state_manager, fixture_with_cct):
        """Shorter brightness transition should complete while CCT continues."""
        now = time.time()

        state_manager.set_fixture_brightness(1, 1.0, transition_duration=0.5, timestamp=now)
        state_manager.set_fixture_color_temp(1, 6500, transition_duration=2.0, timestamp=now)

        # After 0.6 seconds, brightness should be done, CCT still going
        state_manager.update_fixture_transitions(timestamp=now + 0.6)

        fixture = state_manager.get_fixture_state(1)
        assert fixture.current_brightness == 1.0
        assert not fixture.is_brightness_transitioning
        assert fixture.is_cct_transitioning
        assert fixture.current_color_temp != 6500


class TestUpdateFixtureTransitions:
    """Tests for the update_fixture_transitions method."""

    def test_applies_easing(self, state_manager):
        """Transition should apply easing function."""
        state_manager.register_fixture(1)
        state_manager.set_fixture_brightness(1, 0.0, transition_duration=0, use_proportional_time=False)

        now = time.time()
        state_manager.set_fixture_brightness(
            1, 1.0,
            transition_duration=2.0,
            easing=EasingFunction.EASE_IN,  # Quadratic: slower at start
            timestamp=now
        )

        # At 50% time, ease_in should be at 25% value (t^2 = 0.5^2 = 0.25)
        state_manager.update_fixture_transitions(timestamp=now + 1.0)

        fixture = state_manager.get_fixture_state(1)
        assert fixture.current_brightness == pytest.approx(0.25, abs=0.01)

    def test_linear_easing(self, state_manager):
        """Linear easing should give linear interpolation."""
        state_manager.register_fixture(1)
        state_manager.set_fixture_brightness(1, 0.0, transition_duration=0, use_proportional_time=False)

        now = time.time()
        state_manager.set_fixture_brightness(
            1, 1.0,
            transition_duration=2.0,
            easing=EasingFunction.LINEAR,
            timestamp=now
        )

        # At 50% time, linear should be at 50% value
        state_manager.update_fixture_transitions(timestamp=now + 1.0)

        fixture = state_manager.get_fixture_state(1)
        assert fixture.current_brightness == pytest.approx(0.5, abs=0.01)

    def test_transition_completes(self, state_manager):
        """Transition should complete and clear state."""
        state_manager.register_fixture(1)
        state_manager.set_fixture_brightness(1, 0.0, transition_duration=0, use_proportional_time=False)

        now = time.time()
        state_manager.set_fixture_brightness(1, 1.0, transition_duration=1.0, timestamp=now)

        # After full duration, should be complete
        state_manager.update_fixture_transitions(timestamp=now + 1.1)

        fixture = state_manager.get_fixture_state(1)
        assert fixture.current_brightness == 1.0
        assert not fixture.is_brightness_transitioning
        assert fixture.brightness_transition_start is None

    def test_returns_transitioning_count(self, state_manager):
        """Should return count of fixtures still transitioning."""
        state_manager.register_fixture(1)
        state_manager.register_fixture(2)
        state_manager.register_fixture(3)

        now = time.time()
        state_manager.set_fixture_brightness(1, 1.0, transition_duration=1.0, timestamp=now)
        state_manager.set_fixture_brightness(2, 1.0, transition_duration=2.0, timestamp=now)
        state_manager.set_fixture_brightness(3, 1.0, transition_duration=0)  # Instant

        count = state_manager.update_fixture_transitions(timestamp=now + 0.5)
        assert count == 2  # Fixtures 1 and 2 still transitioning

        count = state_manager.update_fixture_transitions(timestamp=now + 1.5)
        assert count == 1  # Only fixture 2 still transitioning

        count = state_manager.update_fixture_transitions(timestamp=now + 2.5)
        assert count == 0  # All complete

    def test_cct_transition_with_easing(self, state_manager, fixture_with_cct):
        """CCT transition should also apply easing."""
        now = time.time()
        state_manager.set_fixture_color_temp(
            1, 6500,
            transition_duration=2.0,
            easing=EasingFunction.EASE_IN,
            timestamp=now
        )

        # At 50% time, ease_in should be at 25% of the range
        state_manager.update_fixture_transitions(timestamp=now + 1.0)

        fixture = state_manager.get_fixture_state(1)
        # From 4000 to 6500 = 2500K range
        # 25% of range = 625K
        # Expected: 4000 + 625 = 4625K
        expected_cct = 4000 + int((6500 - 4000) * 0.25)
        assert fixture.current_color_temp == pytest.approx(expected_cct, abs=50)


class TestFixtureStateDataProperties:
    """Tests for FixtureStateData transition properties."""

    def test_is_brightness_transitioning_property(self):
        """is_brightness_transitioning should reflect transition state."""
        fixture = FixtureStateData(fixture_id=1)

        assert not fixture.is_brightness_transitioning

        fixture.brightness_transition_start = time.time()
        fixture.brightness_transition_duration = 1.0

        assert fixture.is_brightness_transitioning

        fixture.brightness_transition_duration = 0.0

        assert not fixture.is_brightness_transitioning

    def test_is_cct_transitioning_property(self):
        """is_cct_transitioning should reflect transition state."""
        fixture = FixtureStateData(fixture_id=1)

        assert not fixture.is_cct_transitioning

        fixture.cct_transition_start = time.time()
        fixture.cct_transition_duration = 1.0

        assert fixture.is_cct_transitioning
