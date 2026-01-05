"""
Tests for Dim-to-Warm (DTW) curve calculations
"""
import pytest
import math
from tau.logic.dtw import (
    DTWCurve,
    DTWConfig,
    calculate_dtw_cct,
    calculate_dtw_cct_with_config,
    get_example_values,
    validate_dtw_config,
    _apply_curve,
)


class TestDTWCurves:
    """Test DTW curve calculations"""

    def test_calculate_dtw_cct_full_brightness_returns_max(self):
        """At full brightness, CCT should equal max_cct"""
        result = calculate_dtw_cct(1.0, min_cct=1800, max_cct=4000, curve=DTWCurve.LINEAR)
        assert result == 4000

    def test_calculate_dtw_cct_zero_brightness_returns_min(self):
        """At zero brightness, CCT should equal min_cct"""
        result = calculate_dtw_cct(0.0, min_cct=1800, max_cct=4000, curve=DTWCurve.LINEAR)
        assert result == 1800

    def test_calculate_dtw_cct_linear_midpoint(self):
        """Linear curve at 50% brightness should be at midpoint CCT"""
        result = calculate_dtw_cct(0.5, min_cct=1800, max_cct=4000, curve=DTWCurve.LINEAR)
        expected = 1800 + (4000 - 1800) * 0.5
        assert result == expected

    def test_calculate_dtw_cct_log_curve(self):
        """Logarithmic curve should produce warmer CCT at low brightness"""
        # At 50% brightness, log curve should be closer to max CCT than linear
        linear_result = calculate_dtw_cct(0.5, min_cct=1800, max_cct=4000, curve=DTWCurve.LINEAR)
        log_result = calculate_dtw_cct(0.5, min_cct=1800, max_cct=4000, curve=DTWCurve.LOG)

        # Log curve at 0.5 should give higher CCT than linear (steeper change at low end)
        assert log_result > linear_result

    def test_calculate_dtw_cct_square_curve(self):
        """Square curve should produce warmer CCT at mid brightness"""
        # At 50% brightness, square gives 0.25, so closer to min
        linear_result = calculate_dtw_cct(0.5, min_cct=1800, max_cct=4000, curve=DTWCurve.LINEAR)
        square_result = calculate_dtw_cct(0.5, min_cct=1800, max_cct=4000, curve=DTWCurve.SQUARE)

        # Square curve at 0.5 should give lower CCT (0.5^2 = 0.25)
        assert square_result < linear_result

    def test_calculate_dtw_cct_incandescent_curve(self):
        """Incandescent curve should produce warmer CCT at low brightness"""
        # At 50% brightness, incandescent (0.25 power) gives higher value
        linear_result = calculate_dtw_cct(0.5, min_cct=1800, max_cct=4000, curve=DTWCurve.LINEAR)
        incandescent_result = calculate_dtw_cct(0.5, min_cct=1800, max_cct=4000, curve=DTWCurve.INCANDESCENT)

        # Incandescent at 0.5 should give higher CCT (0.5^0.25 ≈ 0.84)
        assert incandescent_result > linear_result

    def test_calculate_dtw_cct_clamps_brightness_high(self):
        """Brightness above 1.0 should be clamped to 1.0"""
        result = calculate_dtw_cct(1.5, min_cct=1800, max_cct=4000, curve=DTWCurve.LINEAR)
        assert result == 4000

    def test_calculate_dtw_cct_negative_brightness_returns_min(self):
        """Negative brightness should return min_cct"""
        result = calculate_dtw_cct(-0.5, min_cct=1800, max_cct=4000, curve=DTWCurve.LINEAR)
        assert result == 1800

    def test_calculate_dtw_cct_min_brightness_floor(self):
        """Brightness below min_brightness should use min_brightness"""
        # Very low brightness should still return min_cct
        result = calculate_dtw_cct(0.0001, min_cct=1800, max_cct=4000, min_brightness=0.01, curve=DTWCurve.LINEAR)
        # Should use min_brightness floor (0.01), not 0.0001
        expected_floor = calculate_dtw_cct(0.01, min_cct=1800, max_cct=4000, min_brightness=0.001, curve=DTWCurve.LINEAR)
        assert result == expected_floor

    def test_calculate_dtw_cct_invalid_cct_range_raises(self):
        """min_cct >= max_cct should raise ValueError"""
        with pytest.raises(ValueError):
            calculate_dtw_cct(0.5, min_cct=4000, max_cct=4000)

        with pytest.raises(ValueError):
            calculate_dtw_cct(0.5, min_cct=5000, max_cct=4000)


