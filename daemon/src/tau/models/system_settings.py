"""
System Settings Model - Global configuration stored in database
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Integer,
    String,
    Float,
    Boolean,
    TIMESTAMP,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from tau.database import Base


class SystemSettings(Base):
    """
    System Settings - Global configuration for the lighting system

    Stores persistent settings that apply system-wide, such as
    dim-to-warm defaults and other global behaviors.

    Uses a single-row pattern with id=1 to store all settings.
    """

    __tablename__ = "system_settings"

    # Primary Key (always 1 for singleton pattern)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # Dim-to-Warm Global Settings
    # These are the system defaults; fixtures and groups can override
    dim_to_warm_max_cct_kelvin: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="3000",
        comment="Default CCT at 100% brightness (Kelvin). Lower of this or fixture max."
    )
    dim_to_warm_min_cct_kelvin: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="1800",
        comment="Default CCT at minimum brightness (Kelvin). Higher of this or fixture min."
    )
    dim_to_warm_curve_exponent: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        server_default="0.5",
        comment="Curve exponent for dim-to-warm. 0.5=square root (incandescent-like), 1.0=linear"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        server_default=func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    def __repr__(self) -> str:
        return (
            f"<SystemSettings(dim_to_warm_max={self.dim_to_warm_max_cct_kelvin}K, "
            f"dim_to_warm_min={self.dim_to_warm_min_cct_kelvin}K, "
            f"curve={self.dim_to_warm_curve_exponent})>"
        )
