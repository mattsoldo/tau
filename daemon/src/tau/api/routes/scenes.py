"""
Scenes API Routes - CRUD operations for scenes and scene control
"""
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from tau.database import get_session
from tau.models.scenes import Scene, SceneValue
from tau.api.schemas import (
    SceneCreate,
    SceneUpdate,
    SceneResponse,
    SceneCaptureRequest,
    SceneRecallRequest,
    SceneReorderRequest,
    SceneValuesUpdateRequest,
)
import structlog

logger = structlog.get_logger(__name__)
from tau.api import get_daemon_instance
from tau.api.websocket import broadcast_scene_recalled

router = APIRouter()


@router.get("/", response_model=List[SceneResponse])
async def list_scenes(
    scope_group_id: int = None,
    session: AsyncSession = Depends(get_session)
):
    """List all scenes, optionally filtered by scope, sorted by display_order"""
    query = select(Scene).options(selectinload(Scene.values))

    if scope_group_id is not None:
        query = query.where(Scene.scope_group_id == scope_group_id)

    # Sort by display_order (nulls last), then by name
    query = query.order_by(Scene.display_order.asc().nullslast(), Scene.name)

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
    await session.refresh(scene, attribute_names=["values"])
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
    await session.refresh(scene, attribute_names=["values"])
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


@router.put("/{scene_id}/values", response_model=SceneResponse)
async def update_scene_values(
    scene_id: int,
    values_data: SceneValuesUpdateRequest,
    session: AsyncSession = Depends(get_session)
):
    """Update scene fixture values (brightness/CCT levels)

    Replaces existing values for specified fixtures. To remove a fixture
    from the scene, omit it from the values list.
    """
    scene = await session.get(
        Scene,
        scene_id,
        options=[selectinload(Scene.values)]
    )
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    # Build a map of existing values by fixture_id
    existing_values = {v.fixture_id: v for v in scene.values}

    # Update or create values for each fixture in the request
    for value_update in values_data.values:
        if value_update.fixture_id in existing_values:
            # Update existing value
            existing = existing_values[value_update.fixture_id]
            if value_update.target_brightness is not None:
                existing.target_brightness = value_update.target_brightness
            if value_update.target_cct_kelvin is not None:
                existing.target_cct_kelvin = value_update.target_cct_kelvin
        else:
            # Create new value
            new_value = SceneValue(
                scene_id=scene_id,
                fixture_id=value_update.fixture_id,
                target_brightness=value_update.target_brightness,
                target_cct_kelvin=value_update.target_cct_kelvin
            )
            session.add(new_value)

    await session.commit()
    await session.refresh(scene, attribute_names=["values"])

    logger.info(
        "scene_values_updated",
        scene_id=scene_id,
        fixture_count=len(values_data.values)
    )

    return scene


