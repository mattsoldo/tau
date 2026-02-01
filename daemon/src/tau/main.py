"""
Tau Lighting Control Daemon - Main Entry Point
"""
import asyncio
import signal
import sys
from typing import Optional

import structlog
import uvicorn
from fastapi import FastAPI

from tau.config import get_settings
from tau.database import init_database, close_database
from tau.api import create_app, set_daemon_instance
from tau.logging_config import setup_logging
from tau.control import (
    EventLoop,
    Scheduler,
    StateManager,
    StatePersistence,
    ConfigLoader,
)
from tau.hardware import HardwareManager
from tau.logic import LightingController
from tau.logic.switch_discovery import SwitchDiscovery
from tau.models.system_settings_helper import get_system_setting_typed

logger = structlog.get_logger(__name__)


class TauDaemon:
    """Main daemon controller for the Tau lighting system"""

    def __init__(self):
        self.settings = get_settings()
        self.app: Optional[FastAPI] = None
        self.should_exit = False
        self.event_loop: Optional[EventLoop] = None
        self.scheduler: Optional[Scheduler] = None
        self.state_manager: Optional[StateManager] = None
        self.persistence: Optional[StatePersistence] = None
        self.config_loader: Optional[ConfigLoader] = None
        self.hardware_manager: Optional[HardwareManager] = None
        self.lighting_controller: Optional[LightingController] = None
        self.switch_discovery: Optional[SwitchDiscovery] = None

    async def startup(self):
        """Initialize all daemon components"""
        logger.info("tau_daemon_starting", version="1.7.1")

        # Initialize database
        logger.info("initializing_database")
        await init_database(self.settings.database_url)

        # Create FastAPI application
        self.app = create_app(self.settings)

        # Set global daemon instance for API access
        set_daemon_instance(self)

        # Initialize state management
        logger.info("initializing_state_management")
        self.state_manager = StateManager()
        self.persistence = StatePersistence(self.state_manager)
        self.config_loader = ConfigLoader(self.state_manager)

        # Load configuration from database
        logger.info("loading_configuration")
        await self.config_loader.load_configuration()

        # Initialize hardware interfaces (LabJack/GPIO, OLA)
        logger.info(
            "initializing_hardware",
            use_gpio=self.settings.use_gpio,
        )
        self.hardware_manager = HardwareManager(
            use_gpio=self.settings.use_gpio,
            gpio_use_pigpio=self.settings.gpio_use_pigpio,
            gpio_pull_up=self.settings.gpio_pull_up,
            gpio_input_pins=self.settings.gpio_input_pins,
            gpio_pwm_pins=self.settings.gpio_pwm_pins,
        )
        hardware_ok = await self.hardware_manager.initialize()
        if not hardware_ok:
            logger.warning(
                "hardware_initialization_failed",
                message="Hardware not available - daemon will start in software-only mode"
            )

        # Initialize lighting controller
        logger.info("initializing_lighting_controller")

        # Load dim_speed from system settings (default 2000ms if not found)
        dim_speed_ms = await get_system_setting_typed(
            key="dim_speed_ms",
            value_type="int",
            default_value=2000
        )
        logger.info("dim_speed_loaded", dim_speed_ms=dim_speed_ms)

        # Load tap_window_ms from system settings (default 500ms, range 200-900ms per PRD)
        tap_window_ms = await get_system_setting_typed(
            key="tap_window_ms",
            value_type="int",
            default_value=500
        )
        # Clamp to valid range
        tap_window_ms = max(200, min(900, tap_window_ms))
        logger.info("tap_window_loaded", tap_window_ms=tap_window_ms)

        dmx_dedupe_enabled = await get_system_setting_typed(
            key="dmx_dedupe_enabled",
            value_type="bool",
            default_value=self.settings.dmx_dedupe_enabled
        )
        dmx_dedupe_ttl_seconds = await get_system_setting_typed(
            key="dmx_dedupe_ttl_seconds",
            value_type="float",
            default_value=self.settings.dmx_dedupe_ttl_seconds
        )
        logger.info(
            "dmx_dedupe_settings_loaded",
            enabled=dmx_dedupe_enabled,
            ttl_seconds=dmx_dedupe_ttl_seconds
        )

        self.lighting_controller = LightingController(
            self.state_manager,
            self.hardware_manager,
            dim_speed_ms=dim_speed_ms,
            tap_window_ms=tap_window_ms,
            dmx_dedupe_enabled=dmx_dedupe_enabled,
            dmx_dedupe_ttl_seconds=dmx_dedupe_ttl_seconds
        )
        controller_ok = await self.lighting_controller.initialize()
        if not controller_ok:
            logger.warning(
                "lighting_controller_initialization_failed",
                message="Lighting controller running in degraded mode without hardware"
            )

        # Initialize switch auto-discovery
        logger.info("initializing_switch_discovery")
        self.switch_discovery = SwitchDiscovery(
            self.hardware_manager,
            change_threshold=3,
            time_window=10.0
        )
        await self.switch_discovery.load_configured_switches()

        # Create scheduler for periodic tasks
        self.scheduler = Scheduler()

        # Schedule state persistence every 5 seconds
        self.scheduler.schedule(
            name="state_persistence",
            callback=self.persistence.save_state,
            interval_seconds=5.0,
        )

        # Schedule switch discovery scan every 0.5 seconds
        self.scheduler.schedule(
            name="switch_discovery",
            callback=self._run_switch_discovery,
            interval_seconds=0.5,
        )

        # Create and configure event loop
        self.event_loop = EventLoop(frequency_hz=self.settings.control_loop_hz)

        # Register scheduler as a callback (runs every loop iteration)
        self.event_loop.register_callback(self.scheduler.tick)

        # Register lighting controller (runs every loop iteration)
        self.event_loop.register_callback(self.lighting_controller.process_control_loop)

        # Start control loop
        logger.info("starting_control_loop", frequency_hz=self.settings.control_loop_hz)
        self.event_loop.start()

        logger.info("tau_daemon_ready", port=self.settings.daemon_port)

    async def _run_switch_discovery(self) -> None:
        """Run switch discovery scan and emit WebSocket events for new switches"""
        if not self.switch_discovery:
            return

        try:
            detected = await self.switch_discovery.scan_for_activity()
            if detected:
                # Emit WebSocket notification
                from tau.api.websocket import connection_manager
                await connection_manager.broadcast({
                    "type": "switch_discovered",
                    "pin": detected["pin"],
                    "is_digital": detected["is_digital"],
                    "change_count": detected["change_count"],
                    "timestamp": detected.get("time_span", 0)
                })

                logger.info("switch_discovery_notification_sent",
                           pin=detected["pin"],
                           is_digital=detected["is_digital"])

        except Exception as e:
            logger.error("switch_discovery_error", error=str(e))

    async def shutdown(self):
        """Gracefully shutdown all components"""
        logger.info("tau_daemon_shutting_down")

        # Stop control loop
        if self.event_loop:
            await self.event_loop.stop()

        # Close hardware connections
        if self.hardware_manager:
            await self.hardware_manager.shutdown()

        # Close database connections
        await close_database()

        logger.info("tau_daemon_stopped")

    def handle_signal(self, signum, frame):
        """Handle shutdown signals"""
        logger.info("signal_received", signal=signal.Signals(signum).name)
        self.should_exit = True


async def main_async():
    """Async main function"""
    daemon = TauDaemon()

    # Register signal handlers
    signal.signal(signal.SIGINT, daemon.handle_signal)
    signal.signal(signal.SIGTERM, daemon.handle_signal)

    try:
        # Start daemon
        await daemon.startup()

        # Run FastAPI with uvicorn
        config = uvicorn.Config(
            daemon.app,
            host=daemon.settings.daemon_host,
            port=daemon.settings.daemon_port,
            log_level=daemon.settings.log_level.lower(),
            access_log=True,
        )
        server = uvicorn.Server(config)
        await server.serve()

    except Exception as e:
        logger.error("daemon_error", error=str(e), exc_info=True)
        sys.exit(1)
    finally:
        await daemon.shutdown()


def main():
    """Entry point for the daemon"""
    # Initialize logging first
    settings = get_settings()
    setup_logging(
        log_level=settings.log_level,
        json_logs=(settings.log_level != "DEBUG"),  # Use JSON in production
    )

    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("interrupted_by_user")
        sys.exit(0)


if __name__ == "__main__":
    main()