class TestApplyCurve:
    """Test curve application functions"""

    def test_apply_curve_linear_identity(self):
        """Linear curve should return input unchanged"""
        assert _apply_curve(0.0, DTWCurve.LINEAR) == 0.0
        assert _apply_curve(0.5, DTWCurve.LINEAR) == 0.5
        assert _apply_curve(1.0, DTWCurve.LINEAR) == 1.0

    def test_apply_curve_log_boundaries(self):
        """Log curve should return 0 at 0 and 1 at 1"""
        assert _apply_curve(0.0, DTWCurve.LOG) == pytest.approx(0.0, abs=0.01)
        assert _apply_curve(1.0, DTWCurve.LOG) == pytest.approx(1.0, abs=0.001)

    def test_apply_curve_square_boundaries(self):
        """Square curve should return 0 at 0 and 1 at 1"""
        assert _apply_curve(0.0, DTWCurve.SQUARE) == 0.0
        assert _apply_curve(1.0, DTWCurve.SQUARE) == 1.0
        assert _apply_curve(0.5, DTWCurve.SQUARE) == 0.25

    def test_apply_curve_incandescent_boundaries(self):
        """Incandescent curve should return 0 at 0 and 1 at 1"""
        # Note: 0^0.25 is mathematically 0
        assert _apply_curve(0.0, DTWCurve.INCANDESCENT) == 0.0
        assert _apply_curve(1.0, DTWCurve.INCANDESCENT) == 1.0

    def test_apply_curve_monotonic(self):
        """All curves should be monotonically increasing"""
        brightness_levels = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]

        for curve in DTWCurve:
            values = [_apply_curve(b, curve) for b in brightness_levels]
            for i in range(1, len(values)):
                assert values[i] >= values[i-1], f"{curve.value} not monotonic at {brightness_levels[i]}"


class TestDTWConfig:
    """Test DTW configuration"""

    def test_dtw_config_defaults(self):
        """DTWConfig should have sensible defaults"""
        config = DTWConfig()
        assert config.enabled is True
        assert config.min_cct == 1800
        assert config.max_cct == 4000
        assert config.min_brightness == 0.001
        assert config.curve == DTWCurve.LOG
        assert config.override_timeout == 28800

    def test_calculate_dtw_cct_with_config(self):
        """Should use config values for calculation"""
        config = DTWConfig(
            min_cct=2000,
            max_cct=5000,
            curve=DTWCurve.LINEAR
        )
        result = calculate_dtw_cct_with_config(0.5, config)
        expected = 2000 + (5000 - 2000) * 0.5
        assert result == expected

    def test_calculate_dtw_cct_with_config_disabled(self):
        """Disabled config should return max_cct"""
        config = DTWConfig(enabled=False, max_cct=5000)
        result = calculate_dtw_cct_with_config(0.5, config)
        assert result == 5000


