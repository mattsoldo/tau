"""
Tau Daemon Configuration Management
"""
from functools import lru_cache
from typing import Literal, Optional

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
    daemon_host: str = Field(
        default="0.0.0.0",
        description="Host to bind the API server (0.0.0.0 for network access)"
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logging level"
    )

    # Hardware Configuration
    labjack_mock: bool = Field(
        default=True, description="Use mock LabJack interface (no real hardware)"
    )
    ola_mock: bool = Field(default=True, description="Use mock OLA interface (no real hardware)")

    # Raspberry Pi GPIO Configuration
    use_gpio: bool = Field(
        default=False,
        description="Use Raspberry Pi GPIO instead of LabJack for switch inputs"
    )
    gpio_use_pigpio: bool = Field(
        default=True,
        description="Use pigpio for hardware PWM (requires pigpiod running)"
    )
    gpio_pull_up: bool = Field(
        default=True,
        description="Enable internal pull-up resistors on GPIO inputs"
    )
    # GPIO pin mappings (comma-separated channel:pin pairs, e.g., "0:17,1:27,2:22")
    gpio_input_pins: Optional[str] = Field(
        default=None,
        description="Custom GPIO input pin mapping (format: channel:pin,channel:pin)"
    )
    gpio_pwm_pins: Optional[str] = Field(
        default=None,
        description="Custom GPIO PWM pin mapping (format: channel:pin,channel:pin)"
    )

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
    cors_allow_all: bool = Field(
        default=False,
        description="Allow CORS from any origin (useful for Raspberry Pi on local network)"
    )


def get_effective_cors_origins(settings: "Settings") -> list[str]:
    """
    Get the effective CORS origins based on settings.

    If cors_allow_all is True, returns ['*'] to allow any origin.
    Otherwise returns the configured cors_origins list.
    """
    if settings.cors_allow_all:
        return ["*"]
    return settings.cors_origins


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
