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
from tau.models.switches import Switch
from tau.api.schemas import (
    FixtureModelCreate,
    FixtureModelUpdate,
    FixtureModelResponse,
    FixtureCreate,
    FixtureUpdate,
    FixtureResponse,
    FixtureStateResponse,
    FixtureMergeRequest,
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


@router.patch("/models/{model_id}", response_model=FixtureModelResponse)
async def update_fixture_model(
    model_id: int,
    model_data: FixtureModelUpdate,
    session: AsyncSession = Depends(get_session)
):
    """Update a fixture model"""
    model = await session.get(FixtureModel, model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Fixture model not found")

    # Update fields
    update_data = model_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(model, field, value)

    await session.commit()
    await session.refresh(model)
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
    import structlog
    logger = structlog.get_logger(__name__)

    # Debug: Log database connection info
    logger.debug("list_fixtures_called", session_id=id(session))

    result = await session.execute(select(Fixture))
    fixtures = result.scalars().all()

    logger.debug("list_fixtures_result", count=len(fixtures), fixtures=[f.id for f in fixtures])

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

    # Check if fixture_model_id is being changed and exists
    if "fixture_model_id" in update_data:
        model = await session.get(FixtureModel, update_data["fixture_model_id"])
        if not model:
            raise HTTPException(
                status_code=404,
                detail=f"Fixture model {update_data['fixture_model_id']} not found"
            )

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
    """Delete a fixture and all related records"""
    fixture = await session.get(Fixture, fixture_id)
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")

    # Delete fixture state first (required due to SQLAlchemy session sync)
    state = await session.get(FixtureState, fixture_id)
    if state:
        await session.delete(state)

    # Delete switches that target this fixture (can't SET NULL due to one_target_only constraint)
    result = await session.execute(
        select(Switch).where(Switch.target_fixture_id == fixture_id)
    )
    switches = result.scalars().all()
    for switch in switches:
        await session.delete(switch)

    await session.delete(fixture)
    await session.commit()


@router.get("/{fixture_id}/state")
async def get_fixture_state(
    fixture_id: int,
    session: AsyncSession = Depends(get_session)
):
    """
    Get fixture current state.

    Returns in-memory state (with goal/current values) when daemon is running,
    otherwise falls back to database state.
    """
    from tau.api import get_daemon_instance

    daemon = get_daemon_instance()

    # Try to get in-memory state from StateManager (has goal/current split)
    if daemon and daemon.state_manager:
        mem_state = daemon.state_manager.get_fixture_state(fixture_id)
        if mem_state:
            return {
                "fixture_id": fixture_id,
                "goal_brightness": int(mem_state.goal_brightness * 1000),
                "goal_cct": mem_state.goal_color_temp,
                "current_brightness": int(mem_state.current_brightness * 1000),
                "current_cct": mem_state.current_color_temp,
                "is_on": mem_state.current_brightness > 0,
                "transitioning": mem_state.transition_start is not None,
            }

    # Fall back to database state
    state = await session.get(FixtureState, fixture_id)
    if not state:
        raise HTTPException(status_code=404, detail="Fixture state not found")

    # Return database state (no goal values, only current)
    return {
        "fixture_id": fixture_id,
        "goal_brightness": state.current_brightness,
        "goal_cct": state.current_cct,
        "current_brightness": state.current_brightness,
        "current_cct": state.current_cct,
        "is_on": state.is_on,
        "transitioning": False,
    }


@router.post("/merge", response_model=FixtureResponse)
async def merge_fixtures(
    merge_data: FixtureMergeRequest,
    session: AsyncSession = Depends(get_session)
):
    """
    Merge two fixtures into one tunable white fixture.

    The primary fixture keeps its name.
    The secondary fixture's DMX channel becomes the secondary_dmx_channel.
    If target_model_id is provided, the primary fixture's model is updated.
    The secondary fixture is deleted after merge.
    """
    import structlog
    logger = structlog.get_logger(__name__)

    # Get both fixtures
    primary = await session.get(Fixture, merge_data.primary_fixture_id)
    secondary = await session.get(Fixture, merge_data.secondary_fixture_id)

    if not primary:
        raise HTTPException(status_code=404, detail="Primary fixture not found")
    if not secondary:
        raise HTTPException(status_code=404, detail="Secondary fixture not found")

    if primary.id == secondary.id:
        raise HTTPException(status_code=400, detail="Cannot merge a fixture with itself")

    # Check if primary already has a secondary channel
    if primary.secondary_dmx_channel is not None:
        raise HTTPException(
            status_code=400,
            detail="Primary fixture already has a secondary DMX channel"
        )

    # If target_model_id provided, verify it exists
    if merge_data.target_model_id:
        target_model = await session.get(FixtureModel, merge_data.target_model_id)
        if not target_model:
            raise HTTPException(status_code=404, detail="Target fixture model not found")

    logger.info(
        "merge_fixtures",
        primary_id=primary.id,
        primary_name=primary.name,
        primary_dmx=primary.dmx_channel_start,
        secondary_id=secondary.id,
        secondary_name=secondary.name,
        secondary_dmx=secondary.dmx_channel_start,
        target_model_id=merge_data.target_model_id
    )

    # Update primary fixture with secondary's DMX channel
    primary.secondary_dmx_channel = secondary.dmx_channel_start

    # Update model if target_model_id provided
    if merge_data.target_model_id:
        primary.fixture_model_id = merge_data.target_model_id

    # Delete the secondary fixture's state first (if exists)
    secondary_state = await session.get(FixtureState, secondary.id)
    if secondary_state:
        await session.delete(secondary_state)

    # Delete the secondary fixture
    await session.delete(secondary)

    await session.commit()
    await session.refresh(primary)

    logger.info(
        "merge_fixtures_complete",
        merged_fixture_id=primary.id,
        dmx_channels=f"{primary.dmx_channel_start}+{primary.secondary_dmx_channel}",
        new_model_id=primary.fixture_model_id
    )

    return primary


@router.post("/{fixture_id}/unmerge", response_model=FixtureResponse)
async def unmerge_fixture(
    fixture_id: int,
    session: AsyncSession = Depends(get_session)
):
    """
    Unmerge a fixture by removing its secondary DMX channel.
    Does NOT recreate the secondary fixture - just removes the secondary channel reference.
    """
    fixture = await session.get(Fixture, fixture_id)
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")

    if fixture.secondary_dmx_channel is None:
        raise HTTPException(status_code=400, detail="Fixture has no secondary channel to unmerge")

    fixture.secondary_dmx_channel = None
    await session.commit()
    await session.refresh(fixture)

    return fixture
