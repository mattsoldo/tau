"""
System Configuration API Routes - Hardware detection
"""
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field
import structlog

from tau.api import get_daemon_instance

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
