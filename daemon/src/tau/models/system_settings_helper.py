"""
System Settings Helper - Utilities for accessing system settings
"""
from typing import Optional
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tau.models.system_settings import SystemSetting
from tau.database import get_session

logger = structlog.get_logger(__name__)


async def get_system_setting(
    key: str,
    default_value: Optional[str] = None,
    session: Optional[AsyncSession] = None
) -> Optional[str]:
    """
    Get a system setting value by key

    Args:
        key: The setting key to retrieve
        default_value: Value to return if setting not found
        session: Optional database session (creates one if not provided)

    Returns:
        The setting value as a string, or default_value if not found
    """
    close_session = False
    if session is None:
        close_session = True
        async for sess in get_session():
            session = sess
            break

    try:
        result = await session.execute(
            select(SystemSetting).where(SystemSetting.key == key)
        )
        setting = result.scalar_one_or_none()

        if setting is None:
            logger.warning(
                "system_setting_not_found",
                key=key,
                using_default=default_value
            )
            return default_value

        return setting.value

    except Exception as e:
        logger.error(
            "system_setting_fetch_error",
            key=key,
            error=str(e),
            using_default=default_value
        )
        return default_value

    finally:
        if close_session and session:
            await session.close()


async def get_system_setting_typed(
    key: str,
    value_type: str = "str",
    default_value = None,
    session: Optional[AsyncSession] = None
):
    """
    Get a system setting value by key and convert to the appropriate type

    Args:
        key: The setting key to retrieve
        value_type: Expected type ('int', 'float', 'bool', 'str')
        default_value: Value to return if setting not found
        session: Optional database session (creates one if not provided)

    Returns:
        The setting value converted to the appropriate type, or default_value if not found
    """
    close_session = False
    if session is None:
        close_session = True
        async for sess in get_session():
            session = sess
            break

    try:
        result = await session.execute(
            select(SystemSetting).where(SystemSetting.key == key)
        )
        setting = result.scalar_one_or_none()

        if setting is None:
            logger.warning(
                "system_setting_not_found",
                key=key,
                using_default=default_value
            )
            return default_value

        # Convert to the appropriate type
        try:
            return setting.get_typed_value()
        except (ValueError, TypeError) as e:
            logger.error(
                "system_setting_conversion_error",
                key=key,
                value=setting.value,
                target_type=value_type,
                error=str(e),
                using_default=default_value
            )
            return default_value

    except Exception as e:
        logger.error(
            "system_setting_fetch_error",
            key=key,
            error=str(e),
            using_default=default_value
        )
        return default_value

    finally:
        if close_session and session:
            await session.close()


async def set_system_setting(
    key: str,
    value: str,
    session: Optional[AsyncSession] = None
) -> bool:
    """
    Set a system setting value

    Args:
        key: The setting key to update
        value: The new value (as string)
        session: Optional database session (creates one if not provided)

    Returns:
        True if successful, False otherwise
    """
    close_session = False
    if session is None:
        close_session = True
        async for sess in get_session():
            session = sess
            break

    try:
        result = await session.execute(
            select(SystemSetting).where(SystemSetting.key == key)
        )
        setting = result.scalar_one_or_none()

        if setting is None:
            logger.error(
                "system_setting_update_failed",
                key=key,
                reason="Setting not found"
            )
            return False

        setting.value = value
        await session.commit()

        logger.info(
            "system_setting_updated",
            key=key,
            new_value=value
        )
        return True

    except Exception as e:
        logger.error(
            "system_setting_update_error",
            key=key,
            error=str(e)
        )
        if session:
            await session.rollback()
        return False

    finally:
        if close_session and session:
            await session.close()
