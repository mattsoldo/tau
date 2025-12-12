"""
Circadian Models - Time-based lighting profiles
"""
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    CheckConstraint,
    TIMESTAMP,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

from tau.database import Base


class CircadianProfile(Base):
    """
    Circadian Profile - Time-based lighting curve

    Defines how brightness and color temperature should change throughout
    the day. Curve points are stored as JSON with interpolation between points.

    Curve Point Schema:
    {
        "time": "HH:MM",           # 24-hour format
        "brightness": 0-1000,      # Tenths of percent (800 = 80.0%)
        "cct": 1800-6500           # Color temperature in Kelvin
    }

    Example:
    [
        {"time": "06:00", "brightness": 0, "cct": 2700},
        {"time": "08:00", "brightness": 900, "cct": 4000},
        {"time": "18:00", "brightness": 900, "cct": 3000},
        {"time": "20:00", "brightness": 400, "cct": 2700},
        {"time": "23:00", "brightness": 0, "cct": 2200}
    ]
    """

    __tablename__ = "circadian_profiles"

    # Primary Key
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Identification
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Curve Definition
    curve_points: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    # Interpolation Method
    interpolation_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        server_default="linear",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        server_default=func.current_timestamp(),
    )

    # Relationships
    groups: Mapped[List["Group"]] = relationship(
        "Group",
        back_populates="circadian_profile",
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "interpolation_type IN ('linear', 'cosine', 'step')",
            name="circadian_profiles_interpolation_type_check",
        ),
    )

    def __repr__(self) -> str:
        return f"<CircadianProfile(id={self.id}, name={self.name}, type={self.interpolation_type})>"
