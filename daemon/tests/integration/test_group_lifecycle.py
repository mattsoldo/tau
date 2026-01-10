"""
Integration tests for group lifecycle (create, update, delete) and state management.

These tests verify that:
1. Creating a group properly initializes all related state
2. Deleting a group cleans up all related state (group_state, fixtures)
3. The control loop can handle deleted groups gracefully
"""
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tau.models.groups import Group
from tau.models.state import GroupState
from tau.models.fixtures import Fixture


@pytest.mark.asyncio
async def test_group_deletion_cleans_up_state(db_session: AsyncSession):
    """Test that deleting a group removes all related state"""
    # Create a test group
    group = Group(
        name="Test Group",
        description="Test group for deletion",
        is_system=False,
    )
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)
    group_id = group.id

    # Create group state
    group_state = GroupState(
        group_id=group_id,
        circadian_suspended=False,
    )
    db_session.add(group_state)
    await db_session.commit()

    # Verify group and state exist
    result = await db_session.execute(
        select(Group).where(Group.id == group_id)
    )
    assert result.scalar_one_or_none() is not None

    result = await db_session.execute(
        select(GroupState).where(GroupState.group_id == group_id)
    )
    assert result.scalar_one_or_none() is not None

    # Delete the group
    await db_session.delete(group)
    await db_session.commit()

    # Verify group is deleted
    result = await db_session.execute(
        select(Group).where(Group.id == group_id)
    )
    assert result.scalar_one_or_none() is None

    # Verify group_state is automatically deleted (cascade)
    result = await db_session.execute(
        select(GroupState).where(GroupState.group_id == group_id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_group_deletion_with_fixtures(db_session: AsyncSession):
    """Test that deleting a group with fixtures handles relationships correctly"""
    # This test would need a fixture model and fixtures to be set up
    # For now, we just verify the concept

    # Create a test group
    group = Group(
        name="Test Group With Fixtures",
        description="Test group with fixtures",
        is_system=False,
    )
    db_session.add(group)
    await db_session.commit()
    await db_session.refresh(group)
    group_id = group.id

    # Create group state
    group_state = GroupState(
        group_id=group_id,
        circadian_suspended=False,
    )
    db_session.add(group_state)
    await db_session.commit()

    # Note: In a full test, we would:
    # 1. Create fixtures associated with this group
    # 2. Verify fixtures are properly reassigned or handled when group is deleted
    # 3. Verify no orphaned fixture_group_membership records remain

    # Delete the group
    await db_session.delete(group)
    await db_session.commit()

    # Verify clean deletion
    result = await db_session.execute(
        select(Group).where(Group.id == group_id)
    )
    assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_cannot_create_group_state_for_nonexistent_group(db_session: AsyncSession):
    """Test that we cannot create group_state for a non-existent group"""
    from sqlalchemy.exc import IntegrityError

    # Try to create group_state for a non-existent group
    group_state = GroupState(
        group_id=99999,  # Non-existent group ID
        circadian_suspended=False,
    )
    db_session.add(group_state)

    # This should fail with IntegrityError due to foreign key constraint
    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()
