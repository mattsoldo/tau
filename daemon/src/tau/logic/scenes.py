"""
Scene Engine

Manages lighting scenes (static presets) that can be captured from current
state and recalled to quickly set specific lighting configurations. Scenes
store target brightness and CCT values for fixtures.
"""
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING
import structlog
from datetime import datetime

from tau.database import get_db_session
from tau.models.scenes import Scene, SceneValue
from tau.models.fixtures import Fixture
from tau.models.groups import GroupFixture

if TYPE_CHECKING:
    from tau.control.state_manager import StateManager

logger = structlog.get_logger(__name__)


class SceneEngine:
    """
    Scene management engine

    Handles storing and recalling lighting scenes (presets). Scenes capture
    the current state of fixtures and can be recalled later to restore that
    exact lighting configuration.
    """

    def __init__(self, state_manager: "StateManager"):
        """
        Initialize scene engine

        Args:
            state_manager: Reference to state manager for reading/writing fixture states
        """
        self.state_manager = state_manager

        # Cache of loaded scenes {scene_id: {fixture_id: (brightness, cct)}}
        self.scenes: Dict[int, Dict[int, Tuple[Optional[int], Optional[int]]]] = {}

        # Statistics
        self.scenes_recalled = 0
        self.scenes_captured = 0
        self.cache_hits = 0

        logger.info("scene_engine_initialized")

    async def load_scene(self, scene_id: int) -> bool:
        """
        Load a scene from database into cache

        Args:
            scene_id: ID of scene to load

        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            async with get_db_session() as session:
                scene = await session.get(Scene, scene_id)

                if not scene:
                    logger.warning("scene_not_found", scene_id=scene_id)
                    return False

                # Parse scene values
                scene_data = {}
                for value in scene.values:
                    scene_data[value.fixture_id] = (
                        value.target_brightness,
                        value.target_cct_kelvin
                    )

                # Cache scene
                self.scenes[scene_id] = scene_data

                logger.info(
                    "scene_loaded",
                    scene_id=scene_id,
                    scene_name=scene.name,
                    fixture_count=len(scene_data),
                )

                return True

        except Exception as e:
            logger.error(
                "scene_load_failed",
                scene_id=scene_id,
                error=str(e),
                exc_info=True,
            )
            return False

    async def capture_scene(
        self,
        name: str,
        fixture_ids: Optional[List[int]] = None,
        include_group_ids: Optional[List[int]] = None,
        exclude_fixture_ids: Optional[List[int]] = None,
        exclude_group_ids: Optional[List[int]] = None,
        scope_group_id: Optional[int] = None
    ) -> Optional[int]:
        """
        Capture current fixture states as a new scene

        Args:
            name: Name for the new scene
            fixture_ids: List of fixture IDs to capture (None = all fixtures)
            include_group_ids: Group IDs to include fixtures from
            exclude_fixture_ids: Fixture IDs to exclude from capture
            exclude_group_ids: Group IDs to exclude fixtures from
            scope_group_id: Optional group to scope this scene to

        Returns:
            ID of created scene, or None if failed
        """
        try:
            async with get_db_session() as session:
                from sqlalchemy import select

                # Determine which fixtures to capture
                include_fixture_ids = set(fixture_ids or [])
                include_group_ids = include_group_ids or []
                exclude_fixture_ids = set(exclude_fixture_ids or [])
                exclude_group_ids = exclude_group_ids or []

                if include_group_ids:
                    result = await session.execute(
                        select(GroupFixture.fixture_id).where(
                            GroupFixture.group_id.in_(include_group_ids)
                        )
                    )
                    include_fixture_ids.update(row[0] for row in result)

                if fixture_ids is None and not include_group_ids:
                    # Default to all fixtures when no include filters are provided
                    result = await session.execute(select(Fixture.id))
                    include_fixture_ids = {row[0] for row in result}

                if exclude_group_ids:
                    result = await session.execute(
                        select(GroupFixture.fixture_id).where(
                            GroupFixture.group_id.in_(exclude_group_ids)
                        )
                    )
                    exclude_fixture_ids.update(row[0] for row in result)

                fixture_ids = sorted(include_fixture_ids - exclude_fixture_ids)

                # Create scene record
                scene = Scene(
                    name=name,
                    scope_group_id=scope_group_id,
                )
                session.add(scene)
                await session.flush()  # Get scene.id

                # Capture current state for each fixture
                for fixture_id in fixture_ids:
                    state = self.state_manager.get_fixture_state(fixture_id)

                    if state is None:
                        logger.warning(
                            "fixture_not_found_during_capture",
                            fixture_id=fixture_id
                        )
                        continue

                    # Convert state manager brightness (0.0-1.0) to database (0-1000)
                    brightness_db = int(state.brightness * 1000)

                    # Create scene value
                    scene_value = SceneValue(
                        scene_id=scene.id,
                        fixture_id=fixture_id,
                        target_brightness=brightness_db,
                        target_cct_kelvin=state.color_temp,
                    )
                    session.add(scene_value)

                await session.commit()

                self.scenes_captured += 1

                logger.info(
                    "scene_captured",
                    scene_id=scene.id,
                    scene_name=name,
                    fixture_count=len(fixture_ids),
                )

                return scene.id

        except Exception as e:
            logger.error(
                "scene_capture_failed",
                name=name,
                error=str(e),
                exc_info=True,
            )
            return None

    async def recall_scene(
        self,
        scene_id: int,
        fade_duration: float = 0.0
    ) -> bool:
        """
        Recall a scene (apply its fixture values)

        Args:
            scene_id: ID of scene to recall
            fade_duration: Duration in seconds to fade to scene values (0 = instant)

        Returns:
            True if recalled successfully, False otherwise
        """
        # Check cache first
        if scene_id not in self.scenes:
            # Not cached, try to load
            loaded = await self.load_scene(scene_id)
            if not loaded:
                return False

        scene_data = self.scenes[scene_id]
        self.cache_hits += 1

        # TODO: Implement fade transitions (Phase 5 enhancement)
        # For now, apply instantly
        if fade_duration > 0:
            logger.warning(
                "fade_not_implemented",
                message="Fade transitions not yet implemented, applying instantly"
            )

        # Apply scene values to state manager
        success_count = 0
        for fixture_id, (brightness_db, cct) in scene_data.items():
            # Convert database brightness (0-1000) to state manager (0.0-1.0)
            brightness = brightness_db / 1000.0 if brightness_db is not None else 0.0

            # Update brightness
            if self.state_manager.set_fixture_brightness(fixture_id, brightness):
                success_count += 1

            # Update CCT if specified
            if cct is not None:
                self.state_manager.set_fixture_color_temp(fixture_id, cct)

        self.scenes_recalled += 1

        logger.info(
            "scene_recalled",
            scene_id=scene_id,
            fixtures_updated=success_count,
            fade_duration=fade_duration,
        )

        return success_count > 0

    async def get_scene(self, scene_id: int) -> Optional[dict]:
        """
        Get scene information

        Args:
            scene_id: Scene ID

        Returns:
            Dictionary with scene info, or None if not found
        """
        try:
            async with get_db_session() as session:
                scene = await session.get(Scene, scene_id)

                if not scene:
                    return None

                return {
                    "id": scene.id,
                    "name": scene.name,
                    "scope_group_id": scene.scope_group_id,
                    "fixture_count": len(scene.values),
                }

        except Exception as e:
            logger.error(
                "get_scene_failed",
                scene_id=scene_id,
                error=str(e),
                exc_info=True,
            )
            return None

    async def list_scenes(
        self,
        scope_group_id: Optional[int] = None
    ) -> List[dict]:
        """
        List all scenes, optionally filtered by scope

        Args:
            scope_group_id: Optional group ID to filter by

        Returns:
            List of scene info dictionaries
        """
        try:
            async with get_db_session() as session:
                from sqlalchemy import select

                query = select(Scene)
                if scope_group_id is not None:
                    query = query.where(Scene.scope_group_id == scope_group_id)

                result = await session.execute(query)
                scenes = result.scalars().all()

                return [
                    {
                        "id": scene.id,
                        "name": scene.name,
                        "scope_group_id": scene.scope_group_id,
                        "fixture_count": len(scene.values),
                    }
                    for scene in scenes
                ]

        except Exception as e:
            logger.error(
                "list_scenes_failed",
                error=str(e),
                exc_info=True,
            )
            return []

    async def delete_scene(self, scene_id: int) -> bool:
        """
        Delete a scene

        Args:
            scene_id: Scene ID to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            async with get_db_session() as session:
                scene = await session.get(Scene, scene_id)

                if not scene:
                    logger.warning("scene_not_found", scene_id=scene_id)
                    return False

                await session.delete(scene)
                await session.commit()

                # Remove from cache
                if scene_id in self.scenes:
                    del self.scenes[scene_id]

                logger.info("scene_deleted", scene_id=scene_id)
                return True

        except Exception as e:
            logger.error(
                "scene_delete_failed",
                scene_id=scene_id,
                error=str(e),
                exc_info=True,
            )
            return False

    def get_statistics(self) -> dict:
        """
        Get engine statistics

        Returns:
            Dictionary with statistics
        """
        return {
            "scenes_cached": len(self.scenes),
            "scenes_recalled": self.scenes_recalled,
            "scenes_captured": self.scenes_captured,
            "cache_hits": self.cache_hits,
        }

    def clear_cache(self) -> None:
        """Clear scene cache"""
        count = len(self.scenes)
        self.scenes.clear()
        logger.info("scene_cache_cleared", scenes_cleared=count)
