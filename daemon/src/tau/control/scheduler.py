"""
Scheduler - Task scheduling for periodic operations

Allows tasks to be scheduled at specific intervals (e.g., every 5 seconds,
every minute, etc.) without blocking the main control loop.
"""
import asyncio
from datetime import datetime, timedelta
from typing import Callable, Dict, Optional
import structlog

logger = structlog.get_logger(__name__)


class ScheduledTask:
    """A task that runs at a specific interval"""

    def __init__(
        self,
        name: str,
        callback: Callable,
        interval_seconds: float,
        run_immediately: bool = False,
    ):
        """
        Initialize a scheduled task

        Args:
            name: Human-readable task name
            callback: Async function to call
            interval_seconds: How often to run the task
            run_immediately: If True, run on first scheduler tick
        """
        self.name = name
        self.callback = callback
        self.interval = timedelta(seconds=interval_seconds)
        self.last_run: Optional[datetime] = None if run_immediately else datetime.now()
        self.run_count = 0
        self.total_time = 0.0
        self.errors = 0

    def should_run(self, now: datetime) -> bool:
        """Check if this task should run now"""
        if self.last_run is None:
            return True
        return (now - self.last_run) >= self.interval

    async def execute(self) -> None:
        """Execute the task and update statistics"""
        start_time = datetime.now()

        try:
            await self.callback()
            self.run_count += 1
        except Exception as e:
            self.errors += 1
            logger.error(
                "scheduled_task_error",
                task=self.name,
                error=str(e),
                exc_info=True,
            )

        execution_time = (datetime.now() - start_time).total_seconds()
        self.total_time += execution_time
        self.last_run = start_time

        if execution_time > self.interval.total_seconds() * 0.8:
            logger.warning(
                "slow_scheduled_task",
                task=self.name,
                execution_time_ms=execution_time * 1000,
                interval_ms=self.interval.total_seconds() * 1000,
            )

    def get_statistics(self) -> dict:
        """Get task statistics"""
        avg_time = self.total_time / self.run_count if self.run_count > 0 else 0

        return {
            "name": self.name,
            "interval_s": self.interval.total_seconds(),
            "run_count": self.run_count,
            "total_time_s": round(self.total_time, 3),
            "avg_time_ms": round(avg_time * 1000, 3),
            "errors": self.errors,
            "last_run": self.last_run.isoformat() if self.last_run else None,
        }


class Scheduler:
    """
    Task scheduler for periodic operations

    Manages tasks that need to run at specific intervals, such as:
    - State persistence (every 5 seconds)
    - Circadian updates (every 60 seconds)
    - DMX output (every 1/44 seconds)
    """

    def __init__(self):
        """Initialize the scheduler"""
        self.tasks: Dict[str, ScheduledTask] = {}
        logger.info("scheduler_initialized")

    def schedule(
        self,
        name: str,
        callback: Callable,
        interval_seconds: float,
        run_immediately: bool = False,
    ) -> None:
        """
        Schedule a task to run at a specific interval

        Args:
            name: Unique task name
            callback: Async function to call
            interval_seconds: How often to run (in seconds)
            run_immediately: If True, run on first tick
        """
        if not asyncio.iscoroutinefunction(callback):
            logger.error(
                "invalid_scheduled_task",
                task=name,
                error="Callback must be async function",
            )
            return

        if name in self.tasks:
            logger.warning("task_already_scheduled", task=name)
            return

        task = ScheduledTask(name, callback, interval_seconds, run_immediately)
        self.tasks[name] = task

        logger.info(
            "task_scheduled",
            task=name,
            interval_s=interval_seconds,
            run_immediately=run_immediately,
        )

    def unschedule(self, name: str) -> bool:
        """
        Remove a scheduled task

        Args:
            name: Task name to remove

        Returns:
            True if task was removed, False if not found
        """
        if name in self.tasks:
            del self.tasks[name]
            logger.info("task_unscheduled", task=name)
            return True

        logger.warning("task_not_found", task=name)
        return False

    async def tick(self) -> None:
        """
        Process all scheduled tasks (called by event loop)

        This should be called on every iteration of the main event loop.
        It checks all tasks and runs those that are due.
        """
        now = datetime.now()

        for task in self.tasks.values():
            if task.should_run(now):
                await task.execute()

    def get_statistics(self) -> dict:
        """
        Get statistics for all scheduled tasks

        Returns:
            Dictionary mapping task names to their statistics
        """
        return {name: task.get_statistics() for name, task in self.tasks.items()}

    def clear(self) -> None:
        """Remove all scheduled tasks"""
        count = len(self.tasks)
        self.tasks.clear()
        logger.info("scheduler_cleared", task_count=count)
