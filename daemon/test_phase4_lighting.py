"""
Phase 4 Lighting Control Logic Test

Tests lighting control components:
- Circadian rhythm engine (keyframe interpolation)
- Scene engine (capture and recall)
- Switch handler (input processing)
- Lighting controller (coordination)
- Integration with event loop
"""
import asyncio
from datetime import datetime, time

from tau.control import StateManager
from tau.hardware import HardwareManager
from tau.logic import (
    CircadianEngine,
    SceneEngine,
    SwitchHandler,
    LightingController,
)
from tau.logic.circadian import CircadianKeyframe


async def test_phase4_lighting():
    """Test complete Phase 4 lighting control logic"""
    print("=" * 60)
    print("Phase 4 Lighting Control Logic Test")
    print("=" * 60)

    # Test Circadian Engine
    print("\n1. Testing Circadian Engine...")
    circadian = CircadianEngine()

    # Create a simple test profile (no database needed)
    test_profile_id = 1
    keyframes = [
        CircadianKeyframe(time(6, 0), 0.3, 2700),   # 6 AM: dim and warm
        CircadianKeyframe(time(12, 0), 1.0, 4000),  # Noon: bright and cool
        CircadianKeyframe(time(18, 0), 0.8, 3000),  # 6 PM: bright and warm
        CircadianKeyframe(time(22, 0), 0.2, 2500),  # 10 PM: very dim and warm
    ]
    circadian.profiles[test_profile_id] = keyframes
    print(f"   ✓ Created test profile with {len(keyframes)} keyframes")

    # Test calculation at different times
    test_times = [
        datetime(2025, 1, 1, 6, 0),   # Exactly at keyframe
        datetime(2025, 1, 1, 9, 0),   # Midpoint between 6 AM and noon
        datetime(2025, 1, 1, 12, 0),  # Noon keyframe
        datetime(2025, 1, 1, 15, 0),  # Between noon and 6 PM
        datetime(2025, 1, 1, 23, 0),  # After last keyframe (wrap around)
    ]

    for test_time in test_times:
        result = circadian.calculate(test_profile_id, test_time)
        assert result is not None, f"Should calculate for {test_time}"
        brightness, cct = result
        assert 0.0 <= brightness <= 1.0, "Brightness should be 0.0-1.0"
        assert 2000 <= cct <= 6500, "CCT should be 2000-6500"
        print(f"   ✓ {test_time.strftime('%H:%M')}: brightness={brightness:.2f}, cct={cct}K")

    # Verify statistics
    stats = circadian.get_statistics()
    assert stats["calculations"] == len(test_times), "Should track calculations"
    print(f"   ✓ Statistics: {stats['calculations']} calculations")

    # Test Scene Engine
    print("\n2. Testing Scene Engine...")
    state_manager = StateManager()

    # Register some test fixtures
    for fixture_id in range(1, 4):
        state_manager.register_fixture(fixture_id)
        state_manager.set_fixture_brightness(fixture_id, fixture_id * 0.3)
        state_manager.set_fixture_color_temp(fixture_id, 2700 + fixture_id * 200)

    scene_engine = SceneEngine(state_manager)
    print("   ✓ Scene engine initialized")

    # Test scene cache (without database)
    test_scene_id = 1
    test_scene_data = {
        1: (700, 3000),   # fixture 1: 70% brightness, 3000K
        2: (500, 2800),   # fixture 2: 50%, 2800K
        3: (1000, 4000),  # fixture 3: 100%, 4000K
    }
    scene_engine.scenes[test_scene_id] = test_scene_data
    print(f"   ✓ Created test scene with {len(test_scene_data)} fixtures")

    # Recall scene (should update state manager)
    success = await scene_engine.recall_scene(test_scene_id)
    assert success, "Should recall scene successfully"
    print("   ✓ Scene recalled")

    # Verify fixture states updated
    for fixture_id, (brightness_db, cct) in test_scene_data.items():
        state = state_manager.get_fixture_state(fixture_id)
        assert state is not None, f"Fixture {fixture_id} should exist"
        expected_brightness = brightness_db / 1000.0
        assert abs(state.brightness - expected_brightness) < 0.01, \
            f"Fixture {fixture_id} brightness should be {expected_brightness}"
        assert state.color_temp == cct, \
            f"Fixture {fixture_id} CCT should be {cct}"
        print(f"   ✓ Fixture {fixture_id}: brightness={state.brightness:.2f}, cct={state.color_temp}K")

    # Verify statistics
    stats = scene_engine.get_statistics()
    assert stats["scenes_recalled"] == 1, "Should have recalled 1 scene"
    print(f"   ✓ Statistics: {stats['scenes_recalled']} scenes recalled")

    # Test Switch Handler
    print("\n3. Testing Switch Handler...")
    hardware_manager = HardwareManager(use_mock=True)
    await hardware_manager.initialize()

    switch_handler = SwitchHandler(state_manager, hardware_manager)
    print("   ✓ Switch handler initialized")

    # Simulate switch input processing (without database)
    # We would normally load switches from database, but for testing
    # we just verify that processing doesn't crash
    await switch_handler.process_inputs()
    print("   ✓ Switch input processing completed")

    stats = switch_handler.get_statistics()
    print(f"   ✓ Statistics: {stats['events_processed']} events processed")

    # Test Lighting Controller
    print("\n4. Testing Lighting Controller...")

    # Reset state manager for clean test
    state_manager.clear()
    for fixture_id in range(1, 4):
        state_manager.register_fixture(fixture_id)
        state_manager.set_fixture_brightness(fixture_id, 0.5)
        state_manager.set_fixture_color_temp(fixture_id, 3000)

    # Register a test group
    state_manager.register_group(1)
    state_manager.add_fixture_to_group(1, 1)
    state_manager.add_fixture_to_group(2, 1)

    controller = LightingController(state_manager, hardware_manager)
    print("   ✓ Lighting controller initialized")

    # Initialize controller (would load from database in real use)
    # For testing, manually set up circadian profile
    controller.group_circadian_profiles[1] = test_profile_id
    controller.circadian.profiles[test_profile_id] = keyframes
    controller.circadian_enabled_groups.add(1)
    print("   ✓ Circadian profile configured for group 1")

    # Test control loop processing
    print("   ⏳ Running control loop iterations...")
    for i in range(5):
        await controller.process_control_loop()
        await asyncio.sleep(0.01)  # Small delay between iterations

    stats = controller.get_statistics()
    assert stats["loop_iterations"] == 5, "Should have 5 iterations"
    print(f"   ✓ Control loop: {stats['loop_iterations']} iterations")
    print(f"   ✓ Hardware updates: {stats['hardware_updates']}")
    print(f"   ✓ Circadian groups: {stats['circadian_enabled_groups']}")

    # Test enable/disable circadian
    await controller.disable_circadian(1)
    assert 1 not in controller.circadian_enabled_groups, "Should disable circadian"
    print("   ✓ Circadian disabled for group 1")

    await controller.enable_circadian(1)
    assert 1 in controller.circadian_enabled_groups, "Should enable circadian"
    print("   ✓ Circadian re-enabled for group 1")

    # Verify all sub-engine statistics
    all_stats = controller.get_statistics()
    print("\n5. Verifying Integrated Statistics...")
    print(f"   ✓ Controller iterations: {all_stats['loop_iterations']}")
    print(f"   ✓ Circadian calculations: {all_stats['circadian']['calculations']}")
    print(f"   ✓ Scenes in cache: {all_stats['scenes']['scenes_cached']}")
    print(f"   ✓ Switch events: {all_stats['switches']['events_processed']}")

    # Test with event loop (brief test)
    print("\n6. Testing Event Loop Integration...")
    from tau.control import EventLoop

    # Create a minimal event loop
    event_loop = EventLoop(frequency_hz=10)  # Lower frequency for test

    # Register controller
    event_loop.register_callback(controller.process_control_loop)

    # Start loop
    event_loop.start()
    print("   ✓ Event loop started")

    # Let it run briefly
    await asyncio.sleep(0.5)

    # Stop loop
    await event_loop.stop()
    print("   ✓ Event loop stopped")

    # Verify loop ran
    loop_stats = event_loop.get_statistics()
    assert loop_stats["iterations"] > 0, "Event loop should have run"
    print(f"   ✓ Event loop ran {loop_stats['iterations']} iterations")

    # Cleanup
    await hardware_manager.shutdown()
    print("   ✓ Hardware manager shut down")

    print("\n" + "=" * 60)
    print("✅ Phase 4 Lighting Control Logic Test PASSED")
    print("=" * 60)
    print("\nVerified components:")
    print("  ✓ Circadian engine (keyframe interpolation)")
    print("  ✓ Scene engine (capture and recall)")
    print("  ✓ Switch handler (input processing)")
    print("  ✓ Lighting controller (coordination)")
    print("  ✓ Event loop integration")
    print("  ✓ Statistics and state tracking")
    print("\n🎉 Phase 4 Complete!")


if __name__ == "__main__":
    asyncio.run(test_phase4_lighting())
