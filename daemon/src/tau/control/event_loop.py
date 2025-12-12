"""
Event Loop - Main control loop for the Tau lighting system

Runs at 30 Hz and coordinates all real-time operations:
- Hardware input polling
- State updates
- DMX output
- Circadian calculations
"""
import asyncio
from datetime import datetime
from typing import Optional, Callable, List
import structlog

logger = structlog.get_logger(__name__)


class EventLoop:
    """
    Main control loop for real-time lighting control

    Runs at a fixed frequency (default 30 Hz) and executes registered
    tasks on each iteration. Handles graceful shutdown and error recovery.
    """

    def __init__(self, frequency_hz: int = 30):
        """
        Initialize the event loop

        Args:
            frequency_hz: Loop frequency in Hz (default 30)
        """
        self.frequency_hz = frequency_hz
        self.interval = 1.0 / frequency_hz
        self.running = False
        self.task: Optional[asyncio.Task] = None

        # Registered callbacks for each loop iteration
        self.callbacks: List[Callable] = []

        # Statistics
        self.iteration_count = 0
        self.total_time = 0.0
        self.min_loop_time = float('inf')
        self.max_loop_time = 0.0

        logger.info(
            "event_loop_initialized",
            frequency_hz=frequency_hz,
            interval_ms=self.interval * 1000,
        )

    def register_callback(self, callback: Callable) -> None:
        """
        Register a callback to be called on each loop iteration

        Args:
            callback: Async function to call each iteration
        """
        if asyncio.iscoroutinefunction(callback):
            self.callbacks.append(callback)
            logger.debug("callback_registered", callback=callback.__name__)
        else:
            logger.error("invalid_callback", error="Callback must be async function")

    async def _loop_iteration(self) -> None:
        """Execute one iteration of the control loop"""
        start_time = datetime.now()

        try:
            # Execute all registered callbacks
            for callback in self.callbacks:
                try:
                    await callback()
                except Exception as e:
                    logger.error(
                        "callback_error",
                        callback=callback.__name__,
                        error=str(e),
                        exc_info=True,
                    )

        except Exception as e:
            logger.error("loop_iteration_error", error=str(e), exc_info=True)

        # Update statistics
        loop_time = (datetime.now() - start_time).total_seconds()
        self.iteration_count += 1
        self.total_time += loop_time
        self.min_loop_time = min(self.min_loop_time, loop_time)
        self.max_loop_time = max(self.max_loop_time, loop_time)

        # Warn if loop is taking too long
        if loop_time > self.interval:
            logger.warning(
                "slow_loop_iteration",
                loop_time_ms=loop_time * 1000,
                target_ms=self.interval * 1000,
                overrun_ms=(loop_time - self.interval) * 1000,
            )

    async def run(self) -> None:
        """
        Run the event loop

        This method runs indefinitely until stop() is called.
        It maintains a consistent loop frequency using precise timing.
        """
        self.running = True
        logger.info("event_loop_started", frequency_hz=self.frequency_hz)

        try:
            while self.running:
                loop_start = asyncio.get_event_loop().time()

                # Execute loop iteration
                await self._loop_iteration()

                # Calculate precise sleep time to maintain frequency
                loop_end = asyncio.get_event_loop().time()
                elapsed = loop_end - loop_start
                sleep_time = max(0, self.interval - elapsed)

                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            logger.info("event_loop_cancelled")
            raise
        except Exception as e:
            logger.error("event_loop_error", error=str(e), exc_info=True)
            raise
        finally:
            self.running = False
            self._log_statistics()
            logger.info("event_loop_stopped")

    def start(self) -> asyncio.Task:
        """
        Start the event loop as a background task

        Returns:
            The asyncio Task running the loop
        """
        if self.task and not self.task.done():
            logger.warning("event_loop_already_running")
            return self.task

        self.task = asyncio.create_task(self.run())
        return self.task

    async def stop(self) -> None:
        """Stop the event loop gracefully"""
        logger.info("event_loop_stopping")
        self.running = False

        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass

        logger.info("event_loop_stopped")

    def _log_statistics(self) -> None:
        """Log event loop performance statistics"""
        if self.iteration_count == 0:
            return

        avg_time = self.total_time / self.iteration_count

        logger.info(
            "event_loop_statistics",
            iterations=self.iteration_count,
            total_time_s=round(self.total_time, 3),
            avg_time_ms=round(avg_time * 1000, 3),
            min_time_ms=round(self.min_loop_time * 1000, 3),
            max_time_ms=round(self.max_loop_time * 1000, 3),
            target_time_ms=round(self.interval * 1000, 3),
        )

    def get_statistics(self) -> dict:
        """
        Get event loop performance statistics

        Returns:
            Dictionary with loop statistics
        """
        if self.iteration_count == 0:
            return {
                "iterations": 0,
                "avg_time_ms": 0,
                "min_time_ms": 0,
                "max_time_ms": 0,
            }

        avg_time = self.total_time / self.iteration_count

        return {
            "iterations": self.iteration_count,
            "total_time_s": round(self.total_time, 3),
            "avg_time_ms": round(avg_time * 1000, 3),
            "min_time_ms": round(self.min_loop_time * 1000, 3),
            "max_time_ms": round(self.max_loop_time * 1000, 3),
            "target_time_ms": round(self.interval * 1000, 3),
            "frequency_hz": self.frequency_hz,
            "running": self.running,
        }
