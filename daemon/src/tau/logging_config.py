"""
Tau Daemon Logging Configuration

Uses structlog for structured logging with JSON output in production
and colored console output in development.
"""
import logging
import sys
from typing import Any

import structlog
from pythonjsonlogger import jsonlogger


def setup_logging(log_level: str = "INFO", json_logs: bool = False) -> None:
    """
    Configure application logging

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_logs: If True, output JSON formatted logs. If False, use colored console output.
    """
    # Convert log level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
    )

    # Configure structlog processors
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.ExtraAdder(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_logs:
        # Production: JSON formatting
        processors.extend(
            [
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ]
        )
    else:
        # Development: Colored console output
        processors.extend(
            [
                structlog.processors.ExceptionRenderer(),
                structlog.dev.ConsoleRenderer(colors=True),
            ]
        )

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


class StructlogFormatter(logging.Formatter):
    """Custom formatter that outputs JSON using structlog"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.json_renderer = structlog.processors.JSONRenderer()

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        event_dict = {
            "event": record.getMessage(),
            "level": record.levelname.lower(),
            "timestamp": self.formatTime(record, self.datefmt),
            "logger": record.name,
        }

        if record.exc_info:
            event_dict["exc_info"] = self.formatException(record.exc_info)

        return self.json_renderer(None, None, event_dict)


def get_file_handler(
    log_file: str, log_level: str = "INFO", json_format: bool = True
) -> logging.FileHandler:
    """
    Create a file handler for logging to disk

    Args:
        log_file: Path to log file
        log_level: Minimum log level
        json_format: If True, use JSON formatting

    Returns:
        Configured file handler
    """
    handler = logging.FileHandler(log_file)
    handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    if json_format:
        formatter = jsonlogger.JsonFormatter(
            "%(timestamp)s %(level)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    handler.setFormatter(formatter)
    return handler
