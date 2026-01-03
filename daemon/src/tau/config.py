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

    # Transition Configuration
    # Times are for the full range - actual time scales proportionally to change amount
    transition_brightness_seconds: float = Field(
        default=0.5,
        ge=0.0,
        le=60.0,
        description="Time in seconds for full brightness transition (0% to 100%)"
    )
    transition_cct_seconds: float = Field(
        default=0.5,
        ge=0.0,
        le=60.0,
        description="Time in seconds for full CCT range transition"
    )
    transition_default_easing: str = Field(
        default="ease_in_out",
        description="Default easing function (linear, ease_in, ease_out, ease_in_out, ease_in_cubic, ease_out_cubic, ease_in_out_cubic)"
    )

    # API Configuration
    api_title: str = Field(default="Tau Lighting Control API", description="API title")
    api_version: str = Field(default="0.1.0", description="API version")
    api_docs_enabled: bool = Field(default=True, description="Enable API documentation")

    # CORS Configuration
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="Allowed CORS origins (use ['*'] for development only)"
    )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
