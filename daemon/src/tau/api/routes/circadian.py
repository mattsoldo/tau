"""
Circadian API Routes - CRUD operations for circadian profiles
"""
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from tau.database import get_session
from tau.models.circadian import CircadianProfile
from tau.api import get_daemon_instance
from tau.api.schemas import (
    CircadianProfileCreate,
    CircadianProfileUpdate,
    CircadianProfileResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get("/", response_model=List[CircadianProfileResponse])
async def list_circadian_profiles(
    session: AsyncSession = Depends(get_session)
):
    """List all circadian profiles"""
    result = await session.execute(select(CircadianProfile))
    profiles = result.scalars().all()
    return profiles


@router.post("/", response_model=CircadianProfileResponse, status_code=201)
async def create_circadian_profile(
    profile_data: CircadianProfileCreate,
    session: AsyncSession = Depends(get_session)
):
    """Create a new circadian profile"""
    # Convert Pydantic keyframes to dict format for JSONB
    keyframes_json = [
        {
            "time": kf.time,
            "brightness": kf.brightness,
            "cct": kf.cct
        }
        for kf in profile_data.keyframes
    ]

    profile = CircadianProfile(
        name=profile_data.name,
        description=profile_data.description,
        keyframes=keyframes_json
    )

    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


@router.get("/{profile_id}", response_model=CircadianProfileResponse)
async def get_circadian_profile(
    profile_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Get a specific circadian profile"""
    profile = await session.get(CircadianProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Circadian profile not found")
    return profile


@router.patch("/{profile_id}", response_model=CircadianProfileResponse)
async def update_circadian_profile(
    profile_id: int,
    profile_data: CircadianProfileUpdate,
    session: AsyncSession = Depends(get_session)
):
    """Update a circadian profile"""
    profile = await session.get(CircadianProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Circadian profile not found")

    # Update fields
    update_data = profile_data.model_dump(exclude_unset=True)

    # Track if keyframes changed
    keyframes_changed = "keyframes" in update_data and update_data["keyframes"]

    # Convert keyframes if provided
    if keyframes_changed:
        keyframes_json = [
            {
                "time": kf.time,
                "brightness": kf.brightness,
                "cct": kf.cct
            }
            for kf in update_data["keyframes"]
        ]
        update_data["keyframes"] = keyframes_json

    for field, value in update_data.items():
        setattr(profile, field, value)

    await session.commit()
    await session.refresh(profile)

    # Hot-reload profile in circadian engine if keyframes changed
    if keyframes_changed:
        daemon = get_daemon_instance()
        if daemon and daemon.lighting_controller:
            try:
                await daemon.lighting_controller.reload_circadian_profile(profile_id)
                logger.info(
                    "circadian_profile_reloaded",
                    profile_id=profile_id,
                    keyframe_count=len(update_data["keyframes"]),
                )
            except Exception as e:
                logger.error(
                    "circadian_profile_reload_failed",
                    profile_id=profile_id,
                    error=str(e),
                )

    return profile


@router.delete("/{profile_id}", status_code=204)
async def delete_circadian_profile(
    profile_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Delete a circadian profile"""
    profile = await session.get(CircadianProfile, profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Circadian profile not found")

    # Check if any groups are using this profile
    from tau.models.groups import Group
    result = await session.execute(
        select(Group).where(Group.circadian_profile_id == profile_id)
    )
    groups = result.scalars().all()

    if groups:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot delete profile: {len(groups)} group(s) are using it"
        )

    await session.delete(profile)
    await session.commit()
