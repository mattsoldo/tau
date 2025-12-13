"""
Unit Tests for Lighting Logic Components

Comprehensive unit tests for circadian, scenes, switches, and controller
with edge cases, error handling, and boundary conditions.
"""
import asyncio
from datetime import datetime, time
import pytest

from tau.control import StateManager
from tau.hardware import HardwareManager
from tau.logic.circadian import CircadianEngine, CircadianKeyframe
from tau.logic.scenes import SceneEngine
from tau.logic.switches import SwitchHandler, SwitchState, SwitchEvent
from tau.logic.controller import LightingController


class TestCircadianEngine:
    """Unit tests for CircadianEngine"""

    def test_keyframe_seconds_since_midnight(self):
        """Test keyframe time conversion to seconds"""
        kf = CircadianKeyframe(time(6, 30, 45), 0.5, 3000)
        expected = 6 * 3600 + 30 * 60 + 45
        assert kf.seconds_since_midnight == expected

    def test_keyframe_midnight(self):
        """Test keyframe at exactly midnight"""
        kf = CircadianKeyframe(time(0, 0, 0), 0.1, 2000)
        assert kf.seconds_since_midnight == 0

    def test_keyframe_almost_midnight(self):
        """Test keyframe just before midnight"""
        kf = CircadianKeyframe(time(23, 59, 59), 0.1, 2000)
        expected = 23 * 3600 + 59 * 60 + 59
        assert kf.seconds_since_midnight == expected

    def test_calculate_without_profile(self):
        """Test calculation with non-existent profile"""
        engine = CircadianEngine()
        result = engine.calculate(999)
        assert result is None

    def test_calculate_with_empty_profile(self):
        """Test calculation with profile that has no keyframes"""
        engine = CircadianEngine()
        engine.profiles[1] = []
        result = engine.calculate(1)
        assert result is None

    def test_calculate_single_keyframe(self):
        """Test calculation with only one keyframe (edge case)"""
        engine = CircadianEngine()
        engine.profiles[1] = [CircadianKeyframe(time(12, 0), 1.0, 4000)]

        # Any time should return the same values
        result = engine.calculate(1, datetime(2025, 1, 1, 6, 0))
        assert result == (1.0, 4000)

    def test_calculate_exact_keyframe_time(self):
        """Test calculation at exact keyframe time"""
        engine = CircadianEngine()
        engine.profiles[1] = [
            CircadianKeyframe(time(6, 0), 0.3, 2700),
            CircadianKeyframe(time(12, 0), 1.0, 4000),
        ]

        result = engine.calculate(1, datetime(2025, 1, 1, 6, 0))
        assert result == (0.3, 2700)

        result = engine.calculate(1, datetime(2025, 1, 1, 12, 0))
        assert result == (1.0, 4000)

    def test_calculate_interpolation_midpoint(self):
        """Test interpolation exactly halfway between keyframes"""
        engine = CircadianEngine()
        engine.profiles[1] = [
            CircadianKeyframe(time(6, 0), 0.0, 2000),
            CircadianKeyframe(time(12, 0), 1.0, 4000),
        ]

        # 9 AM is exactly halfway between 6 AM and noon
        result = engine.calculate(1, datetime(2025, 1, 1, 9, 0))
        brightness, cct = result
        assert abs(brightness - 0.5) < 0.01
        assert abs(cct - 3000) < 10

    def test_calculate_midnight_wraparound_before(self):
        """Test midnight wraparound - time before first keyframe"""
        engine = CircadianEngine()
        engine.profiles[1] = [
            CircadianKeyframe(time(6, 0), 0.3, 2700),
            CircadianKeyframe(time(22, 0), 0.2, 2500),
        ]

        # 3 AM - should interpolate from 22:00 to 6:00
        result = engine.calculate(1, datetime(2025, 1, 1, 3, 0))
        brightness, cct = result
        # Should be between 0.2 and 0.3
        assert 0.2 <= brightness <= 0.3
        assert 2500 <= cct <= 2700

    def test_calculate_midnight_wraparound_after(self):
        """Test midnight wraparound - time after last keyframe"""
        engine = CircadianEngine()
        engine.profiles[1] = [
            CircadianKeyframe(time(6, 0), 0.3, 2700),
            CircadianKeyframe(time(22, 0), 0.2, 2500),
        ]

        # 23:00 - should interpolate from 22:00 to 6:00 (next day)
        result = engine.calculate(1, datetime(2025, 1, 1, 23, 0))
        brightness, cct = result
        # Should be close to 0.2 (just after 22:00)
        assert 0.2 <= brightness <= 0.25
        assert 2500 <= cct <= 2600

    def test_statistics_tracking(self):
        """Test statistics tracking"""
        engine = CircadianEngine()
        engine.profiles[1] = [CircadianKeyframe(time(12, 0), 1.0, 4000)]

        # Run multiple calculations
        for _ in range(5):
            engine.calculate(1, datetime(2025, 1, 1, 12, 0))

        stats = engine.get_statistics()
        assert stats["calculations"] == 5
        assert stats["profiles_loaded"] == 1

    def test_cache_clear(self):
        """Test cache clearing"""
        engine = CircadianEngine()
        engine.profiles[1] = [CircadianKeyframe(time(12, 0), 1.0, 4000)]
        engine.profiles[2] = [CircadianKeyframe(time(12, 0), 0.5, 3000)]

        engine.clear_cache()
        assert len(engine.profiles) == 0


