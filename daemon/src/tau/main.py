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
from tau.database import init_database
from tau.api import create_app
from tau.logging_config import setup_logging

logger = structlog.get_logger(__name__)


class TauDaemon:
    """Main daemon controller for the Tau lighting system"""

    def __init__(self):
        self.settings = get_settings()
        self.app: Optional[FastAPI] = None
        self.should_exit = False

    async def startup(self):
        """Initialize all daemon components"""
        logger.info("tau_daemon_starting", version="0.1.0")

        # Initialize database
        logger.info("initializing_database")
        await init_database(self.settings.database_url)

        # Create FastAPI application
        self.app = create_app(self.settings)

        # Initialize hardware interfaces (LabJack, OLA)
        logger.info("initializing_hardware", mock_mode=self.settings.labjack_mock)
        # TODO: Initialize hardware in next phase

        # Start control loop
        logger.info("starting_control_loop")
        # TODO: Start control loop in next phase

        logger.info("tau_daemon_ready", port=self.settings.daemon_port)

    async def shutdown(self):
        """Gracefully shutdown all components"""
        logger.info("tau_daemon_shutting_down")

        # Stop control loop
        # TODO: Stop control loop

        # Close hardware connections
        # TODO: Close hardware connections

        # Close database connections
        # TODO: Close database connections

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
            host="0.0.0.0",
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
