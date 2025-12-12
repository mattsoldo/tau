"""
State Persistence - Periodic saving of runtime state to database

Handles persisting the in-memory state managed by StateManager to the
database at regular intervals (e.g., every 5 seconds).
"""
from datetime import datetime
from typing import Optional
import structlog

from tau.control.state_manager import StateManager
from tau.database import get_session
from tau.models import FixtureState, GroupState

logger = structlog.get_logger(__name__)


class StatePersistence:
    """
    Manages periodic persistence of runtime state to database

    Runs as a scheduled task to save state every N seconds.
    Only saves state if it has been modified (dirty flag).
    """

    def __init__(self, state_manager: StateManager):
        """
        Initialize state persistence

        Args:
            state_manager: StateManager instance to persist
        """
        self.state_manager = state_manager
        self.last_save_time: Optional[datetime] = None
        self.total_saves = 0
        self.failed_saves = 0

        logger.info("state_persistence_initialized")

    async def save_state(self) -> None:
        """
        Save current state to database

        This is called periodically by the scheduler. It only saves
        if the state has been modified since the last save.
        """
        # Skip if state hasn't changed
        if not self.state_manager.dirty:
            logger.debug("state_persistence_skipped", reason="not_dirty")
            return

        logger.debug("state_persistence_starting")
        start_time = datetime.now()

        try:
            async with get_session() as session:
                # Save fixture states
                fixture_count = await self._save_fixture_states(session)

                # Save group states
                group_count = await self._save_group_states(session)

                # Commit transaction
                await session.commit()

            # Mark state as clean
            self.state_manager.mark_clean()
            self.last_save_time = datetime.now()
            self.total_saves += 1

            duration = (datetime.now() - start_time).total_seconds()
            logger.info(
                "state_persisted",
                fixtures=fixture_count,
                groups=group_count,
                duration_ms=round(duration * 1000, 2),
            )

        except Exception as e:
            self.failed_saves += 1
            logger.error(
                "state_persistence_failed",
                error=str(e),
                exc_info=True,
            )

    async def _save_fixture_states(self, session) -> int:
        """
        Save all fixture states to database

        Args:
            session: Async database session

        Returns:
            Number of fixtures saved
        """
        count = 0

        for fixture_id, state_data in self.state_manager.fixtures.items():
            # Check if state exists
            result = await session.get(FixtureState, fixture_id)

            # Convert float brightness (0-1) to int (0-1000) for database
            current_brightness = int(state_data.brightness * 1000)
            current_cct = state_data.color_temp
            is_on = state_data.brightness > 0.0

            if result:
                # Update existing state
                result.current_brightness = current_brightness
                result.current_cct = current_cct
                result.is_on = is_on
                if state_data.last_updated:
                    result.last_updated = datetime.fromtimestamp(state_data.last_updated)
                else:
                    result.last_updated = datetime.now()
            else:
                # Create new state
                new_state = FixtureState(
                    fixture_id=fixture_id,
                    current_brightness=current_brightness,
                    current_cct=current_cct,
                    is_on=is_on,
                    last_updated=datetime.fromtimestamp(state_data.last_updated)
                    if state_data.last_updated
                    else datetime.now(),
                )
                session.add(new_state)

            count += 1

        return count

    async def _save_group_states(self, session) -> int:
        """
        Save all group states to database

        GroupState in the database only tracks circadian suspension and last active scene,
        not brightness/color values. For Phase 2, we just ensure the record exists.

        Args:
            session: Async database session

        Returns:
            Number of groups saved
        """
        count = 0

        for group_id, state_data in self.state_manager.groups.items():
            # Check if state exists
            result = await session.get(GroupState, group_id)

            if result:
                # Update existing state
                # In Phase 2, we just ensure the record exists
                # Circadian suspension and scene tracking will be added in Phase 4
                pass
            else:
                # Create new state record
                new_state = GroupState(
                    group_id=group_id,
                    circadian_suspended=False,
                )
                session.add(new_state)

            count += 1

        return count

    def get_statistics(self) -> dict:
        """
        Get persistence statistics

        Returns:
            Dictionary with statistics
        """
        return {
            "total_saves": self.total_saves,
            "failed_saves": self.failed_saves,
            "last_save": self.last_save_time.isoformat() if self.last_save_time else None,
        }