class TestSceneEngine:
    """Unit tests for SceneEngine"""

    def test_scene_cache_hit(self):
        """Test scene cache hit tracking"""
        state_manager = StateManager()
        engine = SceneEngine(state_manager)

        # Pre-populate cache
        engine.scenes[1] = {1: (700, 3000)}

        asyncio.run(engine.recall_scene(1))

        stats = engine.get_statistics()
        assert stats["cache_hits"] == 1

    def test_recall_nonexistent_scene(self):
        """Test recalling a scene that doesn't exist"""
        state_manager = StateManager()
        engine = SceneEngine(state_manager)

        # Try to recall scene that doesn't exist and isn't in cache
        result = asyncio.run(engine.recall_scene(999))
        assert result is False

    def test_brightness_conversion_database_to_state(self):
        """Test brightness conversion from database (0-1000) to state (0.0-1.0)"""
        state_manager = StateManager()
        state_manager.register_fixture(1)

        engine = SceneEngine(state_manager)
        engine.scenes[1] = {
            1: (0, 3000),      # 0%
            2: (500, 3000),    # 50%
            3: (1000, 3000),   # 100%
        }

        # Register fixtures
        for i in range(1, 4):
            state_manager.register_fixture(i)

        asyncio.run(engine.recall_scene(1))

        assert state_manager.get_fixture_state(1).brightness == 0.0
        assert state_manager.get_fixture_state(2).brightness == 0.5
        assert state_manager.get_fixture_state(3).brightness == 1.0

    def test_scene_with_none_values(self):
        """Test scene with None brightness or CCT"""
        state_manager = StateManager()
        state_manager.register_fixture(1)

        engine = SceneEngine(state_manager)
        engine.scenes[1] = {1: (None, 3000)}  # None brightness

        asyncio.run(engine.recall_scene(1))

        # Should set brightness to 0.0 when None
        assert state_manager.get_fixture_state(1).brightness == 0.0

    def test_statistics_tracking(self):
        """Test statistics tracking"""
        state_manager = StateManager()
        state_manager.register_fixture(1)

        engine = SceneEngine(state_manager)
        engine.scenes[1] = {1: (700, 3000)}
        engine.scenes[2] = {1: (500, 2800)}

        asyncio.run(engine.recall_scene(1))
        asyncio.run(engine.recall_scene(2))
        asyncio.run(engine.recall_scene(1))  # Cache hit

        stats = engine.get_statistics()
        assert stats["scenes_recalled"] == 3
        assert stats["cache_hits"] == 3
        assert stats["scenes_cached"] == 2

    def test_cache_clear(self):
        """Test cache clearing"""
        state_manager = StateManager()
        engine = SceneEngine(state_manager)

        engine.scenes[1] = {1: (700, 3000)}
        engine.scenes[2] = {1: (500, 2800)}

        engine.clear_cache()
        assert len(engine.scenes) == 0


