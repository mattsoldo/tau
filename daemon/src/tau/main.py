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

    async def startup(self):
        """Initialize all daemon components"""
        logger.info("tau_daemon_starting", version="0.1.0")

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
            logger.error("hardware_initialization_failed")
            raise RuntimeError("Failed to initialize hardware")

        # Initialize lighting controller
        logger.info("initializing_lighting_controller")
        self.lighting_controller = LightingController(
            self.state_manager,
            self.hardware_manager,
            dim_speed_ms=self.settings.retractive_dim_speed_ms
        )
        controller_ok = await self.lighting_controller.initialize()
        if not controller_ok:
            logger.error("lighting_controller_initialization_failed")
            raise RuntimeError("Failed to initialize lighting controller")

        # Create scheduler for periodic tasks
        self.scheduler = Scheduler()

        # Schedule state persistence every 5 seconds
        self.scheduler.schedule(
            name="state_persistence",
            callback=self.persistence.save_state,
            interval_seconds=5.0,
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