class TestValidateDTWConfig:
    """Test DTW configuration validation"""

    def test_validate_valid_config(self):
        """Valid config should return no errors"""
        config = DTWConfig()
        errors = validate_dtw_config(config)
        assert len(errors) == 0

    def test_validate_min_cct_too_low(self):
        """min_cct < 1000 should fail validation"""
        config = DTWConfig(min_cct=500)
        errors = validate_dtw_config(config)
        assert any("min_cct" in e and "1000" in e for e in errors)

    def test_validate_max_cct_too_high(self):
        """max_cct > 10000 should fail validation"""
        config = DTWConfig(max_cct=15000)
        errors = validate_dtw_config(config)
        assert any("max_cct" in e and "10000" in e for e in errors)

    def test_validate_min_cct_greater_than_max(self):
        """min_cct >= max_cct should fail validation"""
        config = DTWConfig(min_cct=5000, max_cct=4000)
        errors = validate_dtw_config(config)
        assert any("less than" in e for e in errors)

    def test_validate_min_brightness_out_of_range(self):
        """min_brightness outside 0-1 should fail validation"""
        config = DTWConfig(min_brightness=-0.1)
        errors = validate_dtw_config(config)
        assert any("min_brightness" in e for e in errors)

        config = DTWConfig(min_brightness=1.5)
        errors = validate_dtw_config(config)
        assert any("min_brightness" in e for e in errors)

    def test_validate_override_timeout_negative(self):
        """Negative override_timeout should fail validation"""
        config = DTWConfig(override_timeout=-1)
        errors = validate_dtw_config(config)
        assert any("override_timeout" in e for e in errors)


class TestGetExampleValues:
    """Test example value generation"""

    def test_get_example_values_returns_list(self):
        """Should return a list of (brightness, cct) tuples"""
        examples = get_example_values()
        assert isinstance(examples, list)
        assert len(examples) > 0
        for b, cct in examples:
            assert isinstance(b, float)
            assert isinstance(cct, int)

    def test_get_example_values_full_brightness_is_max(self):
        """First example (100% brightness) should be at max_cct"""
        examples = get_example_values(min_cct=1800, max_cct=4000)
        # First example should be at 100% brightness
        assert examples[0][0] == 1.0
        assert examples[0][1] == 4000

    def test_get_example_values_respects_curve(self):
        """Different curves should produce different example values"""
        linear_examples = get_example_values(curve=DTWCurve.LINEAR)
        log_examples = get_example_values(curve=DTWCurve.LOG)

        # At 50% brightness, values should differ
        linear_50 = next(cct for b, cct in linear_examples if b == 0.5)
        log_50 = next(cct for b, cct in log_examples if b == 0.5)

        assert linear_50 != log_50


class TestDTWCurveBehavior:
    """Test overall DTW curve behavior"""

    def test_warmer_at_lower_brightness(self):
        """Lower brightness should always produce warmer (lower CCT) temperature"""
        for curve in DTWCurve:
            cct_high = calculate_dtw_cct(0.8, min_cct=1800, max_cct=4000, curve=curve)
            cct_low = calculate_dtw_cct(0.2, min_cct=1800, max_cct=4000, curve=curve)
            assert cct_low < cct_high, f"{curve.value}: lower brightness should be warmer"

    def test_cct_range_respected(self):
        """CCT should always stay within min_cct and max_cct"""
        for curve in DTWCurve:
            for brightness in [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0]:
                cct = calculate_dtw_cct(brightness, min_cct=1800, max_cct=4000, curve=curve)
                assert 1800 <= cct <= 4000, f"{curve.value} at {brightness}: CCT {cct} out of range"

    def test_linear_curve_smooth_transition(self):
        """Linear curve should have consistent CCT change per brightness step"""
        prev_cct = None
        for brightness in [i / 100 for i in range(101)]:
            cct = calculate_dtw_cct(brightness, min_cct=1800, max_cct=4000, curve=DTWCurve.LINEAR)
            if prev_cct is not None:
                # Linear curve should have ~22K change per 1% (2200K range / 100 steps)
                diff = abs(cct - prev_cct)
                assert diff <= 25, f"linear: jump of {diff}K at brightness {brightness}"
            prev_cct = cct
