"""
Tests for transition and easing functions.

Tests cover:
- Easing function correctness (boundary values, midpoint behavior)
- Proportional transition time calculation
- TransitionConfig behavior
"""
import pytest
import math
from tau.logic.transitions import (
    EasingFunction,
    DEFAULT_EASING,
    ease_linear,
    ease_in_quadratic,
    ease_out_quadratic,
    ease_in_out_quadratic,
    ease_in_cubic,
    ease_out_cubic,
    ease_in_out_cubic,
    apply_easing,
    interpolate_with_easing,
    get_easing_function,
    TransitionConfig,
    get_transition_config,
    set_transition_config,
    calculate_brightness_transition_time,
    calculate_cct_transition_time,
    calculate_combined_transition_time,
)


class TestEasingFunctions:
    """Tests for individual easing functions."""

    @pytest.mark.parametrize("ease_func", [
        ease_linear,
        ease_in_quadratic,
        ease_out_quadratic,
        ease_in_out_quadratic,
        ease_in_cubic,
        ease_out_cubic,
        ease_in_out_cubic,
    ])
    def test_boundary_values(self, ease_func):
        """All easing functions should return 0 at t=0 and 1 at t=1."""
        assert ease_func(0.0) == pytest.approx(0.0, abs=1e-9)
        assert ease_func(1.0) == pytest.approx(1.0, abs=1e-9)

    def test_linear_is_identity(self):
        """Linear easing should return input unchanged."""
        for t in [0.0, 0.25, 0.5, 0.75, 1.0]:
            assert ease_linear(t) == pytest.approx(t, abs=1e-9)

    def test_ease_in_starts_slow(self):
        """Ease-in should be slower at the start (below linear)."""
        # At t=0.25, ease_in should be less than 0.25
        assert ease_in_quadratic(0.25) < 0.25
        assert ease_in_cubic(0.25) < ease_in_quadratic(0.25)  # Cubic even slower

    def test_ease_out_starts_fast(self):
        """Ease-out should be faster at the start (above linear)."""
        # At t=0.25, ease_out should be greater than 0.25
        assert ease_out_quadratic(0.25) > 0.25
        assert ease_out_cubic(0.25) > ease_out_quadratic(0.25)  # Cubic even faster

    def test_ease_in_out_symmetry(self):
        """Ease-in-out should be symmetric around t=0.5."""
        # f(0.5 - x) + f(0.5 + x) should equal 1.0
        for x in [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]:
            left = ease_in_out_quadratic(0.5 - x)
            right = ease_in_out_quadratic(0.5 + x)
            assert left + right == pytest.approx(1.0, abs=1e-9)

    def test_ease_in_out_midpoint(self):
        """Ease-in-out should return 0.5 at t=0.5."""
        assert ease_in_out_quadratic(0.5) == pytest.approx(0.5, abs=1e-9)
        assert ease_in_out_cubic(0.5) == pytest.approx(0.5, abs=1e-9)

    def test_quadratic_ease_in_formula(self):
        """Quadratic ease-in should follow t^2."""
        for t in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]:
            assert ease_in_quadratic(t) == pytest.approx(t * t, abs=1e-9)

    def test_cubic_ease_in_formula(self):
        """Cubic ease-in should follow t^3."""
        for t in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]:
            assert ease_in_cubic(t) == pytest.approx(t * t * t, abs=1e-9)


class TestApplyEasing:
    """Tests for the apply_easing helper function."""

    def test_clamps_input(self):
        """Apply easing should clamp input to 0-1 range."""
        assert apply_easing(-0.5) == pytest.approx(0.0, abs=1e-9)
        assert apply_easing(1.5) == pytest.approx(1.0, abs=1e-9)

    def test_uses_default_easing(self):
        """Should use DEFAULT_EASING when not specified."""
        result = apply_easing(0.5)
        expected = get_easing_function(DEFAULT_EASING)(0.5)
        assert result == pytest.approx(expected, abs=1e-9)

    def test_respects_easing_parameter(self):
        """Should use the specified easing function."""
        assert apply_easing(0.5, EasingFunction.LINEAR) == pytest.approx(0.5, abs=1e-9)
        assert apply_easing(0.5, EasingFunction.EASE_IN) == pytest.approx(0.25, abs=1e-9)


