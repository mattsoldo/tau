"""
LabJack API Routes - Hardware monitoring and control endpoints
"""
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import structlog

from tau.api import get_daemon_instance

logger = structlog.get_logger(__name__)

router = APIRouter()


# Pydantic models for request/response
class AnalogReadRequest(BaseModel):
    """Request to read analog inputs"""
    channels: List[int] = Field(..., description="List of channels to read (0-15)")


class AnalogReadResponse(BaseModel):
    """Analog input reading response"""
    readings: Dict[int, float] = Field(..., description="Channel to voltage mapping")
    timestamp: str
    model: str = "U3-LV"


class PWMSetRequest(BaseModel):
    """Request to set PWM outputs"""
    outputs: Dict[int, float] = Field(..., description="Channel to duty cycle mapping (0.0-1.0)")


class ChannelConfigRequest(BaseModel):
    """Channel configuration request"""
    channel: int = Field(..., ge=0, le=15)
    mode: str = Field(..., pattern="^(analog|digital-in|digital-out)$")
    pull_resistor: Optional[str] = Field(None, pattern="^(none|pull-up|pull-down)$")


class LabJackStatusResponse(BaseModel):
    """LabJack status and statistics"""
    connected: bool
    model: str
    statistics: Dict
    configuration: Dict


@router.get(
    "/status",
    response_model=LabJackStatusResponse,
    summary="Get LabJack Status",
    description="Get current LabJack connection status, model info, and statistics"
)
async def get_labjack_status():
    """Get LabJack status and statistics"""
    daemon = get_daemon_instance()

    if not daemon or not daemon.hardware_manager:
        raise HTTPException(status_code=503, detail="Hardware manager not available")

    labjack = daemon.hardware_manager.labjack

    # Actively read all digital input channels to get live state
    # This ensures the statistics reflect current hardware state
    if labjack.is_connected() and hasattr(labjack, 'channel_modes'):
        for channel, mode in labjack.channel_modes.items():
            if mode == 'digital-in':
                try:
                    await labjack.read_digital_input(channel)
                except Exception as e:
                    logger.debug("digital_read_error", channel=channel, error=str(e))

    hw_stats = daemon.hardware_manager.get_statistics()
    labjack_stats = hw_stats.get("labjack", {})

    # Get model from stats or default
    model = labjack_stats.get("model", "U3-LV")
    if model == "Unknown" or not model:
        model = "U3-LV"

    return LabJackStatusResponse(
        connected=labjack_stats.get("connected", False),
        model=model,
        statistics=labjack_stats,
        configuration={
            "sample_rate": "1Hz",
            "resolution": "16-bit",
            "settling_time_us": 1000,
            "channels_configured": 16
        }
    )


@router.post(
    "/read",
    response_model=AnalogReadResponse,
    summary="Read Analog Inputs",
    description="Read voltage values from specified analog input channels"
)
async def read_analog_inputs(request: AnalogReadRequest):
    """Read analog inputs from LabJack"""
    daemon = get_daemon_instance()

    if not daemon or not daemon.hardware_manager:
        raise HTTPException(status_code=503, detail="Hardware manager not available")

    try:
        # Get the LabJack interface
        labjack = daemon.hardware_manager.labjack

        if not labjack.is_connected():
            raise HTTPException(status_code=503, detail="LabJack not connected")

        # Check channel modes and read appropriately
        readings = {}
        for channel in request.channels:
            # Check if channel is in digital mode
            if hasattr(labjack, 'channel_modes') and labjack.channel_modes.get(channel, 'analog') != 'analog':
                # Read digital input and convert to voltage representation
                digital_state = await labjack.read_digital_input(channel)
                # Represent HIGH as 3.3V, LOW as 0V for display purposes
                readings[channel] = 3.3 if digital_state else 0.0
            else:
                # Read analog voltage
                voltage = await labjack.read_analog_input(channel)
                readings[channel] = voltage

        # Get timestamp
        from datetime import datetime
        timestamp = datetime.now().isoformat()

        # Get model from hardware stats
        hw_stats = daemon.hardware_manager.get_statistics()
        labjack_stats = hw_stats.get("labjack", {})
        model = labjack_stats.get("model", "U3-LV")
        if model == "Unknown" or not model:
            model = "U3-LV"

        return AnalogReadResponse(
            readings=readings,
            timestamp=timestamp,
            model=model
        )

    except Exception as e:
        logger.error("labjack_read_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error reading analog inputs: {str(e)}")


@router.post(
    "/pwm",
    summary="Set PWM Outputs",
    description="Set PWM duty cycles for output channels"
)
async def set_pwm_outputs(request: PWMSetRequest):
    """Set PWM outputs on LabJack"""
    daemon = get_daemon_instance()

    if not daemon or not daemon.hardware_manager:
        raise HTTPException(status_code=503, detail="Hardware manager not available")

    try:
        # Get the LabJack interface
        labjack = daemon.hardware_manager.labjack

        if not labjack.is_connected():
            raise HTTPException(status_code=503, detail="LabJack not connected")

        # Set the PWM outputs
        await labjack.set_pwm_outputs(request.outputs)

        return {"status": "success", "outputs_set": len(request.outputs)}

    except Exception as e:
        logger.error("labjack_pwm_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error setting PWM outputs: {str(e)}")


