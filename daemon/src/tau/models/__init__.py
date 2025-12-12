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
]
