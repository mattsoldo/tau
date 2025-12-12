"""
Tau Daemon Configuration Management
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database Configuration
    database_url: PostgresDsn = Field(
        default="postgresql://tau_daemon:tau_dev_password@localhost:5432/tau_lighting",
        description="PostgreSQL database connection URL",
    )

    # Daemon Configuration
    daemon_port: int = Field(default=8000, description="HTTP API port")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logging level"
    )

    # Hardware Configuration
    labjack_mock: bool = Field(
        default=True, description="Use mock LabJack interface (no real hardware)"
    )
    ola_mock: bool = Field(default=True, description="Use mock OLA interface (no real hardware)")

    # Control Loop Configuration
    control_loop_hz: int = Field(default=30, description="Control loop frequency in Hz")
    dmx_update_hz: int = Field(default=44, description="DMX output update frequency in Hz")

    # State Persistence
    state_persist_interval_seconds: int = Field(
        default=5, description="How often to persist state to database"
    )

    # Circadian Configuration
    circadian_update_interval_seconds: int = Field(
        default=60, description="How often to recalculate circadian values"
    )

    # Switch Input Configuration
    switch_poll_hz: int = Field(default=100, description="Switch input polling frequency in Hz")
    switch_debounce_ms: int = Field(default=50, description="Default switch debounce time in ms")

    # API Configuration
    api_title: str = Field(default="Tau Lighting Control API", description="API title")
    api_version: str = Field(default="0.1.0", description="API version")
    api_docs_enabled: bool = Field(default=True, description="Enable API documentation")


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
