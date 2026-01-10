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
        include_group_ids=capture_data.include_group_ids,
        exclude_fixture_ids=capture_data.exclude_fixture_ids,
        exclude_group_ids=capture_data.exclude_group_ids,
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