class TestSwitchHandler:
    """Unit tests for SwitchHandler"""

    def test_switch_state_initialization(self):
        """Test switch state data structure"""
        state = SwitchState(switch_id=1)
        assert state.switch_id == 1
        assert state.last_digital_value is None
        assert state.last_analog_value is None
        assert state.last_change_time == 0.0
        assert state.is_pressed is False

    def test_handler_initialization(self):
        """Test handler initialization"""
        state_manager = StateManager()
        hardware_manager = HardwareManager(use_mock=True)
        handler = SwitchHandler(state_manager, hardware_manager, hold_threshold=2.0)

        assert handler.hold_threshold == 2.0
        assert len(handler.switches) == 0
        assert len(handler.switch_states) == 0

    def test_statistics_tracking(self):
        """Test statistics tracking"""
        state_manager = StateManager()
        hardware_manager = HardwareManager(use_mock=True)
        handler = SwitchHandler(state_manager, hardware_manager)

        stats = handler.get_statistics()
        assert "events_processed" in stats
        assert "switches_loaded" in stats
        assert "active_switches" in stats


class TestLightingController:
    """Unit tests for LightingController"""

    def test_controller_initialization(self):
        """Test controller initialization"""
        state_manager = StateManager()
        hardware_manager = HardwareManager(use_mock=True)
        controller = LightingController(state_manager, hardware_manager)

        assert controller.state_manager == state_manager
        assert controller.hardware_manager == hardware_manager
        assert controller.circadian is not None
        assert controller.scenes is not None
        assert controller.switches is not None

    def test_enable_circadian_without_profile(self):
        """Test enabling circadian for group without profile"""
        state_manager = StateManager()
        hardware_manager = HardwareManager(use_mock=True)
        controller = LightingController(state_manager, hardware_manager)

        # Try to enable circadian for group without profile
        result = asyncio.run(controller.enable_circadian(999))
        assert result is False

    def test_enable_disable_circadian(self):
        """Test enabling and disabling circadian"""
        state_manager = StateManager()
        state_manager.register_group(1)

        hardware_manager = HardwareManager(use_mock=True)
        controller = LightingController(state_manager, hardware_manager)

        # Set up profile
        controller.group_circadian_profiles[1] = 1
        controller.circadian.profiles[1] = [
            CircadianKeyframe(time(12, 0), 1.0, 4000)
        ]

        # Enable
        result = asyncio.run(controller.enable_circadian(1))
        assert result is True
        assert 1 in controller.circadian_enabled_groups

        # Disable
        result = asyncio.run(controller.disable_circadian(1))
        assert result is True
        assert 1 not in controller.circadian_enabled_groups

    def test_statistics_integration(self):
        """Test statistics from all sub-engines"""
        state_manager = StateManager()
        hardware_manager = HardwareManager(use_mock=True)
        controller = LightingController(state_manager, hardware_manager)

        stats = controller.get_statistics()
        assert "loop_iterations" in stats
        assert "hardware_updates" in stats
        assert "circadian" in stats
        assert "scenes" in stats
        assert "switches" in stats

    def test_control_loop_without_fixtures(self):
        """Test control loop with no fixtures (shouldn't crash)"""
        state_manager = StateManager()
        hardware_manager = HardwareManager(use_mock=True)
        asyncio.run(hardware_manager.initialize())

        controller = LightingController(state_manager, hardware_manager)

        # Should complete without error
        asyncio.run(controller.process_control_loop())

        stats = controller.get_statistics()
        assert stats["loop_iterations"] == 1


