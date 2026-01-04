"""
Switches API Routes - CRUD operations for switches and switch models
"""
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tau.database import get_session
from tau.models.switches import Switch, SwitchModel
from tau.models.groups import Group
from tau.models.fixtures import Fixture
from tau.api.schemas import (
    SwitchModelCreate,
    SwitchModelUpdate,
    SwitchModelResponse,
    SwitchCreate,
    SwitchUpdate,
    SwitchResponse,
)

router = APIRouter()


# ============================================================================
# Switch Models Endpoints
# ============================================================================

@router.get("/models", response_model=List[SwitchModelResponse])
async def list_switch_models(
    session: AsyncSession = Depends(get_session)
):
    """List all switch models"""
    result = await session.execute(select(SwitchModel))
    models = result.scalars().all()
    return models


@router.post("/models", response_model=SwitchModelResponse, status_code=201)
async def create_switch_model(
    model_data: SwitchModelCreate,
    session: AsyncSession = Depends(get_session)
):
    """Create a new switch model"""
    # Check for duplicate manufacturer/model combo
    result = await session.execute(
        select(SwitchModel).where(
            SwitchModel.manufacturer == model_data.manufacturer,
            SwitchModel.model == model_data.model
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Switch model '{model_data.manufacturer} {model_data.model}' already exists"
        )

    model = SwitchModel(**model_data.model_dump())
    session.add(model)
    await session.commit()
    await session.refresh(model)
    return model


@router.get("/models/{model_id}", response_model=SwitchModelResponse)
async def get_switch_model(
    model_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Get a specific switch model"""
    model = await session.get(SwitchModel, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Switch model not found")
    return model


@router.patch("/models/{model_id}", response_model=SwitchModelResponse)
async def update_switch_model(
    model_id: int,
    model_data: SwitchModelUpdate,
    session: AsyncSession = Depends(get_session)
):
    """Update a switch model"""
    model = await session.get(SwitchModel, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Switch model not found")

    # Update fields
    update_data = model_data.model_dump(exclude_unset=True)

    # Check for duplicate if manufacturer or model is being changed
    if "manufacturer" in update_data or "model" in update_data:
        new_manufacturer = update_data.get("manufacturer", model.manufacturer)
        new_model = update_data.get("model", model.model)
        result = await session.execute(
            select(SwitchModel).where(
                SwitchModel.manufacturer == new_manufacturer,
                SwitchModel.model == new_model,
                SwitchModel.id != model_id
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Switch model '{new_manufacturer} {new_model}' already exists"
            )

    for field, value in update_data.items():
        setattr(model, field, value)

    await session.commit()
    await session.refresh(model)
    return model


@router.delete("/models/{model_id}", status_code=204)
async def delete_switch_model(
    model_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Delete a switch model (only if no switches are using it)"""
    model = await session.get(SwitchModel, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Switch model not found")

    # Check if any switches are using this model
    result = await session.execute(
        select(Switch).where(Switch.switch_model_id == model_id)
    )
    switches = result.scalars().all()
    if switches:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete switch model: {len(switches)} switch(es) are using it"
        )

    await session.delete(model)
    await session.commit()


# ============================================================================
# Switches Endpoints
# ============================================================================

@router.get("/", response_model=List[SwitchResponse])
async def list_switches(
    session: AsyncSession = Depends(get_session)
):
    """List all switches"""
    result = await session.execute(select(Switch))
    switches = result.scalars().all()
    return switches


@router.post("/", response_model=SwitchResponse, status_code=201)
async def create_switch(
    switch_data: SwitchCreate,
    session: AsyncSession = Depends(get_session)
):
    """Create a new switch"""
    # Verify switch model exists
    model = await session.get(SwitchModel, switch_data.switch_model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Switch model not found")

    # Validate target: must have exactly one target (group OR fixture)
    if switch_data.target_group_id is None and switch_data.target_fixture_id is None:
        raise HTTPException(
            status_code=400,
            detail="Switch must target either a group or a fixture"
        )
    if switch_data.target_group_id is not None and switch_data.target_fixture_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Switch cannot target both a group and a fixture"
        )

    # Verify target exists
    if switch_data.target_group_id is not None:
        group = await session.get(Group, switch_data.target_group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Target group not found")
    if switch_data.target_fixture_id is not None:
        fixture = await session.get(Fixture, switch_data.target_fixture_id)
        if not fixture:
            raise HTTPException(status_code=404, detail="Target fixture not found")

    # Validate pins based on model requirements
    if model.requires_digital_pin and switch_data.labjack_digital_pin is None:
        raise HTTPException(
            status_code=400,
            detail=f"Switch model '{model.manufacturer} {model.model}' requires a digital pin"
        )
    if model.requires_analog_pin and switch_data.labjack_analog_pin is None:
        raise HTTPException(
            status_code=400,
            detail=f"Switch model '{model.manufacturer} {model.model}' requires an analog pin"
        )

    # Check for pin conflicts
    if switch_data.labjack_digital_pin is not None:
        result = await session.execute(
            select(Switch).where(Switch.labjack_digital_pin == switch_data.labjack_digital_pin)
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Digital pin {switch_data.labjack_digital_pin} already in use"
            )
    if switch_data.labjack_analog_pin is not None:
        result = await session.execute(
            select(Switch).where(Switch.labjack_analog_pin == switch_data.labjack_analog_pin)
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Analog pin {switch_data.labjack_analog_pin} already in use"
            )

    switch = Switch(**switch_data.model_dump())
    session.add(switch)
    await session.commit()
    await session.refresh(switch)
    return switch


@router.get("/{switch_id}", response_model=SwitchResponse)
async def get_switch(
    switch_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Get a specific switch"""
    switch = await session.get(Switch, switch_id)
    if not switch:
        raise HTTPException(status_code=404, detail="Switch not found")
    return switch


@router.patch("/{switch_id}", response_model=SwitchResponse)
async def update_switch(
    switch_id: int,
    switch_data: SwitchUpdate,
    session: AsyncSession = Depends(get_session)
):
    """Update a switch"""
    switch = await session.get(Switch, switch_id)
    if not switch:
        raise HTTPException(status_code=404, detail="Switch not found")

    update_data = switch_data.model_dump(exclude_unset=True)

    # Verify switch model if being changed
    if "switch_model_id" in update_data:
        model = await session.get(SwitchModel, update_data["switch_model_id"])
        if not model:
            raise HTTPException(status_code=404, detail="Switch model not found")
    else:
        model = await session.get(SwitchModel, switch.switch_model_id)

    # Validate target if either is being updated
    new_group_id = update_data.get("target_group_id", switch.target_group_id)
    new_fixture_id = update_data.get("target_fixture_id", switch.target_fixture_id)

    # Handle explicit None values
    if "target_group_id" in update_data and update_data["target_group_id"] is None:
        new_group_id = None
    if "target_fixture_id" in update_data and update_data["target_fixture_id"] is None:
        new_fixture_id = None

    if new_group_id is None and new_fixture_id is None:
        raise HTTPException(
            status_code=400,
            detail="Switch must target either a group or a fixture"
        )
    if new_group_id is not None and new_fixture_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Switch cannot target both a group and a fixture"
        )

    # Verify target exists
    if new_group_id is not None:
        group = await session.get(Group, new_group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Target group not found")
    if new_fixture_id is not None:
        fixture = await session.get(Fixture, new_fixture_id)
        if not fixture:
            raise HTTPException(status_code=404, detail="Target fixture not found")

    # Validate pins based on model requirements
    new_digital = update_data.get("labjack_digital_pin", switch.labjack_digital_pin)
    new_analog = update_data.get("labjack_analog_pin", switch.labjack_analog_pin)

    if model.requires_digital_pin and new_digital is None:
        raise HTTPException(
            status_code=400,
            detail=f"Switch model '{model.manufacturer} {model.model}' requires a digital pin"
        )
    if model.requires_analog_pin and new_analog is None:
        raise HTTPException(
            status_code=400,
            detail=f"Switch model '{model.manufacturer} {model.model}' requires an analog pin"
        )

    # Check for pin conflicts (excluding current switch)
    if "labjack_digital_pin" in update_data and update_data["labjack_digital_pin"] is not None:
        result = await session.execute(
            select(Switch).where(
                Switch.labjack_digital_pin == update_data["labjack_digital_pin"],
                Switch.id != switch_id
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Digital pin {update_data['labjack_digital_pin']} already in use"
            )
    if "labjack_analog_pin" in update_data and update_data["labjack_analog_pin"] is not None:
        result = await session.execute(
            select(Switch).where(
                Switch.labjack_analog_pin == update_data["labjack_analog_pin"],
                Switch.id != switch_id
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Analog pin {update_data['labjack_analog_pin']} already in use"
            )

    for field, value in update_data.items():
        setattr(switch, field, value)

    await session.commit()
    await session.refresh(switch)
    return switch


@router.delete("/{switch_id}", status_code=204)
async def delete_switch(
    switch_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Delete a switch"""
    switch = await session.get(Switch, switch_id)
    if not switch:
        raise HTTPException(status_code=404, detail="Switch not found")

    await session.delete(switch)
    await session.commit()

    return {"status": "deleted"}


# ============================================================================
# Switch Discovery Endpoints
# ============================================================================

@router.get("/discovery/stats")
async def get_discovery_stats():
    """Get switch auto-discovery statistics"""
    from tau.api import get_daemon_instance
    daemon = get_daemon_instance()
    
    if not daemon or not daemon.switch_discovery:
        return {
            "enabled": False,
            "message": "Switch discovery not initialized"
        }
    
    stats = daemon.switch_discovery.get_statistics()
    stats["enabled"] = True
    return stats


@router.post("/discovery/dismiss")
async def dismiss_discovery(
    pin: int,
    is_digital: bool = True
):
    """
    Dismiss a switch discovery notification
    
    Args:
        pin: Pin number that was detected
        is_digital: True for digital pin, False for analog pin
    """
    from tau.api import get_daemon_instance
    daemon = get_daemon_instance()
    
    if not daemon or not daemon.switch_discovery:
        raise HTTPException(
            status_code=503,
            detail="Switch discovery not available"
        )
    
    daemon.switch_discovery.clear_detection(pin, is_digital)
    
    return {
        "status": "dismissed",
        "pin": pin,
        "is_digital": is_digital
    }


@router.post("/discovery/reload")
async def reload_configured_switches():
    """
    Reload the list of configured switches
    
    Call this after adding a new switch to update the discovery service
    """
    from tau.api import get_daemon_instance
    daemon = get_daemon_instance()
    
    if not daemon or not daemon.switch_discovery:
        raise HTTPException(
            status_code=503,
            detail="Switch discovery not available"
        )
    
    await daemon.switch_discovery.load_configured_switches()
    
    return {
        "status": "reloaded",
        "configured_digital_pins": len(daemon.switch_discovery.configured_digital_pins),
        "configured_analog_pins": len(daemon.switch_discovery.configured_analog_pins)
    }
