"""
System Configuration API Routes - Mock mode settings and hardware detection
"""
import os
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import structlog

from tau.api import get_daemon_instance
from tau.config import get_settings

logger = structlog.get_logger(__name__)

router = APIRouter()


class SystemConfigResponse(BaseModel):
    """Current system configuration"""
    labjack_mock: bool = Field(..., description="Whether LabJack is running in mock mode")
    ola_mock: bool = Field(..., description="Whether OLA/DMX is running in mock mode")
    labjack_hardware_available: bool = Field(..., description="Whether LabJack hardware is detected")
    ola_hardware_available: bool = Field(..., description="Whether OLA daemon is detected")
    config_file_path: Optional[str] = Field(None, description="Path to .env file if found")


class SystemConfigUpdate(BaseModel):
    """Update system configuration"""
    labjack_mock: Optional[bool] = Field(None, description="Set LabJack mock mode")
    ola_mock: Optional[bool] = Field(None, description="Set OLA mock mode")


class HardwareModeSwitch(BaseModel):
    """Switch hardware mode at runtime"""
    labjack_mock: Optional[bool] = Field(None, description="Switch LabJack to mock (True) or real (False)")
    ola_mock: Optional[bool] = Field(None, description="Switch OLA to mock (True) or real (False)")


class HardwareAvailabilityResponse(BaseModel):
    """Hardware detection results"""
    labjack_available: bool = Field(..., description="LabJack hardware detected")
    labjack_details: Optional[str] = Field(None, description="LabJack device info if found")
    ola_available: bool = Field(..., description="OLA daemon detected")
    ola_details: Optional[str] = Field(None, description="OLA daemon info if found")


def _find_env_file() -> Optional[Path]:
    """Find the .env file location"""
    # Start from daemon directory and work up
    current = Path(__file__).resolve()
    for _ in range(10):  # Limit search depth
        current = current.parent
        env_file = current / ".env"
        if env_file.exists():
            return env_file
        if (current / "daemon").exists():  # Found project root
            return current / ".env"
    return None


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
    "/",
    response_model=SystemConfigResponse,
    summary="Get System Configuration",
    description="Get current system configuration including mock mode settings and hardware availability"
)
async def get_system_config():
    """Get current system configuration"""
    settings = get_settings()
    daemon = get_daemon_instance()

    # Get current mock mode settings
    labjack_mock = settings.labjack_mock
    ola_mock = settings.ola_mock

    # If daemon is running, get actual status from hardware manager
    if daemon and daemon.hardware_manager:
        labjack = daemon.hardware_manager.labjack
        ola = daemon.hardware_manager.ola

        labjack_mock = labjack.is_mock() if hasattr(labjack, 'is_mock') else True
        ola_mock = not hasattr(ola, 'is_mock') or ola.is_mock() if hasattr(ola, 'is_mock') else True

    # Detect hardware availability
    labjack_available, _ = _detect_labjack_hardware()
    ola_available, _ = _detect_ola_daemon()

    # Find env file
    env_file = _find_env_file()

    return SystemConfigResponse(
        labjack_mock=labjack_mock,
        ola_mock=ola_mock,
        labjack_hardware_available=labjack_available,
        ola_hardware_available=ola_available,
        config_file_path=str(env_file) if env_file else None
    )


@router.put(
    "/",
    response_model=dict,
    summary="Update System Configuration",
    description="""
Update system configuration. Changes to mock mode settings are written to the .env file
and will take effect after daemon restart.

**Note**: Changing mock mode requires restarting the daemon for changes to take effect.
"""
)
async def update_system_config(config: SystemConfigUpdate):
    """Update system configuration"""
    env_file = _find_env_file()

    if not env_file:
        raise HTTPException(
            status_code=500,
            detail="Could not find .env file. Please create one in the project root."
        )

    # Read current env file
    env_content = {}
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_content[key.strip()] = value.strip()

    # Update values
    changes = {}
    if config.labjack_mock is not None:
        env_content['LABJACK_MOCK'] = str(config.labjack_mock).lower()
        changes['labjack_mock'] = config.labjack_mock

    if config.ola_mock is not None:
        env_content['OLA_MOCK'] = str(config.ola_mock).lower()
        changes['ola_mock'] = config.ola_mock

    # Write back env file
    with open(env_file, 'w') as f:
        for key, value in env_content.items():
            f.write(f"{key}={value}\n")

    logger.info("system_config_updated", changes=changes, env_file=str(env_file))

    return {
        "status": "success",
        "message": "Configuration updated. Restart daemon for changes to take effect.",
        "changes": changes,
        "restart_required": True
    }


