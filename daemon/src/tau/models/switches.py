"""
Switch Models - Physical input devices (switches, dimmers, rotary encoders)
"""
from typing import Optional, List

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    CheckConstraint,
    ForeignKey,
    UniqueConstraint,
    Text,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from tau.database import Base


class SwitchModel(Base):
    """
    Switch Model - Manufacturer specifications for input devices

    Defines the characteristics of a switch/dimmer type, including
    input type, debouncing, and hardware requirements.
    """

    __tablename__ = "switch_models"

    # Primary Key
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Identification
    manufacturer: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)

    # Input Characteristics
    input_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Hardware Configuration
    debounce_ms: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, server_default="500"
    )
    dimming_curve: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, server_default="logarithmic"
    )

    # Pin Requirements
    requires_digital_pin: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True, server_default="true"
    )
    requires_analog_pin: Mapped[Optional[bool]] = mapped_column(
        Boolean, nullable=True, server_default="false"
    )

    # Relationships
    switches: Mapped[List["Switch"]] = relationship(
        "Switch",
        back_populates="switch_model",
        cascade="all, delete-orphan",
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "input_type IN ('retractive', 'rotary_abs', 'paddle_composite', 'switch_simple')",
            name="switch_models_input_type_check",
        ),
        CheckConstraint(
            "dimming_curve IN ('linear', 'logarithmic')",
            name="switch_models_dimming_curve_check",
        ),
        UniqueConstraint("manufacturer", "model", name="switch_models_manufacturer_model_key"),
    )

    def __repr__(self) -> str:
        return f"<SwitchModel(id={self.id}, manufacturer={self.manufacturer}, model={self.model})>"


class Switch(Base):
    """
    Switch - A physical input device instance

    Represents an actual switch/dimmer installed in the system with its
    hardware pin assignments and target (fixture or group).
    """

    __tablename__ = "switches"

    # Primary Key
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Identification
    name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Model Reference
    switch_model_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("switch_models.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # Hardware Mapping (LabJack pins)
    labjack_digital_pin: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    labjack_analog_pin: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Hardware Configuration
    switch_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="normally-closed"
    )  # 'normally-open' or 'normally-closed'
    invert_reading: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false"
    )  # Whether to invert the digital reading in software

    # Polymorphic Target (either group OR fixture, not both)
    target_group_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("groups.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_fixture_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("fixtures.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Optional UI Photo
    photo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Optional double-tap scene recall
    double_tap_scene_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("scenes.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    switch_model: Mapped[SwitchModel] = relationship(
        "SwitchModel",
        back_populates="switches",
    )

    target_group: Mapped[Optional["Group"]] = relationship(
        "Group",
        back_populates="switches",
        foreign_keys=[target_group_id],
    )

    target_fixture: Mapped[Optional["Fixture"]] = relationship(
        "Fixture",
        back_populates="switches",
        foreign_keys=[target_fixture_id],
    )

    double_tap_scene: Mapped[Optional["Scene"]] = relationship(
        "Scene",
        foreign_keys=[double_tap_scene_id],
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "(target_group_id IS NOT NULL AND target_fixture_id IS NULL) OR "
            "(target_group_id IS NULL AND target_fixture_id IS NOT NULL)",
            name="one_target_only",
        ),
    )

    def __repr__(self) -> str:
        target = f"group={self.target_group_id}" if self.target_group_id else f"fixture={self.target_fixture_id}"
        return f"<Switch(id={self.id}, name={self.name}, {target})>"
