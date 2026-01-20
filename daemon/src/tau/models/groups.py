"""
Group Models - Logical grouping of fixtures with hierarchy support
"""
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    CheckConstraint,
    ForeignKey,
    TIMESTAMP,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

from tau.database import Base


class Group(Base):
    """
    Group - Logical collection of fixtures

    Groups can contain fixtures and other groups (nesting up to 4 levels).
    Groups can have circadian automation enabled.
    """

    __tablename__ = "groups"

    # Primary Key
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Identification
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # System flag (for built-in groups like "All Fixtures")
    is_system: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True, server_default="false"
    )

    # Circadian Configuration
    circadian_enabled: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True, server_default="false"
    )
    circadian_profile_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("circadian_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Default Settings (used when switch turns group on)
    default_max_brightness: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, server_default="1000"
    )
    default_cct_kelvin: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )

    # Dim-to-Warm Configuration
    dtw_ignore: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True, server_default="false"
    )
    dtw_min_cct_override: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    dtw_max_cct_override: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )

    # Display order for UI sorting
    display_order: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        server_default=func.current_timestamp(),
    )

    # Relationships

    # Circadian profile
    circadian_profile: Mapped[Optional["CircadianProfile"]] = relationship(
        "CircadianProfile",
        back_populates="groups",
    )

    # Fixture memberships (many-to-many through GroupFixture)
    fixture_memberships: Mapped[List["GroupFixture"]] = relationship(
        "GroupFixture",
        back_populates="group",
        foreign_keys="GroupFixture.group_id",
        cascade="all, delete-orphan",
    )

    # Parent groups (groups that contain this group)
    parent_memberships: Mapped[List["GroupHierarchy"]] = relationship(
        "GroupHierarchy",
        back_populates="child_group",
        foreign_keys="GroupHierarchy.child_group_id",
        cascade="all, delete-orphan",
    )

    # Child groups (groups contained by this group)
    child_memberships: Mapped[List["GroupHierarchy"]] = relationship(
        "GroupHierarchy",
        back_populates="parent_group",
        foreign_keys="GroupHierarchy.parent_group_id",
        cascade="all, delete-orphan",
    )

    # State relationship (one-to-one)
    state: Mapped[Optional["GroupState"]] = relationship(
        "GroupState",
        back_populates="group",
        uselist=False,
        cascade="all, delete-orphan",
    )

    # Scenes scoped to this group
    scoped_scenes: Mapped[List["Scene"]] = relationship(
        "Scene",
        back_populates="scope_group",
        cascade="all, delete-orphan",
    )

    # Switches targeting this group
    switches: Mapped[List["Switch"]] = relationship(
        "Switch",
        back_populates="target_group",
        foreign_keys="Switch.target_group_id",
    )

    def __repr__(self) -> str:
        system = ", system" if self.is_system else ""
        return f"<Group(id={self.id}, name={self.name}, circadian={self.circadian_enabled}{system})>"


class GroupFixture(Base):
    """
    GroupFixture - Many-to-many relationship between groups and fixtures

    Links fixtures to groups, allowing fixtures to be members of multiple groups.
    """

    __tablename__ = "group_fixtures"

    # Composite Primary Key
    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    fixture_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("fixtures.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Relationships
    group: Mapped[Group] = relationship(
        "Group",
        back_populates="fixture_memberships",
    )

    fixture: Mapped["Fixture"] = relationship(
        "Fixture",
        back_populates="group_memberships",
    )

    def __repr__(self) -> str:
        return f"<GroupFixture(group_id={self.group_id}, fixture_id={self.fixture_id})>"


class GroupHierarchy(Base):
    """
    GroupHierarchy - Hierarchical relationship between groups

    Enables group nesting (up to 4 levels deep) by linking parent and child groups.
    """

    __tablename__ = "group_hierarchy"

    # Composite Primary Key
    parent_group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    child_group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Relationships
    parent_group: Mapped[Group] = relationship(
        "Group",
        back_populates="child_memberships",
        foreign_keys=[parent_group_id],
    )

    child_group: Mapped[Group] = relationship(
        "Group",
        back_populates="parent_memberships",
        foreign_keys=[child_group_id],
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "parent_group_id != child_group_id",
            name="group_hierarchy_parent_child_check",
        ),
    )

    def __repr__(self) -> str:
        return f"<GroupHierarchy(parent={self.parent_group_id}, child={self.child_group_id})>"
