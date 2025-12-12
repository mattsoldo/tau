"""
Scene Models - Static lighting presets
"""
from typing import Optional, List

from sqlalchemy import (
    Column,
    Integer,
    String,
    CheckConstraint,
    ForeignKey,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from tau.database import Base


class Scene(Base):
    """
    Scene - A static lighting preset

    Scenes capture specific brightness and CCT values for fixtures,
    allowing quick recall of pre-configured lighting states.
    """

    __tablename__ = "scenes"

    # Primary Key
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Identification
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Optional scope to a specific group
    scope_group_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Relationships
    scope_group: Mapped[Optional["Group"]] = relationship(
        "Group",
        back_populates="scoped_scenes",
    )

    # Scene values (what fixtures should be set to)
    values: Mapped[List["SceneValue"]] = relationship(
        "SceneValue",
        back_populates="scene",
        cascade="all, delete-orphan",
    )

    # Group states that reference this scene as last active
    group_states: Mapped[List["GroupState"]] = relationship(
        "GroupState",
        back_populates="last_active_scene",
    )

    def __repr__(self) -> str:
        scope = f", scope={self.scope_group_id}" if self.scope_group_id else ""
        return f"<Scene(id={self.id}, name={self.name}{scope})>"


class SceneValue(Base):
    """
    Scene Value - Target state for a fixture within a scene

    Defines what brightness and CCT a specific fixture should have
    when the scene is activated.
    """

    __tablename__ = "scene_values"

    # Composite Primary Key
    scene_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("scenes.id", ondelete="CASCADE"),
        primary_key=True,
    )
    fixture_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("fixtures.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Target Values
    target_brightness: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    target_cct_kelvin: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    scene: Mapped[Scene] = relationship(
        "Scene",
        back_populates="values",
    )

    fixture: Mapped["Fixture"] = relationship(
        "Fixture",
        back_populates="scene_values",
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "target_brightness BETWEEN 0 AND 1000",
            name="scene_values_target_brightness_check",
        ),
    )

    def __repr__(self) -> str:
        return f"<SceneValue(scene={self.scene_id}, fixture={self.fixture_id}, brightness={self.target_brightness})>"
