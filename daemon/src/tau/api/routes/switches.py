"""
Switches API Routes - CRUD operations for switches and switch models
"""
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.orm import selectinload
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
    SwitchWithModelResponse,
)

router = APIRouter()


# Switch Models Endpoints
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
    """Delete a switch model"""
    model = await session.get(SwitchModel, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Switch model not found")

    # Check if any switches are using this model
    result = await session.execute(
        select(Switch).where(Switch.switch_model_id == model_id)
    )
    if result.scalars().first():
        raise HTTPException(
            status_code=409,
            detail="Cannot delete switch model: it is being used by one or more switches"
        )

    await session.delete(model)
    await session.commit()


# Switches Endpoints
@router.get("/", response_model=List[SwitchWithModelResponse])
async def list_switches(
    session: AsyncSession = Depends(get_session)
):
    """List all switches with their models"""
    result = await session.execute(
        select(Switch).options(selectinload(Switch.switch_model))
    )
    switches = result.scalars().all()

    # Map model relationship to expected response format
    response = []
    for switch in switches:
        switch_dict = {
            "id": switch.id,
            "name": switch.name,
            "switch_model_id": switch.switch_model_id,
            "labjack_digital_pin": switch.labjack_digital_pin,
            "labjack_analog_pin": switch.labjack_analog_pin,
            "target_group_id": switch.target_group_id,
            "target_fixture_id": switch.target_fixture_id,
            "model": switch.switch_model,
        }
        response.append(switch_dict)

    return response


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

    # Validate target assignment (must have exactly one target)
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

    # Validate pin assignments based on model requirements
    if model.requires_digital_pin and switch_data.labjack_digital_pin is None:
        raise HTTPException(
            status_code=400,
            detail="This switch model requires a digital pin assignment"
        )
    if model.requires_analog_pin and switch_data.labjack_analog_pin is None:
        raise HTTPException(
            status_code=400,
            detail="This switch model requires an analog pin assignment"
        )

    switch = Switch(**switch_data.model_dump())
    session.add(switch)
    await session.commit()
    await session.refresh(switch)
    return switch


@router.get("/{switch_id}", response_model=SwitchWithModelResponse)
async def get_switch(
    switch_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Get a specific switch with its model"""
    result = await session.execute(
        select(Switch)
        .options(selectinload(Switch.switch_model))
        .where(Switch.id == switch_id)
    )
    switch = result.scalar_one_or_none()
    if not switch:
        raise HTTPException(status_code=404, detail="Switch not found")

    return {
        "id": switch.id,
        "name": switch.name,
        "switch_model_id": switch.switch_model_id,
        "labjack_digital_pin": switch.labjack_digital_pin,
        "labjack_analog_pin": switch.labjack_analog_pin,
        "target_group_id": switch.target_group_id,
        "target_fixture_id": switch.target_fixture_id,
        "model": switch.switch_model,
    }


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

    # If updating switch_model_id, verify it exists
    if "switch_model_id" in update_data:
        model = await session.get(SwitchModel, update_data["switch_model_id"])
        if not model:
            raise HTTPException(status_code=404, detail="Switch model not found")

    # Calculate what the final target assignment will be
    final_group_id = update_data.get("target_group_id", switch.target_group_id)
    final_fixture_id = update_data.get("target_fixture_id", switch.target_fixture_id)

    # Handle explicit None assignments - check if key was provided
    if "target_group_id" in update_data and update_data["target_group_id"] is None:
        final_group_id = None
    if "target_fixture_id" in update_data and update_data["target_fixture_id"] is None:
        final_fixture_id = None

    # Validate target assignment (must have exactly one target)
    if final_group_id is None and final_fixture_id is None:
        raise HTTPException(
            status_code=400,
            detail="Switch must target either a group or a fixture"
        )
    if final_group_id is not None and final_fixture_id is not None:
        raise HTTPException(
            status_code=400,
            detail="Switch cannot target both a group and a fixture"
        )

    # Verify target exists if changed
    if "target_group_id" in update_data and update_data["target_group_id"] is not None:
        group = await session.get(Group, update_data["target_group_id"])
        if not group:
            raise HTTPException(status_code=404, detail="Target group not found")

    if "target_fixture_id" in update_data and update_data["target_fixture_id"] is not None:
        fixture = await session.get(Fixture, update_data["target_fixture_id"])
        if not fixture:
            raise HTTPException(status_code=404, detail="Target fixture not found")

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
