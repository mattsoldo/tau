"""
System Settings Model - Global configuration values stored in database
"""
from typing import Optional

from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from tau.database import Base


class SystemSetting(Base):
    """
    SystemSetting - Key-value storage for global system configuration

    This table stores system-wide configuration values that can be modified
    at runtime without restarting the daemon.
    """

    __tablename__ = "system_settings"

    # Primary Key
    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Setting Key (unique identifier)
    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)

    # Setting Value (stored as string, converted by application)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    # Human-readable description
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Data type hint for validation/conversion (e.g., 'int', 'float', 'str', 'bool')
    value_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="str"
    )

    def __repr__(self):
        return f"<SystemSetting(key='{self.key}', value='{self.value}', type='{self.value_type}')>"

    def get_typed_value(self):
        """
        Convert the stored string value to its proper type

        Returns:
            The value converted to the appropriate Python type
        """
        if self.value_type == "int":
            return int(self.value)
        elif self.value_type == "float":
            return float(self.value)
        elif self.value_type == "bool":
            return self.value.lower() in ("true", "1", "yes")
        else:
            return self.value
