"""
DTW Helper Functions - Utilities for dim-to-warm calculations

Provides functions for:
- Fetching DTW system settings from database
- Resolving effective CCT considering overrides, group settings, and DTW calculations
- Managing DTW-related overrides
"""
from typing import Optional, Dict, Any
from dataclasses import dataclass
import structlog
from datetime import datetime, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from tau.models.system_settings import SystemSetting
from tau.models.override import Override, TargetType, OverrideType, OverrideSource
from tau.database import get_session
from tau.logic.dtw import DTWCurve, DTWConfig, calculate_dtw_cct

logger = structlog.get_logger(__name__)


@dataclass
class DTWSettings:
    """All DTW-related system settings."""
    enabled: bool = True
    min_cct: int = 1800
    max_cct: int = 4000
    min_brightness: float = 0.001
    curve: DTWCurve = DTWCurve.LOG
    override_timeout: int = 28800  # seconds


@dataclass
class EffectiveCCTResult:
    """Result of effective CCT resolution."""
    cct: int
    source: str  # 'override', 'dtw_auto', 'group_override', 'group_default', 'fixture_default'


# Default settings cache
_dtw_settings_cache: Optional[DTWSettings] = None
_dtw_settings_cache_time: Optional[float] = None
_DTW_CACHE_DURATION = 5.0  # seconds


async def get_dtw_settings(
    session: Optional[AsyncSession] = None,
    use_cache: bool = True
) -> DTWSettings:
    """
    Get all DTW system settings from the database.

    Args:
        session: Optional database session (creates one if not provided)
        use_cache: Whether to use cached settings (default True)

    Returns:
        DTWSettings dataclass with all DTW configuration
    """
    global _dtw_settings_cache, _dtw_settings_cache_time

    # Check cache first
    import time
    now = time.time()
    if use_cache and _dtw_settings_cache is not None and _dtw_settings_cache_time is not None:
        if now - _dtw_settings_cache_time < _DTW_CACHE_DURATION:
            return _dtw_settings_cache

    settings = DTWSettings()

    async def _fetch_settings(sess: AsyncSession) -> DTWSettings:
        try:
            # Fetch all DTW settings in one query
            result = await sess.execute(
                select(SystemSetting).where(
                    SystemSetting.key.in_([
                        'dtw_enabled',
                        'dtw_min_cct',
                        'dtw_max_cct',
                        'dtw_min_brightness',
                        'dtw_curve',
                        'dtw_override_timeout'
                    ])
                )
            )
            db_settings = result.scalars().all()

            # Map to DTWSettings
            for setting in db_settings:
                if setting.key == 'dtw_enabled':
                    settings.enabled = setting.value.lower() in ('true', '1', 'yes')
                elif setting.key == 'dtw_min_cct':
                    settings.min_cct = int(setting.value)
                elif setting.key == 'dtw_max_cct':
                    settings.max_cct = int(setting.value)
                elif setting.key == 'dtw_min_brightness':
                    settings.min_brightness = float(setting.value)
                elif setting.key == 'dtw_curve':
                    try:
                        settings.curve = DTWCurve(setting.value.lower())
                    except ValueError:
                        settings.curve = DTWCurve.LOG
                elif setting.key == 'dtw_override_timeout':
                    settings.override_timeout = int(setting.value)

            return settings

        except Exception as e:
            logger.error("dtw_settings_fetch_error", error=str(e))
            return settings

    if session is None:
        async for sess in get_session():
            settings = await _fetch_settings(sess)
            break
    else:
        settings = await _fetch_settings(session)

    # Update cache
    _dtw_settings_cache = settings
    _dtw_settings_cache_time = now

    return settings


def clear_dtw_settings_cache():
    """Clear the DTW settings cache."""
    global _dtw_settings_cache, _dtw_settings_cache_time
    _dtw_settings_cache = None
    _dtw_settings_cache_time = None


