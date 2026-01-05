"""
Groups API Routes - CRUD operations for groups and membership management
"""
from typing import List
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
import structlog

from tau.database import get_session
from tau.models.groups import Group, GroupFixture
from tau.models.fixtures import Fixture
from tau.models.state import GroupState
from tau.api import get_daemon_instance
from tau.api.schemas import (
    GroupCreate,
    GroupUpdate,
    GroupResponse,
    GroupFixtureAdd,
    GroupStateResponse,
    FixtureResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get("/", response_model=List[GroupResponse])
async def list_groups(
    session: AsyncSession = Depends(get_session)
):
    """List all groups"""
    result = await session.execute(select(Group))
    groups = result.scalars().all()
    return groups


@router.post("/", response_model=GroupResponse, status_code=201)
async def create_group(
    group_data: GroupCreate,
    session: AsyncSession = Depends(get_session)
):
    """Create a new group"""
    # Verify circadian profile exists if specified
    if group_data.circadian_profile_id:
        from tau.models.circadian import CircadianProfile
        profile = await session.get(CircadianProfile, group_data.circadian_profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Circadian profile not found")

    group = Group(**group_data.model_dump())
    session.add(group)
    await session.commit()
    await session.refresh(group)

    # Create initial state
    state = GroupState(
        group_id=group.id,
        circadian_suspended=not group_data.circadian_enabled
    )
    session.add(state)
    await session.commit()

    # Register group with StateManager so it can be controlled immediately
    daemon = get_daemon_instance()
    if daemon and daemon.state_manager:
        try:
            daemon.state_manager.register_group(group.id)
            # Set circadian enabled flag
            group_state = daemon.state_manager.groups.get(group.id)
            if group_state:
                group_state.circadian_enabled = group_data.circadian_enabled
            logger.info(
                "group_registered_in_state_manager",
                group_id=group.id,
                group_name=group.name,
                circadian_enabled=group_data.circadian_enabled
            )
        except Exception as e:
            logger.error(
                "state_manager_sync_failed",
                operation="register_group",
                group_id=group.id,
                error=str(e)
            )

    return group


@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Get a specific group"""
    group = await session.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


@router.patch("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: int,
    group_data: GroupUpdate,
    session: AsyncSession = Depends(get_session)
):
    """Update a group"""
    group = await session.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Update fields
    update_data = group_data.model_dump(exclude_unset=True)

    # Verify circadian profile exists if being changed
    if "circadian_profile_id" in update_data and update_data["circadian_profile_id"]:
        from tau.models.circadian import CircadianProfile
        profile = await session.get(CircadianProfile, update_data["circadian_profile_id"])
        if not profile:
            raise HTTPException(status_code=404, detail="Circadian profile not found")

    for field, value in update_data.items():
        setattr(group, field, value)

    await session.commit()
    await session.refresh(group)
    return group


@router.delete("/{group_id}", status_code=204)
async def delete_group(
    group_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Delete a group"""
    group = await session.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    await session.delete(group)
    await session.commit()

    # Unregister group from StateManager cache
    daemon = get_daemon_instance()
    if daemon and daemon.state_manager:
        try:
            daemon.state_manager.unregister_group(group_id)
            logger.info(
                "group_unregistered_from_state_manager",
                group_id=group_id
            )
        except Exception as e:
            logger.error(
                "state_manager_sync_failed",
                operation="unregister_group",
                group_id=group_id,
                error=str(e)
            )


@router.get("/{group_id}/state", response_model=GroupStateResponse)
async def get_group_state(
    group_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Get group current state"""
    state = await session.get(GroupState, group_id)
    if not state:
        raise HTTPException(status_code=404, detail="Group state not found")
    return state


# Fixture membership management
@router.get("/{group_id}/fixtures", response_model=List[FixtureResponse])
async def list_group_fixtures(
    group_id: int,
    session: AsyncSession = Depends(get_session)
):
    """List all fixtures in a group"""
    # Verify group exists
    group = await session.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Get all fixtures in group
    result = await session.execute(
        select(Fixture)
        .join(GroupFixture)
        .where(GroupFixture.group_id == group_id)
    )
    fixtures = result.scalars().all()
    return fixtures


@router.post("/{group_id}/fixtures", status_code=201)
async def add_fixture_to_group(
    group_id: int,
    fixture_data: GroupFixtureAdd,
    session: AsyncSession = Depends(get_session)
):
    """Add a fixture to a group"""
    # Verify group exists
    group = await session.get(Group, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Verify fixture exists
    fixture = await session.get(Fixture, fixture_data.fixture_id)
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")

    # Check if already a member
    result = await session.execute(
        select(GroupFixture).where(
            GroupFixture.group_id == group_id,
            GroupFixture.fixture_id == fixture_data.fixture_id
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Fixture already in group")

    # Add membership
    membership = GroupFixture(group_id=group_id, fixture_id=fixture_data.fixture_id)
    session.add(membership)
    await session.commit()

    # Update StateManager cache so the fixture responds to group controls immediately
    daemon = get_daemon_instance()
    if daemon and daemon.state_manager:
        try:
            daemon.state_manager.add_fixture_to_group(fixture_data.fixture_id, group_id)
            logger.info(
                "fixture_added_to_group_in_state_manager",
                fixture_id=fixture_data.fixture_id,
                group_id=group_id
            )
        except Exception as e:
            logger.error(
                "state_manager_sync_failed",
                operation="add_fixture_to_group",
                fixture_id=fixture_data.fixture_id,
                group_id=group_id,
                error=str(e)
            )

    return {"message": "Fixture added to group successfully"}


@router.delete("/{group_id}/fixtures/{fixture_id}", status_code=204)
async def remove_fixture_from_group(
    group_id: int,
    fixture_id: int,
    session: AsyncSession = Depends(get_session)
):
    """Remove a fixture from a group"""
    # Find membership
    result = await session.execute(
        select(GroupFixture).where(
            GroupFixture.group_id == group_id,
            GroupFixture.fixture_id == fixture_id
        )
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=404, detail="Fixture not in group")

    await session.delete(membership)
    await session.commit()

    # Update StateManager cache so removed fixtures no longer respond to group controls
    daemon = get_daemon_instance()
    if daemon and daemon.state_manager:
        try:
            daemon.state_manager.remove_fixture_from_group(fixture_id, group_id)
            logger.info(
                "fixture_removed_from_group_in_state_manager",
                fixture_id=fixture_id,
                group_id=group_id
            )
        except Exception as e:
            logger.error(
                "state_manager_sync_failed",
                operation="remove_fixture_from_group",
                fixture_id=fixture_id,
                group_id=group_id,
                error=str(e)
            )
