"""
Circadian Rhythm Engine

Calculates lighting parameters (brightness, color temperature) based on
time of day to support natural circadian rhythms. Uses profiles with
keyframes that define lighting at specific times.
"""
from datetime import datetime, time
from typing import Dict, List, Optional, Tuple
import structlog

from tau.database import get_db_session
from tau.models import CircadianProfile

logger = structlog.get_logger(__name__)


class CircadianKeyframe:
    """A single keyframe in a circadian profile"""

    def __init__(self, time_of_day: time, brightness: float, cct: int):
        """
        Initialize keyframe

        Args:
            time_of_day: Time this keyframe occurs
            brightness: Brightness value (0.0 to 1.0)
            cct: Color temperature in Kelvin (2000-6500)
        """
        self.time_of_day = time_of_day
        self.brightness = brightness
        self.cct = cct

    @property
    def seconds_since_midnight(self) -> int:
        """Get seconds since midnight for this keyframe"""
        return (
            self.time_of_day.hour * 3600
            + self.time_of_day.minute * 60
            + self.time_of_day.second
        )

    def __repr__(self) -> str:
        return f"<Keyframe({self.time_of_day}, {self.brightness:.2f}, {self.cct}K)>"


class CircadianEngine:
    """
    Circadian rhythm calculation engine

    Manages circadian profiles and calculates appropriate lighting
    parameters based on current time of day. Supports smooth transitions
    between keyframes using linear interpolation.
    """

    def __init__(self):
        """Initialize circadian engine"""
        # Cache of loaded profiles {profile_id: List[CircadianKeyframe]}
        self.profiles: Dict[int, List[CircadianKeyframe]] = {}

        # Statistics
        self.calculations = 0
        self.profile_loads = 0
        self.cache_hits = 0

        logger.info("circadian_engine_initialized")

    async def load_profile(self, profile_id: int) -> bool:
        """
        Load a circadian profile from database

        Args:
            profile_id: ID of profile to load

        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            async with get_db_session() as session:
                profile = await session.get(CircadianProfile, profile_id)

                if not profile:
                    logger.warning("profile_not_found", profile_id=profile_id)
                    return False

                # Parse keyframes from JSONB data
                # Note: Database model uses 'curve_points' field
                keyframes = []
                for kf_data in profile.curve_points:
                    # curve_points is a list of dicts like:
                    # {"time": "06:00:00", "brightness": 0.3, "cct": 2700}
                    time_str = kf_data["time"]
                    brightness = float(kf_data["brightness"])
                    cct = int(kf_data["cct"])

                    # Parse time
                    time_obj = datetime.strptime(time_str, "%H:%M:%S").time()

                    keyframes.append(CircadianKeyframe(time_obj, brightness, cct))

                # Sort keyframes by time
                keyframes.sort(key=lambda kf: kf.seconds_since_midnight)

                # Cache profile
                self.profiles[profile_id] = keyframes
                self.profile_loads += 1

                logger.info(
                    "profile_loaded",
                    profile_id=profile_id,
                    profile_name=profile.name,
                    keyframe_count=len(keyframes),
                )

                return True

        except Exception as e:
            logger.error(
                "profile_load_failed",
                profile_id=profile_id,
                error=str(e),
                exc_info=True,
            )
            return False

    def calculate(
        self, profile_id: int, current_time: Optional[datetime] = None
    ) -> Optional[Tuple[float, int]]:
        """
        Calculate circadian values for current time

        Args:
            profile_id: ID of circadian profile to use
            current_time: Time to calculate for (defaults to now)

        Returns:
            Tuple of (brightness, cct) or None if profile not loaded
        """
        # Check if profile is loaded
        if profile_id not in self.profiles:
            logger.warning(
                "profile_not_loaded",
                profile_id=profile_id,
                message="Call load_profile() first",
            )
            return None

        keyframes = self.profiles[profile_id]
        if not keyframes:
            logger.warning("profile_empty", profile_id=profile_id)
            return None

        # Get current time
        if current_time is None:
            current_time = datetime.now()

        current_seconds = (
            current_time.hour * 3600
            + current_time.minute * 60
            + current_time.second
        )

        self.calculations += 1
        self.cache_hits += 1

        # Find the two keyframes to interpolate between
        prev_kf, next_kf = self._find_surrounding_keyframes(keyframes, current_seconds)

        # Interpolate between keyframes
        brightness, cct = self._interpolate(prev_kf, next_kf, current_seconds)

        logger.debug(
            "circadian_calculated",
            profile_id=profile_id,
            time=current_time.strftime("%H:%M:%S"),
            brightness=brightness,
            cct=cct,
        )

        return (brightness, cct)

    def _find_surrounding_keyframes(
        self, keyframes: List[CircadianKeyframe], current_seconds: int
    ) -> Tuple[CircadianKeyframe, CircadianKeyframe]:
        """
        Find the keyframes before and after current time

        Args:
            keyframes: Sorted list of keyframes
            current_seconds: Current time in seconds since midnight

        Returns:
            Tuple of (previous_keyframe, next_keyframe)
        """
        # Handle wrap-around (midnight crossing)
        # If current time is before first keyframe or after last keyframe,
        # we need to wrap around

        if current_seconds < keyframes[0].seconds_since_midnight:
            # Before first keyframe - interpolate from last to first
            return (keyframes[-1], keyframes[0])

        if current_seconds >= keyframes[-1].seconds_since_midnight:
            # After last keyframe - interpolate from last to first (next day)
            return (keyframes[-1], keyframes[0])

        # Find the keyframes that bracket current time
        for i in range(len(keyframes) - 1):
            if keyframes[i].seconds_since_midnight <= current_seconds < keyframes[
                i + 1
            ].seconds_since_midnight:
                return (keyframes[i], keyframes[i + 1])

        # Fallback (should never reach here)
        return (keyframes[0], keyframes[0])

    def _interpolate(
        self,
        prev_kf: CircadianKeyframe,
        next_kf: CircadianKeyframe,
        current_seconds: int,
    ) -> Tuple[float, int]:
        """
        Interpolate between two keyframes

        Args:
            prev_kf: Previous keyframe
            next_kf: Next keyframe
            current_seconds: Current time in seconds since midnight

        Returns:
            Tuple of (brightness, cct)
        """
        prev_seconds = prev_kf.seconds_since_midnight
        next_seconds = next_kf.seconds_since_midnight

        # Handle midnight wrap-around
        if next_seconds < prev_seconds:
            # Next keyframe is after midnight
            next_seconds += 86400  # Add 24 hours

            if current_seconds < prev_seconds:
                # Current time is also after midnight
                current_seconds += 86400

        # Calculate interpolation factor (0.0 to 1.0)
        if next_seconds == prev_seconds:
            # Same time (shouldn't happen, but handle it)
            factor = 0.0
        else:
            factor = (current_seconds - prev_seconds) / (next_seconds - prev_seconds)

        # Clamp factor to [0, 1]
        factor = max(0.0, min(1.0, factor))

        # Linear interpolation
        brightness = prev_kf.brightness + factor * (next_kf.brightness - prev_kf.brightness)
        cct = int(prev_kf.cct + factor * (next_kf.cct - prev_kf.cct))

        return (brightness, cct)

    def get_statistics(self) -> dict:
        """
        Get engine statistics

        Returns:
            Dictionary with statistics
        """
        return {
            "profiles_loaded": len(self.profiles),
            "calculations": self.calculations,
            "profile_loads": self.profile_loads,
            "cache_hits": self.cache_hits,
        }

    def clear_cache(self) -> None:
        """Clear profile cache"""
        count = len(self.profiles)
        self.profiles.clear()
        logger.info("profile_cache_cleared", profiles_cleared=count)
