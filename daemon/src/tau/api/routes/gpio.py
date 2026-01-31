"""
GPIO API Routes - Platform detection and GPIO pin layout for Raspberry Pi

Provides endpoints for:
- Platform detection (is this a Pi? which model?)
- GPIO pin layout for the interactive pin selector UI
- GPIO pin availability based on configured switches
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from tau.database import get_session
from tau.models.switches import Switch
from tau.hardware.platform import (
    detect_platform,
    get_gpio_layout,
    find_nearest_ground,
    bcm_to_physical,
    AVAILABLE_GPIO_PINS,
)

router = APIRouter()
logger = structlog.get_logger(__name__)


# Response models
class PlatformResponse(BaseModel):
    """Platform detection response"""
    is_raspberry_pi: bool = Field(..., description="Whether running on a Raspberry Pi")
    pi_model: Optional[str] = Field(None, description="Pi model name (e.g., 'Raspberry Pi 5 Model B')")
    gpio_available: bool = Field(..., description="Whether GPIO is available for switch input")
    reason: Optional[str] = Field(None, description="Reason why GPIO is unavailable (if applicable)")
    gpio_pins: Optional[dict] = Field(None, description="GPIO pin status (available, in_use, disabled)")


class HeaderPinResponse(BaseModel):
    """Single GPIO header pin"""
    physical: int = Field(..., description="Physical pin number (1-40)")
    type: str = Field(..., description="Pin type: gpio, power, ground, disabled")
    label: str = Field(..., description="Pin label for display")
    bcm: Optional[int] = Field(None, description="BCM GPIO number (for GPIO pins)")
    disabled_reason: Optional[str] = Field(None, description="Reason pin is disabled")
    in_use: bool = Field(default=False, description="Whether pin is already assigned to a switch")
    switch_id: Optional[int] = Field(None, description="ID of switch using this pin")
    switch_name: Optional[str] = Field(None, description="Name of switch using this pin")


class GPIOLayoutResponse(BaseModel):
    """GPIO header layout response"""
    header_pins: List[HeaderPinResponse] = Field(..., description="All 40 header pins")
    ground_pins: List[int] = Field(..., description="Physical pin numbers of ground pins")
    available_bcm_pins: List[int] = Field(..., description="BCM pins available for GPIO input")


class NearestGroundResponse(BaseModel):
    """Response for nearest ground pin lookup"""
    selected_physical_pin: int = Field(..., description="The physical pin that was selected")
    nearest_ground_physical: int = Field(..., description="Physical pin number of nearest ground")
    wiring_instruction: str = Field(..., description="Wiring instruction for the user")


@router.get("/platform", response_model=PlatformResponse)
async def get_platform_info(
    session: AsyncSession = Depends(get_session)
):
    """
    Get platform detection information.

    Returns whether this system is a Raspberry Pi, which model,
    and whether GPIO is available for switch input.
    """
    platform = detect_platform()

    # If not a Pi or GPIO not available, return early
    if not platform.gpio_available:
        return PlatformResponse(
            is_raspberry_pi=platform.is_raspberry_pi,
            pi_model=platform.model,
            gpio_available=False,
            reason=platform.reason,
            gpio_pins=None
        )

    # Get GPIO pins that are currently in use by switches (select only needed columns)
    result = await session.execute(
        select(Switch.gpio_bcm_pin).where(
            Switch.input_source == 'gpio',
            Switch.gpio_bcm_pin.isnot(None)
        )
    )
    in_use_pins = [row[0] for row in result.all()]

    # Build disabled pins list (pins with special functions)
    disabled_pins = [pin for pin in range(28) if pin not in AVAILABLE_GPIO_PINS]

    return PlatformResponse(
        is_raspberry_pi=True,
        pi_model=platform.model,
        gpio_available=True,
        reason=None,
        gpio_pins={
            "available": [pin for pin in AVAILABLE_GPIO_PINS if pin not in in_use_pins],
            "in_use": in_use_pins,
            "disabled": disabled_pins
        }
    )


@router.get("/layout", response_model=GPIOLayoutResponse)
async def get_gpio_pin_layout(
    session: AsyncSession = Depends(get_session)
):
    """
    Get the GPIO header pin layout for the UI pin selector.

    Returns all 40 pins of the GPIO header with their status:
    - type: gpio (selectable), power, ground, disabled (special function)
    - in_use: whether the pin is already assigned to a switch
    """
    # Get base layout
    layout = get_gpio_layout()

    # Get GPIO pins currently in use by switches (select only needed columns)
    result = await session.execute(
        select(Switch.gpio_bcm_pin, Switch.id, Switch.name).where(
            Switch.input_source == 'gpio',
            Switch.gpio_bcm_pin.isnot(None)
        )
    )
    gpio_switches = result.all()

    # Build BCM -> switch mapping
    bcm_to_switch = {
        row[0]: {"id": row[1], "name": row[2]}
        for row in gpio_switches
    }

    # Enhance header pins with in_use status
    enhanced_pins = []
    for pin in layout["header_pins"]:
        enhanced = HeaderPinResponse(
            physical=pin["physical"],
            type=pin["type"],
            label=pin["label"],
            bcm=pin.get("bcm"),
            disabled_reason=pin.get("disabled_reason"),
            in_use=False,
            switch_id=None,
            switch_name=None
        )

        # Check if this GPIO pin is in use
        if pin.get("bcm") is not None and pin["bcm"] in bcm_to_switch:
            switch_info = bcm_to_switch[pin["bcm"]]
            enhanced.in_use = True
            enhanced.switch_id = switch_info["id"]
            enhanced.switch_name = switch_info["name"]

        enhanced_pins.append(enhanced)

    return GPIOLayoutResponse(
        header_pins=enhanced_pins,
        ground_pins=layout["ground_pins"],
        available_bcm_pins=layout["available_bcm_pins"]
    )


@router.get("/nearest-ground/{bcm_pin}", response_model=NearestGroundResponse)
async def get_nearest_ground_pin(bcm_pin: int):
    """
    Get the nearest ground pin to a selected GPIO pin.

    Helps users know where to connect the other wire of their switch.
    """
    if bcm_pin not in AVAILABLE_GPIO_PINS:
        raise HTTPException(
            status_code=400,
            detail=f"BCM pin {bcm_pin} is not an available GPIO pin"
        )

    # Convert BCM to physical
    physical_pin = bcm_to_physical(bcm_pin)
    if physical_pin is None:
        raise HTTPException(
            status_code=400,
            detail=f"BCM pin {bcm_pin} not found in header layout"
        )

    # Find nearest ground
    nearest_ground = find_nearest_ground(physical_pin)

    return NearestGroundResponse(
        selected_physical_pin=physical_pin,
        nearest_ground_physical=nearest_ground,
        wiring_instruction=f"Connect switch between Pin {physical_pin} (GPIO{bcm_pin}) and Pin {nearest_ground} (GND)"
    )


@router.get("/validate/{bcm_pin}")
async def validate_gpio_pin(
    bcm_pin: int,
    session: AsyncSession = Depends(get_session)
):
    """
    Validate a GPIO pin selection.

    Checks if the pin is available, not disabled, and not already in use.
    """
    # Check if pin is in available list
    if bcm_pin not in AVAILABLE_GPIO_PINS:
        return {
            "valid": False,
            "reason": f"GPIO{bcm_pin} is not available for switch input (reserved for special function)"
        }

    # Check if already in use
    result = await session.execute(
        select(Switch).where(
            Switch.input_source == 'gpio',
            Switch.gpio_bcm_pin == bcm_pin
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        switch_name = existing.name or f"Switch #{existing.id}"
        return {
            "valid": False,
            "reason": f"GPIO{bcm_pin} is already used by '{switch_name}'"
        }

    return {
        "valid": True,
        "physical_pin": bcm_to_physical(bcm_pin),
        "nearest_ground": find_nearest_ground(bcm_to_physical(bcm_pin))
    }
