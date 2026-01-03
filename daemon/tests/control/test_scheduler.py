"""
Unit tests for Scheduler

Tests task scheduling, execution, and statistics.
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from tau.control.scheduler import Scheduler, ScheduledTask


class TestScheduledTask:
    """Tests for ScheduledTask class."""

    def test_create_task(self):
        """Test creating a scheduled task."""
        callback = AsyncMock()
        task = ScheduledTask("test_task", callback, interval_seconds=5.0)

        assert task.name == "test_task"
        assert task.callback is callback
        assert task.interval == timedelta(seconds=5.0)
        assert task.run_count == 0
        assert task.errors == 0

    def test_should_run_first_time(self):
        """Test that task should run on first tick when run_immediately=True."""
        callback = AsyncMock()
        task = ScheduledTask("test", callback, interval_seconds=5.0, run_immediately=True)

        # Task should run immediately
        assert task.should_run(datetime.now()) is True

    def test_should_run_not_first_time(self):
        """Test that task should not run immediately when run_immediately=False."""
        callback = AsyncMock()
        task = ScheduledTask("test", callback, interval_seconds=5.0, run_immediately=False)

        # Task should not run immediately
        assert task.should_run(datetime.now()) is False

    def test_should_run_after_interval(self):
        """Test that task should run after interval has passed."""
        callback = AsyncMock()
        task = ScheduledTask("test", callback, interval_seconds=5.0, run_immediately=False)

        # Set last_run to 10 seconds ago
        task.last_run = datetime.now() - timedelta(seconds=10)

        # Task should run
        assert task.should_run(datetime.now()) is True

    def test_should_run_before_interval(self):
        """Test that task should not run before interval has passed."""
        callback = AsyncMock()
        task = ScheduledTask("test", callback, interval_seconds=5.0, run_immediately=False)

        # Set last_run to 2 seconds ago
        task.last_run = datetime.now() - timedelta(seconds=2)

        # Task should not run yet
        assert task.should_run(datetime.now()) is False

    @pytest.mark.asyncio
    async def test_execute_success(self):
        """Test successful task execution."""
        callback = AsyncMock()
        task = ScheduledTask("test", callback, interval_seconds=5.0)

        await task.execute()

        callback.assert_called_once()
        assert task.run_count == 1
        assert task.errors == 0
        assert task.last_run is not None

    @pytest.mark.asyncio
    async def test_execute_with_error(self):
        """Test task execution that raises an exception."""
        callback = AsyncMock(side_effect=ValueError("Test error"))
        task = ScheduledTask("test", callback, interval_seconds=5.0)

        await task.execute()  # Should not raise

        callback.assert_called_once()
        assert task.run_count == 0  # Not incremented on error
        assert task.errors == 1

    def test_get_statistics(self):
        """Test getting task statistics."""
        callback = AsyncMock()
        task = ScheduledTask("test_task", callback, interval_seconds=5.0)
        task.run_count = 10
        task.total_time = 0.5
        task.errors = 1
        task.last_run = datetime.now()

        stats = task.get_statistics()

        assert stats["name"] == "test_task"
        assert stats["interval_s"] == 5.0
        assert stats["run_count"] == 10
        assert stats["avg_time_ms"] == 50.0  # 0.5s / 10 runs = 50ms
        assert stats["errors"] == 1


class TestScheduler:
    """Tests for Scheduler class."""

    def test_create_scheduler(self, scheduler):
        """Test creating a scheduler."""
        assert len(scheduler.tasks) == 0

    def test_schedule_task(self, scheduler):
        """Test scheduling a task."""
        callback = AsyncMock()

        scheduler.schedule("test_task", callback, interval_seconds=5.0)

        assert "test_task" in scheduler.tasks
        assert scheduler.tasks["test_task"].callback is callback

    def test_schedule_non_async_callback_rejected(self, scheduler):
        """Test that non-async callbacks are rejected."""
        def sync_callback():
            pass

        scheduler.schedule("test_task", sync_callback, interval_seconds=5.0)

        # Task should not be scheduled
        assert "test_task" not in scheduler.tasks

    def test_schedule_duplicate_task_rejected(self, scheduler):
        """Test that duplicate task names are rejected."""
        callback1 = AsyncMock()
        callback2 = AsyncMock()

        scheduler.schedule("test_task", callback1, interval_seconds=5.0)
        scheduler.schedule("test_task", callback2, interval_seconds=10.0)

        # First callback should be kept
        assert scheduler.tasks["test_task"].callback is callback1
        assert scheduler.tasks["test_task"].interval == timedelta(seconds=5.0)

    def test_unschedule_task(self, scheduler):
        """Test unscheduling a task."""
        callback = AsyncMock()
        scheduler.schedule("test_task", callback, interval_seconds=5.0)

        result = scheduler.unschedule("test_task")

        assert result is True
        assert "test_task" not in scheduler.tasks

    def test_unschedule_nonexistent_task(self, scheduler):
        """Test unscheduling a task that doesn't exist."""
        result = scheduler.unschedule("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_tick_runs_due_tasks(self, scheduler):
        """Test that tick() runs tasks that are due."""
        callback = AsyncMock()
        scheduler.schedule("test_task", callback, interval_seconds=0.1, run_immediately=True)

        await scheduler.tick()

        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_tick_skips_not_due_tasks(self, scheduler):
        """Test that tick() skips tasks that are not due."""
        callback = AsyncMock()
        scheduler.schedule("test_task", callback, interval_seconds=60.0, run_immediately=False)

        await scheduler.tick()

        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_tick_runs_multiple_due_tasks(self, scheduler):
        """Test that tick() runs multiple tasks that are due."""
        callback1 = AsyncMock()
        callback2 = AsyncMock()

        scheduler.schedule("task1", callback1, interval_seconds=0.1, run_immediately=True)
        scheduler.schedule("task2", callback2, interval_seconds=0.1, run_immediately=True)

        await scheduler.tick()

        callback1.assert_called_once()
        callback2.assert_called_once()

    def test_get_statistics(self, scheduler):
        """Test getting scheduler statistics."""
        callback = AsyncMock()
        scheduler.schedule("task1", callback, interval_seconds=5.0)
        scheduler.schedule("task2", callback, interval_seconds=10.0)

        stats = scheduler.get_statistics()

        assert "task1" in stats
        assert "task2" in stats
        assert stats["task1"]["interval_s"] == 5.0
        assert stats["task2"]["interval_s"] == 10.0

    def test_clear(self, scheduler):
        """Test clearing all tasks."""
        callback = AsyncMock()
        scheduler.schedule("task1", callback, interval_seconds=5.0)
        scheduler.schedule("task2", callback, interval_seconds=10.0)

        scheduler.clear()

        assert len(scheduler.tasks) == 0


class TestSchedulerIntegration:
    """Integration tests for scheduler with real timing."""

    @pytest.mark.asyncio
    async def test_task_runs_at_interval(self, scheduler):
        """Test that task runs at approximately the correct interval."""
        call_times = []

        async def track_time():
            call_times.append(datetime.now())

        # Schedule task to run every 0.1 seconds
        scheduler.schedule("test", track_time, interval_seconds=0.1, run_immediately=True)

        # Run multiple ticks
        for _ in range(5):
            await scheduler.tick()
            await asyncio.sleep(0.05)

        # Should have at least 2 calls
        assert len(call_times) >= 2

    @pytest.mark.asyncio
    async def test_slow_task_warning(self, scheduler):
        """Test that slow tasks are logged as warnings."""
        async def slow_task():
            await asyncio.sleep(0.2)

        # Schedule task with short interval
        scheduler.schedule("slow", slow_task, interval_seconds=0.1, run_immediately=True)

        # Execute should complete without error despite being slow
        await scheduler.tick()

        # Verify task was executed
        assert scheduler.tasks["slow"].run_count == 1