@router.get(
    "/hardware-availability",
    response_model=HardwareAvailabilityResponse,
    summary="Check Hardware Availability",
    description="Detect available hardware interfaces (LabJack, DMX/OLA) regardless of mock mode settings"
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


@router.get(
    "/hardware-alert",
    summary="Get Hardware Alert Status",
    description="""
Check if hardware is available but mock mode is enabled.
Returns alert info that can be shown to users.
"""
)
async def get_hardware_alert():
    """Check if user should be alerted about available hardware in mock mode"""
    settings = get_settings()
    daemon = get_daemon_instance()

    # Get current mock mode settings from running daemon
    labjack_mock = settings.labjack_mock
    ola_mock = settings.ola_mock

    if daemon and daemon.hardware_manager:
        labjack = daemon.hardware_manager.labjack
        ola = daemon.hardware_manager.ola
        labjack_mock = labjack.is_mock() if hasattr(labjack, 'is_mock') else True
        ola_mock = not hasattr(ola, 'is_mock') or ola.is_mock() if hasattr(ola, 'is_mock') else True

    # Detect hardware
    labjack_available, labjack_details = _detect_labjack_hardware()
    ola_available, ola_details = _detect_ola_daemon()

    alerts = []

    if labjack_mock and labjack_available:
        alerts.append({
            "type": "labjack",
            "message": f"LabJack hardware detected ({labjack_details}) but running in mock mode",
            "hardware": labjack_details
        })

    if ola_mock and ola_available:
        alerts.append({
            "type": "ola",
            "message": f"DMX interface detected ({ola_details}) but running in mock mode",
            "hardware": ola_details
        })

    return {
        "has_alerts": len(alerts) > 0,
        "alerts": alerts,
        "labjack_mock": labjack_mock,
        "ola_mock": ola_mock
    }


@router.post(
    "/hardware-mode",
    summary="Switch Hardware Mode",
    description="""
Switch between mock and real hardware at runtime without restarting the daemon.

This endpoint allows hot-swapping hardware drivers, useful for:
- Testing with mock hardware, then switching to real hardware
- Disconnecting real hardware temporarily
- Switching individual components (LabJack or OLA) independently

**Note**: This switch happens immediately and does not require daemon restart.
After switching, the discovery service will reload configured switches.
"""
)
async def switch_hardware_mode(mode: HardwareModeSwitch):
    """Switch hardware mode at runtime"""
    daemon = get_daemon_instance()

    if not daemon or not daemon.hardware_manager:
        raise HTTPException(
            status_code=503,
            detail="Daemon not running or hardware manager not available"
        )

    # Validate at least one mode is specified
    if mode.labjack_mock is None and mode.ola_mock is None:
        raise HTTPException(
            status_code=400,
            detail="Must specify at least one mode to switch (labjack_mock or ola_mock)"
        )

    # Attempt the switch
    success = await daemon.hardware_manager.switch_mode(
        labjack_mock=mode.labjack_mock,
        ola_mock=mode.ola_mock
    )

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Hardware mode switch failed. Check daemon logs for details."
        )

    # Reload switch discovery if we switched LabJack mode
    if mode.labjack_mock is not None and daemon.switch_discovery:
        try:
            await daemon.switch_discovery.load_configured_switches()
            logger.info("switch_discovery_reloaded_after_mode_switch")
        except Exception as e:
            logger.warning("switch_discovery_reload_failed", error=str(e))

    # Get new hardware status
    stats = daemon.hardware_manager.get_statistics()
    current_mode = stats.get("mode", {})

    return {
        "status": "success",
        "message": "Hardware mode switched successfully",
        "current_mode": current_mode,
        "restart_required": False
    }
