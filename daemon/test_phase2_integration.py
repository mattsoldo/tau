"""
Phase 2 Integration Test

Tests all Phase 2 components working together:
- Database connection
- ORM models
- Event loop at 30 Hz
- Scheduler with periodic tasks
- State management
- Configuration loading
- State persistence
"""
import asyncio
import time
from datetime import datetime

from tau.config import get_settings
from tau.database import init_database, get_session
from tau.models import Fixture, FixtureModel, Group, GroupFixture, FixtureState, GroupState
from tau.control import (
    EventLoop,
    Scheduler,
    StateManager,
    StatePersistence,
    ConfigLoader,
)


async def test_phase2_integration():
    """Test complete Phase 2 integration"""
    print("=" * 60)
    print("Phase 2 Integration Test")
    print("=" * 60)

    # Initialize database
    print("\n1. Testing database connection...")
    settings = get_settings()
    await init_database(settings.database_url)
    print("   ✓ Database connected")

    # Create test data
    print("\n2. Creating test fixtures and groups...")
    async with get_session() as session:
        # Create fixture model
        fixture_model = FixtureModel(
            manufacturer="Test",
            model="TestModel",
            type="tunable_white",
            dmx_footprint=3,
            mixing_type="linear",
        )
        session.add(fixture_model)
        await session.flush()

        # Create fixtures
        fixture1 = Fixture(
            name="Test Fixture 1",
            dmx_channel_start=1,
            fixture_model_id=fixture_model.id,
        )
        fixture2 = Fixture(
            name="Test Fixture 2",
            dmx_channel_start=4,
            fixture_model_id=fixture_model.id,
        )
        session.add_all([fixture1, fixture2])
        await session.flush()

        # Create group
        group = Group(
            name="Test Group",
            circadian_enabled=True,
        )
        session.add(group)
        await session.flush()

        # Add fixtures to group
        gf1 = GroupFixture(group_id=group.id, fixture_id=fixture1.id)
        gf2 = GroupFixture(group_id=group.id, fixture_id=fixture2.id)
        session.add_all([gf1, gf2])

        await session.commit()

        fixture1_id = fixture1.id
        fixture2_id = fixture2.id
        group_id = group.id

    print(f"   ✓ Created fixtures: {fixture1_id}, {fixture2_id}")
    print(f"   ✓ Created group: {group_id}")

    # Test state management
    print("\n3. Testing state management...")
    state_manager = StateManager()
    config_loader = ConfigLoader(state_manager)
    persistence = StatePersistence(state_manager)

    # Load configuration
    await config_loader.load_configuration()
    print(f"   ✓ Loaded {len(state_manager.fixtures)} fixtures")
    print(f"   ✓ Loaded {len(state_manager.groups)} groups")

    # Verify fixtures are in the group
    memberships = state_manager.fixture_group_memberships.get(fixture1_id, set())
    assert group_id in memberships, "Fixture 1 should be in group"
    print("   ✓ Fixture-to-group membership loaded")

    # Update fixture state
    state_manager.set_fixture_brightness(fixture1_id, 0.75, time.time())
    state_manager.set_fixture_color_temp(fixture1_id, 3000, time.time())
    assert state_manager.dirty, "State should be dirty after update"
    print("   ✓ Fixture state updated (dirty flag set)")

    # Test persistence
    print("\n4. Testing state persistence...")
    await persistence.save_state()
    assert not state_manager.dirty, "State should be clean after save"
    print("   ✓ State persisted to database")

    # Verify saved state in database
    async with get_session() as session:
        saved_state = await session.get(FixtureState, fixture1_id)
        assert saved_state is not None, "State should be saved"
        # Convert from database format (0-1000) to runtime format (0-1)
        assert saved_state.current_brightness == 750, "Brightness should be 750 (0.75 * 1000)"
        assert saved_state.current_cct == 3000, "Color temp should be 3000"
    print("   ✓ Verified saved state in database")

    # Test group state with circadian
    print("\n5. Testing group state with circadian...")
    state_manager.set_group_brightness(group_id, 0.5, time.time())
    state_manager.set_group_circadian(group_id, 0.8, 2700, time.time())
    print("   ✓ Group state and circadian values set")

    # Calculate effective fixture state
    effective_state = state_manager.get_effective_fixture_state(fixture1_id)
    # Expected: fixture(0.75) * group(0.5) * circadian(0.8) = 0.3
    expected_brightness = 0.75 * 0.5 * 0.8
    assert abs(effective_state.brightness - expected_brightness) < 0.01, \
        f"Expected {expected_brightness}, got {effective_state.brightness}"
    assert effective_state.color_temp == 2700, "Should use circadian color temp"
    print(f"   ✓ Effective brightness: {effective_state.brightness:.3f} (fixture * group * circadian)")
    print(f"   ✓ Effective color temp: {effective_state.color_temp}K (from circadian)")

    # Test event loop
    print("\n6. Testing event loop...")
    event_loop = EventLoop(frequency_hz=30)

    # Track callback executions
    callback_count = 0

    async def test_callback():
        nonlocal callback_count
        callback_count += 1

    event_loop.register_callback(test_callback)
    task = event_loop.start()

    # Let it run for 1 second
    await asyncio.sleep(1.0)
    await event_loop.stop()

    # Should have ~30 iterations in 1 second
    assert 25 <= callback_count <= 35, f"Expected ~30 callbacks, got {callback_count}"
    print(f"   ✓ Event loop ran {callback_count} iterations in 1.0s (~30 Hz)")

    stats = event_loop.get_statistics()
    print(f"   ✓ Avg loop time: {stats['avg_time_ms']:.3f}ms (target: {stats['target_time_ms']:.3f}ms)")

    # Test scheduler
    print("\n7. Testing scheduler...")
    scheduler = Scheduler()

    task_run_count = 0

    async def scheduled_task():
        nonlocal task_run_count
        task_run_count += 1

    # Schedule task every 0.2 seconds
    scheduler.schedule("test_task", scheduled_task, interval_seconds=0.2, run_immediately=True)

    # Manually tick the scheduler for 1 second
    start = time.time()
    while time.time() - start < 1.0:
        await scheduler.tick()
        await asyncio.sleep(0.05)  # 50ms between ticks

    # Should run ~5-6 times in 1 second (every 0.2s)
    assert 4 <= task_run_count <= 7, f"Expected ~5 task runs, got {task_run_count}"
    print(f"   ✓ Scheduled task ran {task_run_count} times in 1.0s (every 0.2s)")

    task_stats = scheduler.get_statistics()["test_task"]
    print(f"   ✓ Avg task time: {task_stats['avg_time_ms']:.3f}ms")

    # Cleanup
    print("\n8. Cleaning up test data...")
    async with get_session() as session:
        # Delete in correct order to respect foreign keys
        await session.execute(
            GroupFixture.__table__.delete().where(GroupFixture.group_id == group_id)
        )
        await session.execute(
            FixtureState.__table__.delete().where(FixtureState.fixture_id.in_([fixture1_id, fixture2_id]))
        )
        await session.execute(
            GroupState.__table__.delete().where(GroupState.group_id == group_id)
        )
        await session.execute(
            Fixture.__table__.delete().where(Fixture.id.in_([fixture1_id, fixture2_id]))
        )
        await session.execute(
            Group.__table__.delete().where(Group.id == group_id)
        )
        await session.execute(
            FixtureModel.__table__.delete().where(FixtureModel.id == fixture_model.id)
        )
        await session.commit()
    print("   ✓ Test data cleaned up")

    print("\n" + "=" * 60)
    print("✅ Phase 2 Integration Test PASSED")
    print("=" * 60)
    print("\nVerified components:")
    print("  ✓ Database connection and ORM models")
    print("  ✓ State manager with fixture and group state")
    print("  ✓ Configuration loader from database")
    print("  ✓ State persistence to database")
    print("  ✓ Effective state calculation (fixture * group * circadian)")
    print("  ✓ Event loop at 30 Hz with callbacks")
    print("  ✓ Scheduler with periodic tasks")
    print("\n🎉 Phase 2 Complete!")


if __name__ == "__main__":
    asyncio.run(test_phase2_integration())
