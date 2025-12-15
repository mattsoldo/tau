"""
LabJack API Routes - Hardware monitoring and control endpoints
"""
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends
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


class SimulateInputRequest(BaseModel):
    """Request to simulate an input (mock mode only)"""
    channel: int = Field(..., ge=0, le=15, description="Channel number (0-15)")
    voltage: float = Field(..., ge=-10.0, le=10.0, description="Voltage to simulate")


class ChannelConfigRequest(BaseModel):
    """Channel configuration request"""
    channel: int = Field(..., ge=0, le=15)
    mode: str = Field(..., pattern="^(analog|digital-in|digital-out)$")
    pull_resistor: Optional[str] = Field(None, pattern="^(none|pull-up|pull-down)$")


class LabJackStatusResponse(BaseModel):
    """LabJack status and statistics"""
    connected: bool
    model: str
    mock_mode: bool
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

    # Get the actual LabJack instance to check if it's mock
    labjack = daemon.hardware_manager.labjack
    is_mock = labjack.is_mock() if hasattr(labjack, 'is_mock') else True

    # Get model from stats or default
    model = labjack_stats.get("model", "U3-LV")
    if model == "Unknown" or not model:
        model = "U3-LV"

    return LabJackStatusResponse(
        connected=labjack_stats.get("connected", False),
        model=model,
        mock_mode=is_mock,
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
    "/simulate",
    summary="Simulate Input (Mock Mode)",
    description="Simulate an analog input value (only works in mock mode)"
)
async def simulate_input(request: SimulateInputRequest):
    """Simulate an input value (mock mode only)"""
    daemon = get_daemon_instance()

    if not daemon or not daemon.hardware_manager:
        raise HTTPException(status_code=503, detail="Hardware manager not available")

    try:
        # Get the LabJack interface
        labjack = daemon.hardware_manager.labjack

        # Check if it's a mock instance
        if not hasattr(labjack, 'simulate_analog_input'):
            raise HTTPException(status_code=400, detail="Simulation only available in mock mode")

        # Simulate the input
        labjack.simulate_analog_input(request.channel, request.voltage)

        logger.info(
            "labjack_input_simulated",
            channel=request.channel,
            voltage=request.voltage
        )

        return {
            "status": "success",
            "channel": request.channel,
            "voltage": request.voltage
        }

    except Exception as e:
        logger.error("labjack_simulate_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error simulating input: {str(e)}")


class SimulateDigitalRequest(BaseModel):
    """Request to toggle/simulate a digital input (mock mode only)"""
    channel: int = Field(..., ge=0, le=15, description="Channel number (0-15)")
    state: Optional[bool] = Field(None, description="Specific state to set (None = toggle)")


@router.post(
    "/simulate-digital",
    summary="Simulate/Toggle Digital Input (Mock Mode)",
    description="Toggle or set a digital input state (only works in mock mode)"
)
async def simulate_digital_input(request: SimulateDigitalRequest):
    """Toggle or set a digital input state (mock mode only)"""
    daemon = get_daemon_instance()

    if not daemon or not daemon.hardware_manager:
        raise HTTPException(status_code=503, detail="Hardware manager not available")

    try:
        labjack = daemon.hardware_manager.labjack

        # Check if it's a mock instance
        if not labjack.is_mock():
            raise HTTPException(status_code=400, detail="Digital simulation only available in mock mode")

        # Get current state and toggle, or set specific state
        current_state = labjack.digital_inputs.get(request.channel, False)
        new_state = not current_state if request.state is None else request.state

        # Set the new state
        labjack.digital_inputs[request.channel] = new_state

        logger.info(
            "labjack_digital_simulated",
            channel=request.channel,
            state=new_state
        )

        return {
            "status": "success",
            "channel": request.channel,
            "state": new_state
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("labjack_simulate_digital_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error simulating digital input: {str(e)}")


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

        # In mock mode, reset all simulated inputs
        if hasattr(labjack, 'analog_inputs'):
            for i in range(16):
                labjack.analog_inputs[i] = 0.0

        logger.info("labjack_reset")

        return {"status": "success", "message": "All channels reset to defaults"}

    except Exception as e:
        logger.error("labjack_reset_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Error resetting LabJack: {str(e)}")