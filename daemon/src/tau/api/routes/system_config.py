"""
System Configuration API Routes - Hardware detection and system settings
"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import structlog

from tau.api import get_daemon_instance
from tau.database import get_db_session
from tau.models.system_settings_helper import (
    get_system_setting_typed,
    set_system_setting
)
from tau.models.system_settings import SystemSetting
from sqlalchemy import select

logger = structlog.get_logger(__name__)

router = APIRouter()


class HardwareAvailabilityResponse(BaseModel):
    """Hardware detection results"""
    labjack_available: bool = Field(..., description="LabJack hardware detected")
    labjack_details: Optional[str] = Field(None, description="LabJack device info if found")
    ola_available: bool = Field(..., description="OLA daemon detected")
    ola_details: Optional[str] = Field(None, description="OLA daemon info if found")


def _detect_labjack_hardware() -> tuple[bool, Optional[str]]:
    """
    Attempt to detect LabJack hardware without disrupting current operations.
    Returns (available, details)
    """
    try:
        import u3
        # Try to enumerate devices without opening
        # LabJack provides listAll for discovery
        try:
            device = u3.U3()
            config = device.configU3()
            serial = config.get('SerialNumber', 'Unknown')
            model = 'U3-HV' if config.get('VersionInfo', 0) & 18 else 'U3-LV'
            device.close()
            return True, f"{model} (S/N: {serial})"
        except Exception as e:
            # Device might be in use by daemon - check if daemon has real hardware
            daemon = get_daemon_instance()
            if daemon and daemon.hardware_manager:
                labjack = daemon.hardware_manager.labjack
                if hasattr(labjack, 'is_mock') and not labjack.is_mock():
                    stats = labjack.get_statistics()
                    model = stats.get('model', 'U3')
                    serial = stats.get('serial_number', 'Unknown')
                    return True, f"{model} (S/N: {serial}) - in use"
            return False, None
    except ImportError:
        return False, None
    except Exception as e:
        logger.debug("labjack_detection_error", error=str(e))
        return False, None


def _detect_ola_daemon() -> tuple[bool, Optional[str]]:
    """
    Attempt to detect OLA daemon.
    Returns (available, details)
    """
    try:
        import subprocess
        # Check if olad is running
        result = subprocess.run(
            ["ola_dev_info"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            # Parse output to count devices
            lines = result.stdout.strip().split('\n')
            device_count = len([l for l in lines if l.strip() and not l.startswith('Device')])
            return True, f"OLA daemon running ({device_count} devices)"
        return False, None
    except FileNotFoundError:
        # ola_dev_info not installed
        return False, None
    except subprocess.TimeoutExpired:
        return False, None
    except Exception as e:
        logger.debug("ola_detection_error", error=str(e))
        return False, None


@router.get(
    "/hardware-availability",
    response_model=HardwareAvailabilityResponse,
    summary="Check Hardware Availability",
    description="Detect available hardware interfaces (LabJack, DMX/OLA)"
)
async def check_hardware_availability():
    """Check what hardware is physically available"""
    labjack_available, labjack_details = _detect_labjack_hardware()
    ola_available, ola_details = _detect_ola_daemon()

    return HardwareAvailabilityResponse(
        labjack_available=labjack_available,
        labjack_details=labjack_details,
        ola_available=ola_available,
        ola_details=ola_details
    )


# System Settings Models and Endpoints

class SystemSettingResponse(BaseModel):
    """System setting response"""
    id: int = Field(..., description="Setting ID")
    key: str = Field(..., description="Setting key")
    value: str = Field(..., description="Setting value (as string)")
    description: Optional[str] = Field(None, description="Human-readable description")
    value_type: str = Field(..., description="Value type (int, float, bool, str)")

    class Config:
        from_attributes = True


class SystemSettingUpdateRequest(BaseModel):
    """System setting update request"""
    value: str = Field(..., description="New value (as string)")


@router.get(
    "/settings",
    response_model=List[SystemSettingResponse],
    summary="Get All System Settings",
    description="Retrieve all global system settings"
)
async def get_all_system_settings():
    """Get all system settings"""
    async with get_db_session() as session:
        try:
            result = await session.execute(select(SystemSetting))
            settings = result.scalars().all()
            return [SystemSettingResponse.model_validate(s) for s in settings]
        except Exception as e:
            logger.error("get_system_settings_error", error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to fetch system settings: {str(e)}")


@router.get(
    "/settings/{key}",
    response_model=SystemSettingResponse,
    summary="Get System Setting by Key",
    description="Retrieve a specific system setting by its key"
)
async def get_system_setting_by_key(key: str):
    """Get a specific system setting by key"""
    async with get_db_session() as session:
        try:
            result = await session.execute(
                select(SystemSetting).where(SystemSetting.key == key)
            )
            setting = result.scalar_one_or_none()

            if setting is None:
                raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")

            return SystemSettingResponse.model_validate(setting)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("get_system_setting_error", key=key, error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to fetch setting: {str(e)}")


@router.put(
    "/settings/{key}",
    response_model=SystemSettingResponse,
    summary="Update System Setting",
    description="Update a system setting value"
)
async def update_system_setting(key: str, update: SystemSettingUpdateRequest):
    """Update a system setting"""
    async with get_db_session() as session:
        try:
            # Get the setting first to validate it exists
            result = await session.execute(
                select(SystemSetting).where(SystemSetting.key == key)
            )
            setting = result.scalar_one_or_none()

            if setting is None:
                raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")

            # Validate the new value can be converted to the expected type
            try:
                if setting.value_type == "int":
                    int(update.value)
                elif setting.value_type == "float":
                    float(update.value)
                elif setting.value_type == "bool":
                    if update.value.lower() not in ("true", "false", "1", "0", "yes", "no"):
                        raise ValueError("Boolean value must be true/false, 1/0, or yes/no")
            except ValueError as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid value for type {setting.value_type}: {str(e)}"
                )

            # Update the setting
            old_value = setting.value
            setting.value = update.value
            await session.commit()
            await session.refresh(setting)

            logger.info(
                "system_setting_updated_via_api",
                key=key,
                old_value=old_value,
                new_value=update.value
            )

            # Hot-reload specific settings that need runtime updates
            if key == "dim_speed_ms":
                daemon = get_daemon_instance()
                if daemon and daemon.lighting_controller:
                    daemon.lighting_controller.set_dim_speed_ms(int(update.value))
                    logger.info("dim_speed_hot_reloaded", new_value=update.value)

            return SystemSettingResponse.model_validate(setting)

        except HTTPException:
            raise
        except Exception as e:
            await session.rollback()
            logger.error("update_system_setting_error", key=key, error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to update setting: {str(e)}")