class TestStateManagerEdgeCases:
    """Unit tests for StateManager edge cases"""

    def test_set_brightness_clamping_low(self):
        """Test brightness clamping below 0"""
        manager = StateManager()
        manager.register_fixture(1)

        result = manager.set_fixture_brightness(1, -0.5)
        assert result is True
        assert manager.get_fixture_state(1).brightness == 0.0

    def test_set_brightness_clamping_high(self):
        """Test brightness clamping above 1"""
        manager = StateManager()
        manager.register_fixture(1)

        result = manager.set_fixture_brightness(1, 1.5)
        assert result is True
        assert manager.get_fixture_state(1).brightness == 1.0

    def test_set_color_temp_clamping_low(self):
        """Test CCT clamping below 2000K"""
        manager = StateManager()
        manager.register_fixture(1)

        result = manager.set_fixture_color_temp(1, 1000)
        assert result is True
        assert manager.get_fixture_state(1).color_temp == 2000

    def test_set_color_temp_clamping_high(self):
        """Test CCT clamping above 6500K"""
        manager = StateManager()
        manager.register_fixture(1)

        result = manager.set_fixture_color_temp(1, 10000)
        assert result is True
        assert manager.get_fixture_state(1).color_temp == 6500

    def test_set_nonexistent_fixture(self):
        """Test setting brightness for non-existent fixture"""
        manager = StateManager()

        result = manager.set_fixture_brightness(999, 0.5)
        assert result is False

    def test_effective_state_with_group_brightness(self):
        """Test effective state calculation with group brightness"""
        manager = StateManager()
        manager.register_fixture(1)
        manager.register_group(1)
        manager.add_fixture_to_group(1, 1)

        # Set fixture to 80%
        manager.set_fixture_brightness(1, 0.8)

        # Set group to 50%
        manager.set_group_brightness(1, 0.5)

        effective = manager.get_effective_fixture_state(1)
        # Should be 0.8 * 0.5 = 0.4
        assert abs(effective.brightness - 0.4) < 0.01

    def test_effective_state_with_circadian(self):
        """Test effective state with circadian enabled"""
        manager = StateManager()
        manager.register_fixture(1)
        manager.register_group(1)
        manager.add_fixture_to_group(1, 1)

        # Set fixture to 100%
        manager.set_fixture_brightness(1, 1.0)

        # Set group to 80%
        manager.set_group_brightness(1, 0.8)

        # Enable circadian at 50%
        group_state = manager.get_group_state(1)
        group_state.circadian_enabled = True
        manager.set_group_circadian(1, 0.5, 3000)

        effective = manager.get_effective_fixture_state(1)
        # Should be 1.0 * 0.8 * 0.5 = 0.4
        assert abs(effective.brightness - 0.4) < 0.01
        # CCT should be overridden to circadian value
        assert effective.color_temp == 3000


def run_all_tests():
    """Run all unit tests"""
    print("=" * 60)
    print("Running Unit Tests for Lighting Logic")
    print("=" * 60)

    test_classes = [
        TestCircadianEngine,
        TestSceneEngine,
        TestSwitchHandler,
        TestLightingController,
        TestStateManagerEdgeCases,
    ]

    total_tests = 0
    passed_tests = 0
    failed_tests = []

    for test_class in test_classes:
        class_name = test_class.__name__
        print(f"\n{class_name}:")

        # Get all test methods
        test_methods = [
            method for method in dir(test_class)
            if method.startswith('test_') and callable(getattr(test_class, method))
        ]

        for method_name in test_methods:
            total_tests += 1
            try:
                # Create instance and run test
                instance = test_class()
                method = getattr(instance, method_name)
                method()
                print(f"  ✓ {method_name}")
                passed_tests += 1
            except Exception as e:
                print(f"  ✗ {method_name}: {str(e)}")
                failed_tests.append((class_name, method_name, str(e)))

    print("\n" + "=" * 60)
    print(f"Test Results: {passed_tests}/{total_tests} passed")
    print("=" * 60)

    if failed_tests:
        print("\nFailed Tests:")
        for class_name, method_name, error in failed_tests:
            print(f"  ✗ {class_name}.{method_name}")
            print(f"    {error}")
        return False
    else:
        print("\n✅ All Unit Tests PASSED!")
        return True


if __name__ == "__main__":
    success = run_all_tests()
    exit(0 if success else 1)