@router.post(
    "/configure-channel",
    summary="Configure Channel Mode",
    description="Configure a channel as analog input, digital input, or digital output"
)
async def configure_channel(request: ChannelConfigRequest):
    """Configure a channel's mode"""
    daemon = get_daemon_instance()

    if not daemon or not daemon.hardware_manager:
        raise HTTPException(status_code=503, detail="Hardware manager not available")

    try:
        # Get the LabJack interface
        labjack = daemon.hardware_manager.labjack

        if not labjack.is_connected():
            raise HTTPException(status_code=503, detail="LabJack not connected")

        # Configure the channel
        await labjack.configure_channel(request.channel, request.mode)

        logger.info(
            "labjack_channel_configured",
            channel=request.channel,
            mode=request.mode,
            pull_resistor=request.pull_resistor
        )

        return {
            "status": "success",
            "channel": request.channel,
            "mode": request.mode,
            "pull_resistor": request.pull_resistor
        }

    except Exception as e:
        logger.error("labjack_configure_channel_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error configuring channel: {str(e)}")


@router.get(
    "/channels",
    summary="Get All Channel States",
    description="Get current state of all LabJack channels"
)
async def get_all_channels():
    """Get all channel states"""
    daemon = get_daemon_instance()

    if not daemon or not daemon.hardware_manager:
        raise HTTPException(status_code=503, detail="Hardware manager not available")

    hw_stats = daemon.hardware_manager.get_statistics()
    labjack_stats = hw_stats.get("labjack", {})

    # Format channel data
    channels = []
    analog_inputs = labjack_stats.get("analog_inputs", {})
    pwm_outputs = labjack_stats.get("pwm_outputs", {})

    # Add analog input channels
    for i in range(16):
        channel_type = "FIO" if i < 8 else "EIO"
        channel_num = i if i < 8 else i - 8
        channels.append({
            "id": i,
            "name": f"{channel_type}{channel_num}",
            "type": "analog_input",
            "value": analog_inputs.get(str(i), 0.0),
            "unit": "V"
        })

    # Add PWM output channels
    for i in range(2):
        channels.append({
            "id": 16 + i,
            "name": f"PWM{i}",
            "type": "pwm_output",
            "value": pwm_outputs.get(str(i), 0.0) * 100,
            "unit": "%"
        })

    return {
        "channels": channels,
        "connected": labjack_stats.get("connected", False)
    }


@router.get(
    "/diagnose/{channel}",
    summary="Diagnose Channel",
    description="Read the actual voltage on a channel (temporarily reconfigures as analog)"
)
async def diagnose_channel(channel: int):
    """
    Diagnose a channel by reading its actual voltage.

    This temporarily reconfigures the channel as analog to measure voltage,
    then restores its original configuration.

    Useful for debugging switch wiring issues.
    """
    if channel < 0 or channel > 7:
        raise HTTPException(status_code=400, detail="Only FIO channels 0-7 supported for diagnosis")

    daemon = get_daemon_instance()

    if not daemon or not daemon.hardware_manager:
        raise HTTPException(status_code=503, detail="Hardware manager not available")

    labjack = daemon.hardware_manager.labjack

    if not labjack.is_connected():
        raise HTTPException(status_code=503, detail="LabJack not connected")

    try:
        import u3

        # Save current mode
        original_mode = labjack.channel_modes.get(channel, 'analog')

        # Temporarily configure as analog to read voltage
        # Set bit for this channel to 1 (analog)
        current_fio_analog = labjack._fio_analog_mask
        temp_fio_analog = current_fio_analog | (1 << channel)
        labjack.device.configIO(FIOAnalog=temp_fio_analog)

        # Read voltage
        voltage = labjack.device.getAIN(channel)

        # Restore original configuration
        labjack.device.configIO(FIOAnalog=current_fio_analog)

        # If it was digital, reconfigure direction
        if original_mode in ('digital-in', 'digital-out'):
            direction = 1 if original_mode == 'digital-out' else 0
            labjack.device.getFeedback(u3.BitDirWrite(channel, direction))

        # Interpret the voltage
        interpretation = ""
        if voltage < 0.5:
            interpretation = "LOW (connected to GND or switch closed to GND)"
        elif voltage > 2.5:
            interpretation = "HIGH (floating with pull-up or connected to VS)"
        else:
            interpretation = "INTERMEDIATE (possible floating or partial connection)"

        logger.info(
            "channel_diagnosed",
            channel=channel,
            voltage=voltage,
            original_mode=original_mode,
            interpretation=interpretation
        )

        return {
            "channel": channel,
            "voltage": round(voltage, 3),
            "interpretation": interpretation,
            "expected_for_nc_switch": {
                "at_rest": "~0V (LOW) - switch closed, connected to GND",
                "when_pressed": "~3.3V (HIGH) - switch open, pull-up active"
            },
            "wiring_tip": "For NC switch: one terminal to FIO, other terminal to GND"
        }

    except Exception as e:
        logger.error("channel_diagnose_error", channel=channel, error=str(e))
        raise HTTPException(status_code=500, detail=f"Error diagnosing channel: {str(e)}")


@router.post(
    "/reset",
    summary="Reset LabJack",
    description="Reset all LabJack channels to default values"
)
async def reset_labjack():
    """Reset all LabJack channels"""
    daemon = get_daemon_instance()

    if not daemon or not daemon.hardware_manager:
        raise HTTPException(status_code=503, detail="Hardware manager not available")

    try:
        labjack = daemon.hardware_manager.labjack

        # Reset all PWM outputs to 0
        await labjack.set_pwm_outputs({0: 0.0, 1: 0.0})

        logger.info("labjack_reset")

        return {"status": "success", "message": "All channels reset to defaults"}

    except Exception as e:
        logger.error("labjack_reset_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error resetting LabJack: {str(e)}")