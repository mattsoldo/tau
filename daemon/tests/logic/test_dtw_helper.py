"""
Tests for DTW helper functions
"""
import pytest
from tau.logic.dtw import DTWCurve
from tau.models.dtw_helper import (
    DTWSettings,
    EffectiveCCTResult,
    calculate_effective_cct_sync,
    clear_dtw_settings_cache,
)


class TestDTWSettings:
    """Test DTW settings dataclass"""

    def test_default_settings(self):
        """Default DTWSettings should have sensible values"""
        settings = DTWSettings()
        assert settings.enabled is True
        assert settings.min_cct == 1800
        assert settings.max_cct == 4000
        assert settings.min_brightness == 0.001
        assert settings.curve == DTWCurve.LOG
        assert settings.override_timeout == 28800


class TestCalculateEffectiveCCTSync:
    """Test synchronous effective CCT calculation"""

    def test_override_takes_priority(self):
        """Active override should be used regardless of other settings"""
        result = calculate_effective_cct_sync(
            brightness=0.5,
            override_cct=3500,
            dtw_settings=DTWSettings()
        )
        assert result.cct == 3500
        assert result.source == 'override'

    def test_fixture_dtw_ignore_uses_default(self):
        """Fixture with dtw_ignore should use default CCT"""
        result = calculate_effective_cct_sync(
            brightness=0.5,
            fixture_dtw_ignore=True,
            fixture_default_cct=3000,
            dtw_settings=DTWSettings()
        )
        assert result.cct == 3000
        assert result.source == 'fixture_default'

    def test_group_dtw_ignore_uses_group_default(self):
        """Group with dtw_ignore should use group CCT"""
        result = calculate_effective_cct_sync(
            brightness=0.5,
            group_dtw_ignore=True,
            group_cct=3200,
            dtw_settings=DTWSettings()
        )
        assert result.cct == 3200
        assert result.source == 'group_default'

    def test_dtw_enabled_uses_calculation(self):
        """When DTW enabled, should calculate CCT from brightness"""
        settings = DTWSettings(enabled=True, min_cct=1800, max_cct=4000, curve=DTWCurve.LINEAR)
        result = calculate_effective_cct_sync(
            brightness=0.5,
            dtw_settings=settings
        )
        # Linear curve at 50% should be midpoint
        expected = 1800 + (4000 - 1800) * 0.5
        assert result.cct == expected
        assert result.source == 'dtw_auto'

    def test_dtw_disabled_uses_fixture_default(self):
        """When DTW disabled, should use fixture default CCT"""
        settings = DTWSettings(enabled=False, max_cct=4000)
        result = calculate_effective_cct_sync(
            brightness=0.5,
            fixture_default_cct=3000,
            dtw_settings=settings
        )
        assert result.cct == 3000
        assert result.source == 'fixture_default'

    def test_fixture_cct_override_used(self):
        """Fixture-level CCT range override should be used"""
        settings = DTWSettings(enabled=True, min_cct=1800, max_cct=4000, curve=DTWCurve.LINEAR)
        result = calculate_effective_cct_sync(
            brightness=0.5,
            fixture_dtw_min_cct=2000,
            fixture_dtw_max_cct=3500,
            dtw_settings=settings
        )
        # Should use fixture's range, not system default
        expected = 2000 + (3500 - 2000) * 0.5
        assert result.cct == expected

    def test_group_cct_override_used_as_fallback(self):
        """Group-level CCT range should be used if fixture doesn't have override"""
        settings = DTWSettings(enabled=True, min_cct=1800, max_cct=4000, curve=DTWCurve.LINEAR)
        result = calculate_effective_cct_sync(
            brightness=0.5,
            group_dtw_min_cct=2200,
            group_dtw_max_cct=3800,
            dtw_settings=settings
        )
        # Should use group's range
        expected = 2200 + (3800 - 2200) * 0.5
        assert result.cct == expected

    def test_priority_order_fixture_over_group(self):
        """Fixture override should take priority over group override"""
        settings = DTWSettings(enabled=True, min_cct=1800, max_cct=4000, curve=DTWCurve.LINEAR)
        result = calculate_effective_cct_sync(
            brightness=0.5,
            fixture_dtw_min_cct=2000,  # Fixture override
            fixture_dtw_max_cct=3500,
            group_dtw_min_cct=2500,   # Group override (should be ignored)
            group_dtw_max_cct=4500,
            dtw_settings=settings
        )
        # Should use fixture's range, not group's
        expected = 2000 + (3500 - 2000) * 0.5
        assert result.cct == expected

    def test_zero_brightness_returns_min_cct(self):
        """Zero brightness should return minimum CCT"""
        settings = DTWSettings(enabled=True, min_cct=1800, max_cct=4000)
        result = calculate_effective_cct_sync(
            brightness=0.0,
            dtw_settings=settings
        )
        assert result.cct == 1800
        assert result.source == 'dtw_auto'

    def test_full_brightness_returns_max_cct(self):
        """Full brightness should return maximum CCT"""
        settings = DTWSettings(enabled=True, min_cct=1800, max_cct=4000)
        result = calculate_effective_cct_sync(
            brightness=1.0,
            dtw_settings=settings
        )
        assert result.cct == 4000
        assert result.source == 'dtw_auto'


class TestCacheManagement:
    """Test DTW settings cache"""

    def test_clear_cache(self):
        """Cache clear should not raise errors"""
        # Just verify it doesn't raise
        clear_dtw_settings_cache()


class TestEffectiveCCTResult:
    """Test EffectiveCCTResult dataclass"""

    def test_result_fields(self):
        """Result should have cct and source fields"""
        result = EffectiveCCTResult(cct=3500, source='override')
        assert result.cct == 3500
        assert result.source == 'override'