class TestInterpolateWithEasing:
    """Tests for interpolation with easing."""

    def test_basic_interpolation(self):
        """Linear easing should give linear interpolation."""
        result = interpolate_with_easing(0.0, 100.0, 0.5, EasingFunction.LINEAR)
        assert result == pytest.approx(50.0, abs=1e-9)

    def test_start_and_end(self):
        """At t=0 should return start, at t=1 should return end."""
        start, end = 10.0, 90.0
        for easing in EasingFunction:
            assert interpolate_with_easing(start, end, 0.0, easing) == pytest.approx(start, abs=1e-9)
            assert interpolate_with_easing(start, end, 1.0, easing) == pytest.approx(end, abs=1e-9)

    def test_negative_values(self):
        """Should work with negative ranges."""
        result = interpolate_with_easing(100.0, 0.0, 0.5, EasingFunction.LINEAR)
        assert result == pytest.approx(50.0, abs=1e-9)

    def test_ease_in_slower_at_start(self):
        """Ease-in should be below linear at midpoint."""
        linear_mid = interpolate_with_easing(0.0, 100.0, 0.5, EasingFunction.LINEAR)
        ease_in_mid = interpolate_with_easing(0.0, 100.0, 0.5, EasingFunction.EASE_IN)
        assert ease_in_mid < linear_mid


class TestTransitionConfig:
    """Tests for TransitionConfig dataclass."""

    def test_default_values(self):
        """Should have sensible defaults."""
        config = TransitionConfig()
        assert config.brightness_transition_seconds == 0.5
        assert config.cct_transition_seconds == 0.5
        assert config.default_easing == DEFAULT_EASING
        assert config.min_transition_seconds == 0.0
        assert config.max_transition_seconds == 60.0

    def test_custom_values(self):
        """Should accept custom values."""
        config = TransitionConfig(
            brightness_transition_seconds=2.0,
            cct_transition_seconds=3.0,
            default_easing=EasingFunction.LINEAR,
            min_transition_seconds=0.1,
            max_transition_seconds=30.0,
        )
        assert config.brightness_transition_seconds == 2.0
        assert config.cct_transition_seconds == 3.0
        assert config.default_easing == EasingFunction.LINEAR


class TestGlobalConfig:
    """Tests for global transition config management."""

    def test_get_returns_config(self):
        """get_transition_config should return a TransitionConfig."""
        config = get_transition_config()
        assert isinstance(config, TransitionConfig)

    def test_set_and_get(self):
        """set_transition_config should update global config."""
        original = get_transition_config()
        new_config = TransitionConfig(brightness_transition_seconds=5.0)

        try:
            set_transition_config(new_config)
            assert get_transition_config().brightness_transition_seconds == 5.0
        finally:
            # Restore original
            set_transition_config(original)


class TestBrightnessTransitionTime:
    """Tests for calculate_brightness_transition_time."""

    def test_full_range(self):
        """Full range (0 to 1) should use full configured time."""
        config = TransitionConfig(brightness_transition_seconds=2.0)
        duration = calculate_brightness_transition_time(0.0, 1.0, config)
        assert duration == pytest.approx(2.0, abs=1e-9)

    def test_half_range(self):
        """Half the range should use half the time."""
        config = TransitionConfig(brightness_transition_seconds=2.0)
        duration = calculate_brightness_transition_time(0.0, 0.5, config)
        assert duration == pytest.approx(1.0, abs=1e-9)

    def test_quarter_range(self):
        """Quarter range should use quarter time."""
        config = TransitionConfig(brightness_transition_seconds=2.0)
        duration = calculate_brightness_transition_time(0.25, 0.5, config)
        assert duration == pytest.approx(0.5, abs=1e-9)

    def test_symmetric(self):
        """Direction shouldn't matter - up and down should be same time."""
        config = TransitionConfig(brightness_transition_seconds=2.0)
        up = calculate_brightness_transition_time(0.2, 0.8, config)
        down = calculate_brightness_transition_time(0.8, 0.2, config)
        assert up == pytest.approx(down, abs=1e-9)

    def test_no_change(self):
        """No change should return 0 (or min) duration."""
        config = TransitionConfig(brightness_transition_seconds=2.0, min_transition_seconds=0.0)
        duration = calculate_brightness_transition_time(0.5, 0.5, config)
        assert duration == pytest.approx(0.0, abs=1e-9)

    def test_respects_min(self):
        """Should respect min_transition_seconds."""
        config = TransitionConfig(
            brightness_transition_seconds=1.0,
            min_transition_seconds=0.5
        )
        # Very small change would be < 0.5, but should be clamped to min
        duration = calculate_brightness_transition_time(0.5, 0.51, config)
        assert duration >= 0.5

    def test_respects_max(self):
        """Should respect max_transition_seconds."""
        config = TransitionConfig(
            brightness_transition_seconds=100.0,  # Very long
            max_transition_seconds=5.0
        )
        duration = calculate_brightness_transition_time(0.0, 1.0, config)
        assert duration <= 5.0