async def get_active_cct_override(
    target_type: str,
    target_id: int,
    session: Optional[AsyncSession] = None
) -> Optional[Override]:
    """
    Get the active CCT override for a target (fixture or group).

    Args:
        target_type: 'fixture' or 'group'
        target_id: ID of the fixture or group
        session: Optional database session

    Returns:
        Active Override if exists and not expired, None otherwise
    """
    async def _fetch_override(sess: AsyncSession) -> Optional[Override]:
        try:
            now = datetime.now()
            result = await sess.execute(
                select(Override).where(
                    and_(
                        Override.target_type == target_type,
                        Override.target_id == target_id,
                        Override.property == 'cct',
                        Override.expires_at > now
                    )
                ).order_by(Override.created_at.desc()).limit(1)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(
                "override_fetch_error",
                target_type=target_type,
                target_id=target_id,
                error=str(e)
            )
            return None

    if session is None:
        async for sess in get_session():
            return await _fetch_override(sess)
    else:
        return await _fetch_override(session)

    return None


async def create_dtw_override(
    target_type: str,
    target_id: int,
    cct_value: int,
    source: str = 'user',
    timeout_seconds: Optional[int] = None,
    session: Optional[AsyncSession] = None
) -> Optional[Override]:
    """
    Create a CCT override for a fixture or group.

    This is called when a user manually adjusts CCT while DTW is active.

    Args:
        target_type: 'fixture' or 'group'
        target_id: ID of the fixture or group
        cct_value: The manual CCT value in Kelvin
        source: Source of the override ('user', 'api', 'scene', 'schedule')
        timeout_seconds: Override timeout (uses system default if not specified)
        session: Optional database session

    Returns:
        Created Override or None if failed
    """
    async def _create_override(sess: AsyncSession) -> Optional[Override]:
        try:
            # Get timeout from settings if not specified
            nonlocal timeout_seconds
            if timeout_seconds is None:
                settings = await get_dtw_settings(sess)
                timeout_seconds = settings.override_timeout

            now = datetime.now()
            expires_at = now + timedelta(seconds=timeout_seconds)

            # Delete any existing CCT override for this target
            await sess.execute(
                Override.__table__.delete().where(
                    and_(
                        Override.target_type == target_type,
                        Override.target_id == target_id,
                        Override.property == 'cct'
                    )
                )
            )

            # Create new override
            override = Override(
                target_type=target_type,
                target_id=target_id,
                override_type=OverrideType.DTW_CCT.value,
                property='cct',
                value=str(cct_value),
                expires_at=expires_at,
                source=source
            )
            sess.add(override)
            await sess.commit()
            await sess.refresh(override)

            logger.info(
                "dtw_override_created",
                target_type=target_type,
                target_id=target_id,
                cct=cct_value,
                expires_at=expires_at.isoformat()
            )

            return override

        except Exception as e:
            logger.error(
                "override_create_error",
                target_type=target_type,
                target_id=target_id,
                error=str(e)
            )
            await sess.rollback()
            return None

    if session is None:
        async for sess in get_session():
            return await _create_override(sess)
    else:
        return await _create_override(session)

    return None


async def cancel_dtw_override(
    target_type: str,
    target_id: int,
    session: Optional[AsyncSession] = None
) -> int:
    """
    Cancel CCT override(s) for a target.

    Args:
        target_type: 'fixture' or 'group'
        target_id: ID of the fixture or group
        session: Optional database session

    Returns:
        Number of overrides cancelled
    """
    async def _cancel_override(sess: AsyncSession) -> int:
        try:
            from sqlalchemy import delete

            result = await sess.execute(
                delete(Override).where(
                    and_(
                        Override.target_type == target_type,
                        Override.target_id == target_id,
                        Override.property == 'cct'
                    )
                )
            )
            await sess.commit()
            cancelled = result.rowcount

            if cancelled > 0:
                logger.info(
                    "dtw_override_cancelled",
                    target_type=target_type,
                    target_id=target_id,
                    count=cancelled
                )

            return cancelled

        except Exception as e:
            logger.error(
                "override_cancel_error",
                target_type=target_type,
                target_id=target_id,
                error=str(e)
            )
            await sess.rollback()
            return 0

    if session is None:
        async for sess in get_session():
            return await _cancel_override(sess)
    else:
        return await _cancel_override(session)

    return 0


async def cancel_all_overrides_for_target(
    target_type: str,
    target_id: int,
    session: Optional[AsyncSession] = None
) -> int:
    """
    Cancel all overrides for a target (used on power-off).

    Args:
        target_type: 'fixture' or 'group'
        target_id: ID of the fixture or group
        session: Optional database session

    Returns:
        Number of overrides cancelled
    """
    async def _cancel_all(sess: AsyncSession) -> int:
        try:
            from sqlalchemy import delete

            result = await sess.execute(
                delete(Override).where(
                    and_(
                        Override.target_type == target_type,
                        Override.target_id == target_id
                    )
                )
            )
            await sess.commit()
            cancelled = result.rowcount

            if cancelled > 0:
                logger.info(
                    "all_overrides_cancelled",
                    target_type=target_type,
                    target_id=target_id,
                    count=cancelled
                )

            return cancelled

        except Exception as e:
            logger.error(
                "override_cancel_all_error",
                target_type=target_type,
                target_id=target_id,
                error=str(e)
            )
            await sess.rollback()
            return 0

    if session is None:
        async for sess in get_session():
            return await _cancel_all(sess)
    else:
        return await _cancel_all(session)

    return 0


async def cleanup_expired_overrides(
    session: Optional[AsyncSession] = None
) -> int:
    """
    Delete all expired overrides from the database.

    Should be called periodically (e.g., every 60 seconds).

    Args:
        session: Optional database session

    Returns:
        Number of overrides deleted
    """
    async def _cleanup(sess: AsyncSession) -> int:
        try:
            from sqlalchemy import delete

            now = datetime.now()
            result = await sess.execute(
                delete(Override).where(Override.expires_at <= now)
            )
            await sess.commit()
            deleted = result.rowcount

            if deleted > 0:
                logger.info("expired_overrides_cleaned", count=deleted)

            return deleted

        except Exception as e:
            logger.error("override_cleanup_error", error=str(e))
            await sess.rollback()
            return 0

    if session is None:
        async for sess in get_session():
            return await _cleanup(sess)
    else:
        return await _cleanup(session)

    return 0


def calculate_effective_cct_sync(
    brightness: float,
    fixture_dtw_ignore: bool = False,
    fixture_dtw_min_cct: Optional[int] = None,
    fixture_dtw_max_cct: Optional[int] = None,
    fixture_default_cct: Optional[int] = None,
    group_dtw_ignore: bool = False,
    group_dtw_min_cct: Optional[int] = None,
    group_dtw_max_cct: Optional[int] = None,
    group_cct: Optional[int] = None,
    override_cct: Optional[int] = None,
    dtw_settings: Optional[DTWSettings] = None
) -> EffectiveCCTResult:
    """
    Calculate effective CCT synchronously using pre-fetched data.

    This is the core resolution algorithm used by the control loop.
    Order of precedence (highest to lowest):
    1. Active CCT override
    2. DTW automatic calculation (if enabled and not ignored)
    3. Group CCT (if fixture is in a group with CCT set)
    4. Fixture default CCT

    Args:
        brightness: Current brightness (0.0 to 1.0)
        fixture_dtw_ignore: Whether fixture ignores DTW
        fixture_dtw_min_cct: Fixture's DTW min CCT override
        fixture_dtw_max_cct: Fixture's DTW max CCT override
        fixture_default_cct: Fixture's default CCT
        group_dtw_ignore: Whether group ignores DTW
        group_dtw_min_cct: Group's DTW min CCT override
        group_dtw_max_cct: Group's DTW max CCT override
        group_cct: Group's current CCT setting
        override_cct: Active CCT override value
        dtw_settings: DTW system settings

    Returns:
        EffectiveCCTResult with calculated CCT and source
    """
    # Default settings if not provided
    if dtw_settings is None:
        dtw_settings = DTWSettings()

    # 1. Check for active CCT override
    if override_cct is not None:
        return EffectiveCCTResult(cct=override_cct, source='override')

    # 2. Check if fixture ignores DTW
    if fixture_dtw_ignore:
        default_cct = fixture_default_cct or dtw_settings.max_cct
        return EffectiveCCTResult(cct=default_cct, source='fixture_default')

    # 3. Check if group ignores DTW (for fixtures in groups)
    if group_dtw_ignore:
        group_default = group_cct or fixture_default_cct or dtw_settings.max_cct
        return EffectiveCCTResult(cct=group_default, source='group_default')

    # 4. Apply DTW if enabled
    if dtw_settings.enabled:
        # Determine effective DTW range (fixture -> group -> system)
        min_cct = (
            fixture_dtw_min_cct or
            group_dtw_min_cct or
            dtw_settings.min_cct
        )
        max_cct = (
            fixture_dtw_max_cct or
            group_dtw_max_cct or
            dtw_settings.max_cct
        )

        cct = calculate_dtw_cct(
            brightness=brightness,
            min_cct=min_cct,
            max_cct=max_cct,
            min_brightness=dtw_settings.min_brightness,
            curve=dtw_settings.curve
        )

        return EffectiveCCTResult(cct=cct, source='dtw_auto')

    # 5. Fall back to fixture default
    default_cct = fixture_default_cct or dtw_settings.max_cct
    return EffectiveCCTResult(cct=default_cct, source='fixture_default')
