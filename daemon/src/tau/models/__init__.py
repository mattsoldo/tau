"""
Tau Lighting Control - SQLAlchemy ORM Models

This package contains all database models for the Tau lighting control system.
"""

from tau.database import Base

# Import all models to ensure they're registered with Base.metadata
from tau.models.fixtures import FixtureModel, Fixture
from tau.models.switches import SwitchModel, Switch
from tau.models.groups import Group, GroupFixture, GroupHierarchy
from tau.models.circadian import CircadianProfile
from tau.models.scenes import Scene, SceneValue
from tau.models.state import FixtureState, GroupState
from tau.models.update_log import UpdateLog, UpdateStatus
from tau.models.system_settings import SystemSetting
from tau.models.software_update import (
    Installation,
    VersionHistory,
    AvailableRelease,
    UpdateCheck,
    UpdateConfig,
    DEFAULT_UPDATE_CONFIG,
)

__all__ = [
    "Base",
    "FixtureModel",
    "Fixture",
    "SwitchModel",
    "Switch",
    "Group",
    "GroupFixture",
    "GroupHierarchy",
    "CircadianProfile",
    "Scene",
    "SceneValue",
    "FixtureState",
    "GroupState",
    "UpdateLog",
    "UpdateStatus",
    "SystemSetting",
    "Installation",
    "VersionHistory",
    "AvailableRelease",
    "UpdateCheck",
    "UpdateConfig",
    "DEFAULT_UPDATE_CONFIG",
]