class TestCCTTransitionTime:
    """Tests for calculate_cct_transition_time."""

    def test_full_range(self):
        """Full CCT range should use full configured time."""
        config = TransitionConfig(cct_transition_seconds=2.0)
        duration = calculate_cct_transition_time(2700, 6500, 2700, 6500, config)
        assert duration == pytest.approx(2.0, abs=1e-9)

    def test_half_range(self):
        """Half the CCT range should use half the time."""
        config = TransitionConfig(cct_transition_seconds=2.0)
        # 2700 to 4600 is about half of 2700-6500 range (3800K span vs 3800K total)
        duration = calculate_cct_transition_time(2700, 4600, 2700, 6500, config)
        expected = 2.0 * (1900 / 3800)  # Half the range
        assert duration == pytest.approx(expected, abs=0.01)

    def test_symmetric(self):
        """Direction shouldn't matter - warm to cool same as cool to warm."""
        config = TransitionConfig(cct_transition_seconds=2.0)
        up = calculate_cct_transition_time(3000, 5000, 2700, 6500, config)
        down = calculate_cct_transition_time(5000, 3000, 2700, 6500, config)
        assert up == pytest.approx(down, abs=1e-9)

    def test_zero_range(self):
        """Zero CCT range should return 0."""
        config = TransitionConfig(cct_transition_seconds=2.0)
        duration = calculate_cct_transition_time(2700, 2700, 2700, 2700, config)
        assert duration == 0.0

    def test_no_change(self):
        """No CCT change should return 0."""
        config = TransitionConfig(cct_transition_seconds=2.0)
        duration = calculate_cct_transition_time(4000, 4000, 2700, 6500, config)
        assert duration == pytest.approx(0.0, abs=1e-9)


class TestCombinedTransitionTime:
    """Tests for calculate_combined_transition_time."""

    def test_returns_longer_time(self):
        """Should return the longer of brightness or CCT transition."""
        config = TransitionConfig(
            brightness_transition_seconds=1.0,
            cct_transition_seconds=2.0
        )
        # Full brightness change (1.0s) vs full CCT change (2.0s)
        duration = calculate_combined_transition_time(
            start_brightness=0.0,
            end_brightness=1.0,
            start_cct=2700,
            end_cct=6500,
            cct_min=2700,
            cct_max=6500,
            config=config
        )
        assert duration == pytest.approx(2.0, abs=1e-9)

    def test_brightness_only(self):
        """With no CCT change, should use brightness time."""
        config = TransitionConfig(brightness_transition_seconds=1.0)
        duration = calculate_combined_transition_time(
            start_brightness=0.0,
            end_brightness=1.0,
            start_cct=4000,
            end_cct=4000,  # No change
            cct_min=2700,
            cct_max=6500,
            config=config
        )
        assert duration == pytest.approx(1.0, abs=1e-9)

    def test_cct_only(self):
        """With no brightness change, should use CCT time."""
        config = TransitionConfig(cct_transition_seconds=2.0)
        duration = calculate_combined_transition_time(
            start_brightness=0.5,
            end_brightness=0.5,  # No change
            start_cct=2700,
            end_cct=6500,
            cct_min=2700,
            cct_max=6500,
            config=config
        )
        assert duration == pytest.approx(2.0, abs=1e-9)

    def test_handles_none_cct(self):
        """Should handle None CCT values gracefully."""
        config = TransitionConfig(brightness_transition_seconds=1.0)
        duration = calculate_combined_transition_time(
            start_brightness=0.0,
            end_brightness=1.0,
            start_cct=None,
            end_cct=None,
            cct_min=None,
            cct_max=None,
            config=config
        )
        assert duration == pytest.approx(1.0, abs=1e-9)


class TestDefaultEasing:
    """Tests for default easing configuration."""

    def test_default_is_ease_in_out(self):
        """Default easing should be EASE_IN_OUT."""
        assert DEFAULT_EASING == EasingFunction.EASE_IN_OUT

    def test_config_default_matches(self):
        """TransitionConfig default should match DEFAULT_EASING."""
        config = TransitionConfig()
        assert config.default_easing == DEFAULT_EASING
