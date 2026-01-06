"""
Scenes API Routes - CRUD operations for scenes and scene control
"""
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from tau.database import get_session
from tau.models.scenes import Scene, SceneValue
from tau.models.fixtures import Fixture
from tau.api.schemas import (
    SceneCreate,
    SceneUpdate,
    SceneResponse,
    SceneCaptureRequest,
    SceneRecallRequest,
    SceneCreateWithValues,
    SceneValueCreate,
    SceneValuesUpdateRequest,
    SceneValueResponse,
)
from tau.api import get_daemon_instance
from tau.api.websocket import broadcast_scene_recalled

router = APIRouter()


@router.get("/", response_model=List[SceneResponse])
async def list_scenes(
    scope_group_id: int = None,
    session: AsyncSession = Depends(get_session)
):
    """List all scenes, optionally filtered by scope"""
    query = select(Scene).options(selectinload(Scene.values))

    if scope_group_id is not None:
        query = query.where(Scene.scope_group_id == scope_group_id)

    result = await session.execute(query)
    scenes = result.scalars().all()
    return scenes


@router.post("/", response_model=SceneResponse, status_code=201)
async def create_scene(
    scene_data: SceneCreate,
    session: AsyncSession = Depends(get_session)
):
    """Create a new scene (empty - use capture to populate)"""
    # Verify scope group exists if specified
    if scene_data.scope_group_id:
        from tau.models.groups import Group
        group = await session.get(Group, scene_data.scope_group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")

    scene = Scene(**scene_data.model_dump())
    session.add(scene)
    await session.commit()
    await session.refresh(scene)
    return scene


@router.get("/{scene_id}", response_model=SceneResponse)
async def get_scene(
    scene_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Get a specific scene"""
    scene = await session.get(
        Scene,
        scene_id,
        options=[selectinload(Scene.values)]
    )
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    return scene


@router.patch("/{scene_id}", response_model=SceneResponse)
async def update_scene(
    scene_id: int,
    scene_data: SceneUpdate,
    session: AsyncSession = Depends(get_session)
):
    """Update a scene"""
    scene = await session.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    # Update fields
    update_data = scene_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(scene, field, value)

    await session.commit()
    await session.refresh(scene)
    return scene


@router.delete("/{scene_id}", status_code=204)
async def delete_scene(
    scene_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Delete a scene"""
    scene = await session.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    await session.delete(scene)
    await session.commit()


@router.post("/capture", response_model=SceneResponse, status_code=201)
async def capture_scene(
    capture_data: SceneCaptureRequest,
    session: AsyncSession = Depends(get_session)
):
    """Capture current state as a new scene"""
    daemon = get_daemon_instance()
    if not daemon or not daemon.lighting_controller:
        raise HTTPException(
            status_code=503,
            detail="Lighting controller not available"
        )

    # Use scene engine to capture
    scene_id = await daemon.lighting_controller.scenes.capture_scene(
        name=capture_data.name,
        fixture_ids=capture_data.fixture_ids,
        scope_group_id=capture_data.scope_group_id
    )

    if not scene_id:
        raise HTTPException(status_code=500, detail="Failed to capture scene")

    # Return the created scene
    scene = await session.get(
        Scene,
        scene_id,
        options=[selectinload(Scene.values)]
    )
    return scene


@router.post("/recall", status_code=200)
async def recall_scene(
    recall_data: SceneRecallRequest,
    session: AsyncSession = Depends(get_session)
):
    """Recall a scene (apply its values to fixtures)"""
    daemon = get_daemon_instance()
    if not daemon or not daemon.lighting_controller:
        raise HTTPException(
            status_code=503,
            detail="Lighting controller not available"
        )

    # Get scene name for broadcast
    scene = await session.get(Scene, recall_data.scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    # Use scene engine to recall
    success = await daemon.lighting_controller.scenes.recall_scene(
        scene_id=recall_data.scene_id,
        fade_duration=recall_data.fade_duration
    )

    if not success:
        raise HTTPException(status_code=404, detail="Scene recall failed")

    # Broadcast scene recalled event
    await broadcast_scene_recalled(
        scene_id=recall_data.scene_id,
        scene_name=scene.name
    )

    return {"message": "Scene recalled successfully"}


@router.post("/with-values", response_model=SceneResponse, status_code=201)
async def create_scene_with_values(
    scene_data: SceneCreateWithValues,
    session: AsyncSession = Depends(get_session)
):
    """Create a new scene with explicit fixture values"""
    # Verify scope group exists if specified
    if scene_data.scope_group_id:
        from tau.models.groups import Group
        group = await session.get(Group, scene_data.scope_group_id)
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")

    # Verify all fixtures exist
    fixture_ids = [v.fixture_id for v in scene_data.values]
    if fixture_ids:
        result = await session.execute(
            select(Fixture.id).where(Fixture.id.in_(fixture_ids))
        )
        existing_ids = set(row[0] for row in result)
        missing = set(fixture_ids) - existing_ids
        if missing:
            raise HTTPException(
                status_code=404,
                detail=f"Fixtures not found: {list(missing)}"
            )

    # Create scene
    scene = Scene(
        name=scene_data.name,
        scope_group_id=scene_data.scope_group_id,
    )
    session.add(scene)
    await session.flush()

    # Create scene values
    for value_data in scene_data.values:
        scene_value = SceneValue(
            scene_id=scene.id,
            fixture_id=value_data.fixture_id,
            target_brightness=value_data.target_brightness,
            target_cct_kelvin=value_data.target_cct_kelvin,
        )
        session.add(scene_value)

    await session.commit()
    await session.refresh(scene)

    # Reload with values
    scene = await session.get(
        Scene,
        scene.id,
        options=[selectinload(Scene.values)]
    )

    # Invalidate scene cache in engine
    daemon = get_daemon_instance()
    if daemon and daemon.lighting_controller:
        if scene.id in daemon.lighting_controller.scenes.scenes:
            del daemon.lighting_controller.scenes.scenes[scene.id]

    return scene


@router.get("/{scene_id}/values", response_model=List[SceneValueResponse])
async def get_scene_values(
    scene_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Get all values for a scene"""
    scene = await session.get(
        Scene,
        scene_id,
        options=[selectinload(Scene.values)]
    )
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")
    return scene.values


@router.put("/{scene_id}/values", response_model=SceneResponse)
async def update_scene_values(
    scene_id: int,
    values_data: SceneValuesUpdateRequest,
    session: AsyncSession = Depends(get_session)
):
    """Update multiple scene values at once (replaces all values)"""
    scene = await session.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    # Verify all fixtures exist
    fixture_ids = [v.fixture_id for v in values_data.values]
    result = await session.execute(
        select(Fixture.id).where(Fixture.id.in_(fixture_ids))
    )
    existing_ids = set(row[0] for row in result)
    missing = set(fixture_ids) - existing_ids
    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Fixtures not found: {list(missing)}"
        )

    # Delete all existing scene values
    await session.execute(
        delete(SceneValue).where(SceneValue.scene_id == scene_id)
    )

    # Create new scene values
    for value_data in values_data.values:
        scene_value = SceneValue(
            scene_id=scene_id,
            fixture_id=value_data.fixture_id,
            target_brightness=value_data.target_brightness,
            target_cct_kelvin=value_data.target_cct_kelvin,
        )
        session.add(scene_value)

    await session.commit()

    # Reload scene with values
    scene = await session.get(
        Scene,
        scene_id,
        options=[selectinload(Scene.values)]
    )

    # Invalidate scene cache in engine
    daemon = get_daemon_instance()
    if daemon and daemon.lighting_controller:
        if scene_id in daemon.lighting_controller.scenes.scenes:
            del daemon.lighting_controller.scenes.scenes[scene_id]

    return scene


@router.post("/{scene_id}/values/{fixture_id}", response_model=SceneValueResponse)
async def set_scene_value(
    scene_id: int,
    fixture_id: int,
    value_data: SceneValueCreate,
    session: AsyncSession = Depends(get_session)
):
    """Set or update a single fixture value in a scene"""
    # Verify scene exists
    scene = await session.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    # Verify fixture exists
    fixture = await session.get(Fixture, fixture_id)
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")

    # Check if value already exists
    existing = await session.get(SceneValue, (scene_id, fixture_id))

    if existing:
        # Update existing value
        if value_data.target_brightness is not None:
            existing.target_brightness = value_data.target_brightness
        if value_data.target_cct_kelvin is not None:
            existing.target_cct_kelvin = value_data.target_cct_kelvin
        scene_value = existing
    else:
        # Create new value
        scene_value = SceneValue(
            scene_id=scene_id,
            fixture_id=fixture_id,
            target_brightness=value_data.target_brightness,
            target_cct_kelvin=value_data.target_cct_kelvin,
        )
        session.add(scene_value)

    await session.commit()
    await session.refresh(scene_value)

    # Invalidate scene cache in engine
    daemon = get_daemon_instance()
    if daemon and daemon.lighting_controller:
        if scene_id in daemon.lighting_controller.scenes.scenes:
            del daemon.lighting_controller.scenes.scenes[scene_id]

    return scene_value


@router.delete("/{scene_id}/values/{fixture_id}", status_code=204)
async def remove_scene_value(
    scene_id: int,
    fixture_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Remove a fixture from a scene"""
    # Verify scene exists
    scene = await session.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    # Check if value exists
    existing = await session.get(SceneValue, (scene_id, fixture_id))
    if not existing:
        raise HTTPException(status_code=404, detail="Fixture not in scene")

    await session.delete(existing)
    await session.commit()

    # Invalidate scene cache in engine
    daemon = get_daemon_instance()
    if daemon and daemon.lighting_controller:
        if scene_id in daemon.lighting_controller.scenes.scenes:
            del daemon.lighting_controller.scenes.scenes[scene_id]


@router.get("/current-state", response_model=List[SceneValueResponse])
async def get_current_fixture_states(
    session: AsyncSession = Depends(get_session)
):
    """Get current state of all fixtures (for scene capture preview)"""
    daemon = get_daemon_instance()
    if not daemon or not daemon.state_manager:
        raise HTTPException(
            status_code=503,
            detail="State manager not available"
        )

    # Get all fixtures
    result = await session.execute(select(Fixture.id))
    fixture_ids = [row[0] for row in result]

    states = []
    for fixture_id in fixture_ids:
        state = daemon.state_manager.get_fixture_state(fixture_id)
        if state:
            # Convert state manager brightness (0.0-1.0) to API format (0-1000)
            brightness_db = int(state.brightness * 1000)
            states.append(SceneValueResponse(
                fixture_id=fixture_id,
                target_brightness=brightness_db,
                target_cct_kelvin=state.color_temp,
            ))

    return states
