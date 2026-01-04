"""
Update Tracking Models - Software update history and status
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    CheckConstraint,
    TIMESTAMP,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from tau.database import Base


class UpdateLog(Base):
    """
    Update Log - Historical record of software updates

    Tracks each update attempt including versions, status, errors, and changelog.
    """

    __tablename__ = "update_log"

    # Primary Key
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Version Information
    version_before: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    version_after: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Update Status
    status: Mapped[str] = mapped_column(String(50), nullable=False)

    # Timestamps
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP,
        nullable=False,
        server_default=func.current_timestamp(),
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)

    # Error and Change Information
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changelog: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Update Type
    update_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "status IN ('checking', 'available', 'in_progress', 'completed', 'failed')",
            name="update_log_status_check",
        ),
        CheckConstraint(
            "update_type IN ('manual', 'automatic') OR update_type IS NULL",
            name="update_log_update_type_check",
        ),
    )

    def __repr__(self) -> str:
        return f"<UpdateLog(id={self.id}, status={self.status}, version_before={self.version_before}, version_after={self.version_after})>"


class UpdateStatus(Base):
    """
    Update Status - Current update state (single row table)

    Maintains the current update status, available version, and last check time.
    This table always contains exactly one row (id=1).
    """

    __tablename__ = "update_status"

    # Primary Key (always 1)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Update State
    is_updating: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    update_available: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    # Version Information
    current_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    available_version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Last Check Timestamp
    last_check_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)

    # Constraints
    __table_args__ = (
        CheckConstraint("id = 1", name="update_status_single_row_check"),
    )

    def __repr__(self) -> str:
        return f"<UpdateStatus(current_version={self.current_version}, update_available={self.update_available}, is_updating={self.is_updating})>"
