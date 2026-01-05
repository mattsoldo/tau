"""
Override Model - Temporary manual settings that supersede automatic values

Overrides allow temporary manual control of CCT and other properties that
would otherwise be automatically calculated (e.g., by DTW or circadian).
Overrides expire based on timeout or power-off conditions.
"""
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import (
    Integer,
    String,
    Text,
    TIMESTAMP,
    Index,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from tau.database import Base


class TargetType(str, Enum):
    """Type of target for an override."""
    FIXTURE = "fixture"
    GROUP = "group"


class OverrideType(str, Enum):
    """Type of override."""
    DTW_CCT = "dtw_cct"  # Manual CCT change when DTW active
    FIXTURE_GROUP = "fixture_group"  # Individual fixture control when in group
    SCENE = "scene"  # Scene recall


class OverrideSource(str, Enum):
    """Source of an override."""
    USER = "user"
    API = "api"
    SCENE = "scene"
    SCHEDULE = "schedule"


class Override(Base):
    """
    Override - Temporary manual setting that supersedes automatic values

    Overrides are created when a user manually adjusts a value that would
    otherwise be automatically calculated (e.g., manually setting CCT
    when DTW is active). They expire after a timeout or when the target
    is powered off.
    """

    __tablename__ = "overrides"

    # Primary Key
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Target identification
    target_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    target_id: Mapped[int] = mapped_column(
        Integer, nullable=False
    )

    # Override details
    override_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    property: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    value: Mapped[str] = mapped_column(
        Text, nullable=False
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        server_default=func.current_timestamp(),
    )
    expires_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
    )

    # Source tracking
    source: Mapped[str] = mapped_column(
        String(20), nullable=False
    )

    # Indexes and constraints are defined in the migration

    def __repr__(self) -> str:
        return (
            f"<Override(id={self.id}, "
            f"target={self.target_type}:{self.target_id}, "
            f"type={self.override_type}, "
            f"property={self.property})>"
        )

    def get_typed_value(self):
        """
        Get the override value as the appropriate Python type.

        Currently supports: int (for CCT), float (for brightness)
        """
        if self.property == "cct":
            return int(self.value)
        elif self.property == "brightness":
            return float(self.value)
        return self.value

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """
        Check if this override has expired.

        Args:
            now: Current time (defaults to datetime.now())

        Returns:
            True if expired, False otherwise
        """
        if now is None:
            now = datetime.now()
        return now >= self.expires_at
