"""
DTW Engine - Real-time dim-to-warm calculation engine for control loop

This module provides a high-performance DTW engine for use in the 30 Hz
control loop. It caches DTW settings and provides synchronous CCT calculation
to minimize database access during real-time operation.
"""
from typing import Optional, Dict, Any
from dataclasses import dataclass
import structlog
import time

from tau.logic.dtw import DTWCurve, calculate_dtw_cct
from tau.models.dtw_helper import (
    DTWSettings,
    get_dtw_settings,
    calculate_effective_cct_sync,
    EffectiveCCTResult,
)

logger = structlog.get_logger(__name__)


@dataclass
class FixtureDTWConfig:
    """Per-fixture DTW configuration loaded from database."""
    fixture_id: int
    dtw_ignore: bool = False
    dtw_min_cct_override: Optional[int] = None
    dtw_max_cct_override: Optional[int] = None
    default_cct: Optional[int] = None
    # Group info (primary group, if any)
    group_id: Optional[int] = None
    group_dtw_ignore: bool = False
    group_dtw_min_cct_override: Optional[int] = None
    group_dtw_max_cct_override: Optional[int] = None
    group_cct: Optional[int] = None


class DTWEngine:
    """
    Real-time DTW calculation engine.

    Maintains cached DTW settings and provides fast synchronous CCT
    calculation for use in the control loop. Settings are refreshed
    periodically to reflect database changes.
    """

    def __init__(self, refresh_interval: float = 10.0):
        """
        Initialize DTW engine.

        Args:
            refresh_interval: Seconds between settings refresh (default 10s)
        """
        self._settings: Optional[DTWSettings] = None
        self._last_refresh: float = 0.0
        self._refresh_interval = refresh_interval
        self._fixture_configs: Dict[int, FixtureDTWConfig] = {}
        self._override_cache: Dict[str, Optional[int]] = {}  # "fixture:123" -> cct or None
        self._override_cache_time: float = 0.0
        self._override_cache_duration: float = 1.0  # Refresh override cache every second

        # Statistics
        self._calculations = 0
        self._cache_hits = 0

        logger.info("dtw_engine_initialized")

    @property
    def settings(self) -> DTWSettings:
        """Get current DTW settings (may be default if not yet loaded)."""
        if self._settings is None:
            return DTWSettings()
        return self._settings

    @property
    def is_enabled(self) -> bool:
        """Check if DTW is globally enabled."""
        return self.settings.enabled

    async def initialize(self) -> bool:
        """
        Initialize engine by loading settings from database.

        Returns:
            True if initialization successful
        """
        try:
            self._settings = await get_dtw_settings(use_cache=False)
            self._last_refresh = time.time()
            logger.info(
                "dtw_engine_settings_loaded",
                enabled=self._settings.enabled,
                curve=self._settings.curve.value,
                min_cct=self._settings.min_cct,
                max_cct=self._settings.max_cct
            )
            return True
        except Exception as e:
            logger.error("dtw_engine_init_error", error=str(e))
            self._settings = DTWSettings()  # Use defaults
            return False

    async def refresh_settings(self, force: bool = False) -> bool:
        """
        Refresh settings from database if interval has elapsed.

        Args:
            force: Force refresh regardless of interval

        Returns:
            True if settings were refreshed
        """
        now = time.time()
        if not force and now - self._last_refresh < self._refresh_interval:
            return False

        try:
            self._settings = await get_dtw_settings(use_cache=False)
            self._last_refresh = now
            logger.debug("dtw_engine_settings_refreshed")
            return True
        except Exception as e:
            logger.error("dtw_engine_refresh_error", error=str(e))
            return False

    def register_fixture(
        self,
        fixture_id: int,
        dtw_ignore: bool = False,
        dtw_min_cct_override: Optional[int] = None,
        dtw_max_cct_override: Optional[int] = None,
        default_cct: Optional[int] = None,
        group_id: Optional[int] = None,
        group_dtw_ignore: bool = False,
        group_dtw_min_cct_override: Optional[int] = None,
        group_dtw_max_cct_override: Optional[int] = None,
        group_cct: Optional[int] = None
    ) -> None:
        """
        Register or update fixture DTW configuration.

        Called during initialization or when fixture config changes.
        """
        self._fixture_configs[fixture_id] = FixtureDTWConfig(
            fixture_id=fixture_id,
            dtw_ignore=dtw_ignore,
            dtw_min_cct_override=dtw_min_cct_override,
            dtw_max_cct_override=dtw_max_cct_override,
            default_cct=default_cct,
            group_id=group_id,
            group_dtw_ignore=group_dtw_ignore,
            group_dtw_min_cct_override=group_dtw_min_cct_override,
            group_dtw_max_cct_override=group_dtw_max_cct_override,
            group_cct=group_cct
        )

    def unregister_fixture(self, fixture_id: int) -> None:
        """Remove fixture from DTW engine."""
        self._fixture_configs.pop(fixture_id, None)

    def set_override(self, target_type: str, target_id: int, cct: Optional[int]) -> None:
        """
        Set or clear an override in the local cache.

        Called when overrides are created/deleted via API.
        """
        cache_key = f"{target_type}:{target_id}"
        self._override_cache[cache_key] = cct

    def clear_override(self, target_type: str, target_id: int) -> None:
        """Clear an override from the local cache."""
        cache_key = f"{target_type}:{target_id}"
        self._override_cache.pop(cache_key, None)

    def calculate_cct(
        self,
        fixture_id: int,
        brightness: float,
        override_cct: Optional[int] = None
    ) -> EffectiveCCTResult:
        """
        Calculate effective CCT for a fixture at given brightness.

        This is the main entry point for the control loop. It uses
        cached settings and fixture config for fast synchronous calculation.

        Args:
            fixture_id: Fixture ID
            brightness: Current brightness (0.0 to 1.0)
            override_cct: Optional override CCT (from cache)

        Returns:
            EffectiveCCTResult with calculated CCT and source
        """
        self._calculations += 1

        # Get fixture config (or use defaults)
        config = self._fixture_configs.get(fixture_id)

        if config is None:
            # Fixture not registered - use system defaults
            if self.is_enabled:
                cct = calculate_dtw_cct(
                    brightness=brightness,
                    min_cct=self.settings.min_cct,
                    max_cct=self.settings.max_cct,
                    min_brightness=self.settings.min_brightness,
                    curve=self.settings.curve
                )
                return EffectiveCCTResult(cct=cct, source='dtw_auto')
            else:
                return EffectiveCCTResult(cct=self.settings.max_cct, source='fixture_default')

        # Check override cache first
        if override_cct is None:
            cache_key = f"fixture:{fixture_id}"
            if cache_key in self._override_cache:
                override_cct = self._override_cache[cache_key]
                self._cache_hits += 1

        # Use the synchronous calculation function
        return calculate_effective_cct_sync(
            brightness=brightness,
            fixture_dtw_ignore=config.dtw_ignore,
            fixture_dtw_min_cct=config.dtw_min_cct_override,
            fixture_dtw_max_cct=config.dtw_max_cct_override,
            fixture_default_cct=config.default_cct,
            group_dtw_ignore=config.group_dtw_ignore,
            group_dtw_min_cct=config.group_dtw_min_cct_override,
            group_dtw_max_cct=config.group_dtw_max_cct_override,
            group_cct=config.group_cct,
            override_cct=override_cct,
            dtw_settings=self.settings
        )

    def calculate_cct_simple(self, brightness: float) -> int:
        """
        Calculate DTW CCT using only system settings.

        Simplified version for cases where fixture config isn't available.

        Args:
            brightness: Brightness value (0.0 to 1.0)

        Returns:
            Calculated CCT in Kelvin
        """
        if not self.is_enabled:
            return self.settings.max_cct

        return calculate_dtw_cct(
            brightness=brightness,
            min_cct=self.settings.min_cct,
            max_cct=self.settings.max_cct,
            min_brightness=self.settings.min_brightness,
            curve=self.settings.curve
        )

    def get_statistics(self) -> dict:
        """Get engine statistics."""
        return {
            "enabled": self.is_enabled,
            "curve": self.settings.curve.value if self._settings else "unknown",
            "min_cct": self.settings.min_cct,
            "max_cct": self.settings.max_cct,
            "registered_fixtures": len(self._fixture_configs),
            "calculations": self._calculations,
            "cache_hits": self._cache_hits,
            "last_refresh": self._last_refresh,
        }
