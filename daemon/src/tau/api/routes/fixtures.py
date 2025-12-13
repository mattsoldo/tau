"""
Fixtures API Routes - CRUD operations for fixtures and fixture models
"""
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tau.database import get_session
from tau.models.fixtures import Fixture, FixtureModel
from tau.models.state import FixtureState
from tau.api.schemas import (
    FixtureModelCreate,
    FixtureModelResponse,
    FixtureCreate,
    FixtureUpdate,
    FixtureResponse,
    FixtureStateResponse,
)

router = APIRouter()


# Fixture Models Endpoints
@router.get("/models", response_model=List[FixtureModelResponse])
async def list_fixture_models(
    session: AsyncSession = Depends(get_session)
):
    """List all fixture models"""
    result = await session.execute(select(FixtureModel))
    models = result.scalars().all()
    return models


@router.post("/models", response_model=FixtureModelResponse, status_code=201)
async def create_fixture_model(
    model_data: FixtureModelCreate,
    session: AsyncSession = Depends(get_session)
):
    """Create a new fixture model"""
    model = FixtureModel(**model_data.model_dump())
    session.add(model)
    await session.commit()
    await session.refresh(model)
    return model


@router.get("/models/{model_id}", response_model=FixtureModelResponse)
async def get_fixture_model(
    model_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Get a specific fixture model"""
    model = await session.get(FixtureModel, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Fixture model not found")
    return model


@router.delete("/models/{model_id}", status_code=204)
async def delete_fixture_model(
    model_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Delete a fixture model"""
    model = await session.get(FixtureModel, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Fixture model not found")

    await session.delete(model)
    await session.commit()


# Fixtures Endpoints
@router.get("/", response_model=List[FixtureResponse])
async def list_fixtures(
    session: AsyncSession = Depends(get_session)
):
    """List all fixtures"""
    result = await session.execute(select(Fixture))
    fixtures = result.scalars().all()
    return fixtures


@router.post("/", response_model=FixtureResponse, status_code=201)
async def create_fixture(
    fixture_data: FixtureCreate,
    session: AsyncSession = Depends(get_session)
):
    """Create a new fixture"""
    # Verify fixture model exists
    model = await session.get(FixtureModel, fixture_data.fixture_model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Fixture model not found")

    # Check if DMX channel is already in use
    result = await session.execute(
        select(Fixture).where(Fixture.dmx_channel_start == fixture_data.dmx_channel_start)
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"DMX channel {fixture_data.dmx_channel_start} already in use"
        )

    fixture = Fixture(**fixture_data.model_dump())
    session.add(fixture)
    await session.commit()
    await session.refresh(fixture)

    # Create initial state
    state = FixtureState(
        fixture_id=fixture.id,
        current_brightness=0,
        current_cct=2700,
        is_on=False
    )
    session.add(state)
    await session.commit()

    return fixture


@router.get("/{fixture_id}", response_model=FixtureResponse)
async def get_fixture(
    fixture_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Get a specific fixture"""
    fixture = await session.get(Fixture, fixture_id)
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")
    return fixture


@router.patch("/{fixture_id}", response_model=FixtureResponse)
async def update_fixture(
    fixture_id: int,
    fixture_data: FixtureUpdate,
    session: AsyncSession = Depends(get_session)
):
    """Update a fixture"""
    fixture = await session.get(Fixture, fixture_id)
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")

    # Update fields
    update_data = fixture_data.model_dump(exclude_unset=True)

    # Check if DMX channel is being changed and is available
    if "dmx_channel_start" in update_data:
        result = await session.execute(
            select(Fixture).where(
                Fixture.dmx_channel_start == update_data["dmx_channel_start"],
                Fixture.id != fixture_id
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"DMX channel {update_data['dmx_channel_start']} already in use"
            )

    for field, value in update_data.items():
        setattr(fixture, field, value)

    await session.commit()
    await session.refresh(fixture)
    return fixture


@router.delete("/{fixture_id}", status_code=204)
async def delete_fixture(
    fixture_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Delete a fixture"""
    fixture = await session.get(Fixture, fixture_id)
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")

    await session.delete(fixture)
    await session.commit()


@router.get("/{fixture_id}/state", response_model=FixtureStateResponse)
async def get_fixture_state(
    fixture_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Get fixture current state"""
    state = await session.get(FixtureState, fixture_id)
    if not state:
        raise HTTPException(status_code=404, detail="Fixture state not found")
    return state
