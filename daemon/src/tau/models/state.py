"""
State Models - Runtime state persistence
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    Integer,
    Boolean,
    CheckConstraint,
    ForeignKey,
    String,
    TIMESTAMP,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

from tau.database import Base


class FixtureState(Base):
    """
    Fixture State - Current runtime state of a fixture

    Stores the current brightness, CCT, and on/off state of each fixture.
    This is the source of truth for system recovery after restart.
    """

    __tablename__ = "fixture_state"

    # Primary Key (one-to-one with fixtures)
    fixture_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("fixtures.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Current State
    current_brightness: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        server_default="0",
    )
    current_cct: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        server_default="2700",
    )
    is_on: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        server_default="false",
    )

    # Override State (for bypassing group/circadian control)
    override_active: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        server_default="false",
    )
    override_expires_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        nullable=True,
    )
    override_source: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )

    # Timestamps
    last_updated: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        server_default=func.current_timestamp(),
    )

    # Relationships
    fixture: Mapped["Fixture"] = relationship(
        "Fixture",
        back_populates="state",
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "current_brightness BETWEEN 0 AND 1000",
            name="fixture_state_current_brightness_check",
        ),
    )

    def __repr__(self) -> str:
        override = f", override={self.override_source}" if self.override_active else ""
        return (
            f"<FixtureState(fixture={self.fixture_id}, "
            f"on={self.is_on}, brightness={self.current_brightness}, cct={self.current_cct}{override})>"
        )


class GroupState(Base):
    """
    Group State - Current runtime state of a group

    Tracks circadian suspension status and the last activated scene for a group.
    """

    __tablename__ = "group_state"

    # Primary Key (one-to-one with groups)
    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Circadian Suspension
    circadian_suspended: Mapped[Optional[bool]] = mapped_column(
        Boolean,
        nullable=True,
        server_default="false",
    )
    circadian_suspended_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP,
        nullable=True,
    )

    # Last Active Scene
    last_active_scene_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("scenes.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    group: Mapped["Group"] = relationship(
        "Group",
        back_populates="state",
    )

    last_active_scene: Mapped[Optional["Scene"]] = relationship(
        "Scene",
        back_populates="group_states",
    )

    def __repr__(self) -> str:
        suspended = "suspended" if self.circadian_suspended else "active"
        return f"<GroupState(group={self.group_id}, circadian={suspended})>"