@router.delete("/{scene_id}/values/{fixture_id}", response_model=SceneResponse)
async def remove_fixture_from_scene(
    scene_id: int,
    fixture_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Remove a fixture from a scene"""
    scene = await session.get(
        Scene,
        scene_id,
        options=[selectinload(Scene.values)]
    )
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    # Find and remove the fixture value
    value_to_remove = None
    for value in scene.values:
        if value.fixture_id == fixture_id:
            value_to_remove = value
            break

    if not value_to_remove:
        raise HTTPException(status_code=404, detail="Fixture not in scene")

    await session.delete(value_to_remove)
    await session.commit()
    await session.refresh(scene, attribute_names=["values"])

    logger.info(
        "fixture_removed_from_scene",
        scene_id=scene_id,
        fixture_id=fixture_id
    )

    return scene


@router.post("/{scene_id}/values/{fixture_id}", response_model=SceneResponse)
async def add_fixture_to_scene(
    scene_id: int,
    fixture_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Add a fixture to a scene using its current state"""
    daemon = get_daemon_instance()
    if not daemon or not daemon.state_manager:
        raise HTTPException(status_code=503, detail="State manager not available")

    scene = await session.get(
        Scene,
        scene_id,
        options=[selectinload(Scene.values)]
    )
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    # Check if fixture already in scene
    for value in scene.values:
        if value.fixture_id == fixture_id:
            raise HTTPException(status_code=400, detail="Fixture already in scene")

    # Get current fixture state
    fixture_state = daemon.state_manager.fixtures.get(fixture_id)
    if not fixture_state:
        raise HTTPException(status_code=404, detail="Fixture not found")

    # Create new scene value from current state
    new_value = SceneValue(
        scene_id=scene_id,
        fixture_id=fixture_id,
        target_brightness=int(fixture_state.goal_brightness * 1000),
        target_cct_kelvin=fixture_state.goal_color_temp
    )
    session.add(new_value)
    await session.commit()
    await session.refresh(scene, attribute_names=["values"])

    logger.info(
        "fixture_added_to_scene",
        scene_id=scene_id,
        fixture_id=fixture_id,
        brightness=new_value.target_brightness
    )

    return scene


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
        include_group_ids=capture_data.include_group_ids,
        exclude_fixture_ids=capture_data.exclude_fixture_ids,
        exclude_group_ids=capture_data.exclude_group_ids,
        scope_group_id=capture_data.scope_group_id
    )

    if not scene_id:
        raise HTTPException(status_code=500, detail="Failed to capture scene")

    # Update scene_type if specified
    scene = await session.get(Scene, scene_id)
    if scene and capture_data.scene_type:
        scene.scene_type = capture_data.scene_type
        await session.commit()

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
    """Recall a scene (apply its values to fixtures)

    For toggle scenes: If all fixtures are at their scene levels, turn them off instead.
    For idempotent scenes: Always apply the scene values.
    """
    daemon = get_daemon_instance()
    if not daemon or not daemon.lighting_controller:
        raise HTTPException(
            status_code=503,
            detail="Lighting controller not available"
        )

    # Get scene with values for toggle check
    scene = await session.get(
        Scene,
        recall_data.scene_id,
        options=[selectinload(Scene.values)]
    )
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    # Check for toggle behavior
    should_turn_off = False
    if scene.scene_type == "toggle" and daemon.state_manager:
        # Check if all fixtures are at their scene levels
        all_at_scene_level = True
        scene_values_count = len(scene.values)
        logger.info(
            "toggle_scene_checking",
            scene_id=scene.id,
            scene_name=scene.name,
            values_count=scene_values_count
        )

        for scene_value in scene.values:
            fixture_state = daemon.state_manager.fixtures.get(scene_value.fixture_id)
            if fixture_state:
                # Convert goal_brightness (0.0-1.0) to 0-1000 scale for comparison
                current_brightness_1000 = int(fixture_state.goal_brightness * 1000)
                scene_brightness = scene_value.target_brightness or 0
                diff = abs(current_brightness_1000 - scene_brightness)

                logger.info(
                    "toggle_fixture_compare",
                    fixture_id=scene_value.fixture_id,
                    current_brightness_1000=current_brightness_1000,
                    scene_brightness=scene_brightness,
                    diff=diff,
                    matches=(diff <= 50)
                )

                # Allow small tolerance (50 units out of 1000 = 5%)
                if diff > 50:
                    all_at_scene_level = False
                    break
            else:
                logger.info(
                    "toggle_fixture_not_found",
                    fixture_id=scene_value.fixture_id
                )
                all_at_scene_level = False
                break

        should_turn_off = all_at_scene_level
        logger.info(
            "toggle_scene_result",
            scene_id=scene.id,
            all_at_scene_level=all_at_scene_level,
            should_turn_off=should_turn_off
        )

    if should_turn_off:
        # Turn off all fixtures in this scene
        for scene_value in scene.values:
            await daemon.lighting_controller.control.set_fixture_brightness(
                fixture_id=scene_value.fixture_id,
                brightness=0.0,
                transition_duration=recall_data.fade_duration
            )

        # Broadcast scene turned off
        await broadcast_scene_recalled(
            scene_id=recall_data.scene_id,
            scene_name=scene.name
        )
        return {"message": "Toggle scene turned off", "toggled_off": True}

    # Normal recall - apply scene values
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

    return {"message": "Scene recalled successfully", "toggled_off": False}


@router.post("/reorder", response_model=List[SceneResponse])
async def reorder_scenes(
    reorder_data: SceneReorderRequest,
    session: AsyncSession = Depends(get_session)
):
    """Reorder scenes by setting display_order based on the provided order"""
    # Update display_order for each scene
    for index, scene_id in enumerate(reorder_data.scene_ids):
        scene = await session.get(Scene, scene_id)
        if scene:
            scene.display_order = index

    await session.commit()

    # Return updated scenes
    result = await session.execute(
        select(Scene)
        .options(selectinload(Scene.values))
        .order_by(Scene.display_order.asc().nullslast())
    )
    scenes = result.scalars().all()
    logger.info("scenes_reordered", scene_ids=reorder_data.scene_ids)
    return scenes
