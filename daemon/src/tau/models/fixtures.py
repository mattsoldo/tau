"""
Fixture Models - Physical lighting fixtures and their specifications
"""
from datetime import datetime
from typing import Optional, List

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Float,
    CheckConstraint,
    ForeignKey,
    UniqueConstraint,
    TIMESTAMP,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

from tau.database import Base


class FixtureModel(Base):
    """
    Fixture Model - Manufacturer specifications for light fixtures

    Defines the characteristics and capabilities of a fixture type,
    including DMX footprint, CCT range, and mixing algorithm.
    """

    __tablename__ = "fixture_models"

    # Primary Key
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Identification
    manufacturer: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Fixture Type
    type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="simple_dimmable",
    )

    # DMX Configuration
    dmx_footprint: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")

    # Color Temperature Limits (Kelvin)
    cct_min_kelvin: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, server_default="1800"
    )
    cct_max_kelvin: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, server_default="4000"
    )

    # Planckian Locus Color Mixing Parameters (for tunable_white fixtures)
    # CIE 1931 xy chromaticity coordinates for warm LED
    warm_xy_x: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    warm_xy_y: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # CIE 1931 xy chromaticity coordinates for cool LED
    cool_xy_x: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cool_xy_y: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Luminous flux at 100% for each channel
    warm_lumens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cool_lumens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # PWM-to-light gamma correction (default 2.2)
    gamma: Mapped[Optional[float]] = mapped_column(Float, nullable=True, server_default="2.2")

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        server_default=func.current_timestamp(),
    )

    # Relationships
    fixtures: Mapped[List["Fixture"]] = relationship(
        "Fixture",
        back_populates="fixture_model",
        cascade="all, delete-orphan",
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "type IN ('simple_dimmable', 'tunable_white', 'dim_to_warm', 'non_dimmable', 'other')",
            name="fixture_models_type_check",
        ),
        UniqueConstraint("manufacturer", "model", name="fixture_models_manufacturer_model_key"),
    )

    def __repr__(self) -> str:
        return f"<FixtureModel(id={self.id}, manufacturer={self.manufacturer}, model={self.model})>"


class Fixture(Base):
    """
    Fixture - A physical lighting fixture instance

    Represents an actual fixture installed in the system with its
    DMX addressing and association to a fixture model.
    """

    __tablename__ = "fixtures"

    # Primary Key
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Identification
    name: Mapped[str] = mapped_column(String(100), nullable=False)

    # Model Reference
    fixture_model_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("fixture_models.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # DMX Configuration
    dmx_channel_start: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    secondary_dmx_channel: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, unique=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        server_default=func.current_timestamp(),
    )

    # Relationships
    fixture_model: Mapped[FixtureModel] = relationship(
        "FixtureModel",
        back_populates="fixtures",
    )

    # State relationship (one-to-one)
    state: Mapped[Optional["FixtureState"]] = relationship(
        "FixtureState",
        back_populates="fixture",
        uselist=False,
    )

    # Group memberships (many-to-many)
    group_memberships: Mapped[List["GroupFixture"]] = relationship(
        "GroupFixture",
        back_populates="fixture",
        cascade="all, delete-orphan",
    )

    # Scene values
    scene_values: Mapped[List["SceneValue"]] = relationship(
        "SceneValue",
        back_populates="fixture",
        cascade="all, delete-orphan",
    )

    # Switch targets
    switches: Mapped[List["Switch"]] = relationship(
        "Switch",
        back_populates="target_fixture",
        foreign_keys="Switch.target_fixture_id",
    )

    def __repr__(self) -> str:
        return f"<Fixture(id={self.id}, name={self.name}, dmx_channel={self.dmx_channel_start})>"
