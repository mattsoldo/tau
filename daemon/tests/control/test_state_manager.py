"""
Unit tests for StateManager

Tests fixture and group state management, transitions, and interpolation.
"""
import pytest
import time


class TestStateManagerFixtureRegistration:
    """Tests for fixture registration and basic state management."""

    def test_register_fixture(self, state_manager):
        """Test registering a new fixture."""
        state_manager.register_fixture(1)

        assert 1 in state_manager.fixtures
        assert state_manager.fixtures[1].fixture_id == 1
        assert state_manager.fixtures[1].current_brightness == 0.0
        assert state_manager.fixtures[1].goal_brightness == 0.0

    def test_register_fixture_is_idempotent(self, state_manager):
        """Test that registering the same fixture twice doesn't reset state."""
        state_manager.register_fixture(1)
        state_manager.set_fixture_brightness(1, 0.5)

        state_manager.register_fixture(1)  # Register again

        # State should not be reset
        assert state_manager.fixtures[1].goal_brightness == 0.5

    def test_register_multiple_fixtures(self, state_manager):
        """Test registering multiple fixtures."""
        for i in range(1, 6):
            state_manager.register_fixture(i)

        assert len(state_manager.fixtures) == 5
        for i in range(1, 6):
            assert i in state_manager.fixtures

    def test_get_fixture_state(self, state_manager):
        """Test getting fixture state."""
        state_manager.register_fixture(1)
        state_manager.set_fixture_brightness(1, 0.75)

        state = state_manager.get_fixture_state(1)

        assert state is not None
        assert state.fixture_id == 1
        assert state.goal_brightness == 0.75

    def test_get_fixture_state_not_found(self, state_manager):
        """Test getting state for non-existent fixture returns None."""
        state = state_manager.get_fixture_state(999)
        assert state is None


class TestStateManagerBrightness:
    """Tests for brightness control."""

    def test_set_fixture_brightness_instant(self, state_manager):
        """Test setting fixture brightness without transition."""
        state_manager.register_fixture(1)

        result = state_manager.set_fixture_brightness(1, 0.5, transition_duration=0.0)

        assert result is True
        fixture = state_manager.fixtures[1]
        assert fixture.goal_brightness == 0.5
        assert fixture.current_brightness == 0.5

    def test_set_fixture_brightness_clamping_upper(self, state_manager):
        """Test that brightness is clamped to 1.0."""
        state_manager.register_fixture(1)

        state_manager.set_fixture_brightness(1, 1.5)

        assert state_manager.fixtures[1].goal_brightness == 1.0

    def test_set_fixture_brightness_clamping_lower(self, state_manager):
        """Test that brightness is clamped to 0.0."""
        state_manager.register_fixture(1)

        state_manager.set_fixture_brightness(1, -0.5)

        assert state_manager.fixtures[1].goal_brightness == 0.0

    def test_set_fixture_brightness_not_found(self, state_manager):
        """Test setting brightness for non-existent fixture."""
        result = state_manager.set_fixture_brightness(999, 0.5)
        assert result is False

    def test_set_fixture_brightness_marks_dirty(self, state_manager):
        """Test that setting brightness marks state as dirty."""
        state_manager.register_fixture(1)
        state_manager.dirty = False

        state_manager.set_fixture_brightness(1, 0.5)

        assert state_manager.dirty is True


class TestStateManagerColorTemp:
    """Tests for color temperature control."""

    def test_set_fixture_color_temp_instant(self, state_manager):
        """Test setting color temperature without transition."""
        state_manager.register_fixture(1)

        result = state_manager.set_fixture_color_temp(1, 4000)

        assert result is True
        fixture = state_manager.fixtures[1]
        assert fixture.goal_color_temp == 4000
        assert fixture.current_color_temp == 4000

    def test_set_fixture_color_temp_clamping_upper(self, state_manager):
        """Test that color temp is clamped to 6500K."""
        state_manager.register_fixture(1)

        state_manager.set_fixture_color_temp(1, 8000)

        assert state_manager.fixtures[1].goal_color_temp == 6500

    def test_set_fixture_color_temp_clamping_lower(self, state_manager):
        """Test that color temp is clamped to 2000K."""
        state_manager.register_fixture(1)

        state_manager.set_fixture_color_temp(1, 1500)

        assert state_manager.fixtures[1].goal_color_temp == 2000

    def test_set_fixture_color_temp_not_found(self, state_manager):
        """Test setting color temp for non-existent fixture."""
        result = state_manager.set_fixture_color_temp(999, 4000)
        assert result is False


class TestStateManagerTransitions:
    """Tests for gradual state transitions."""

    def test_set_brightness_with_transition(self, state_manager, mock_time):
        """Test setting brightness with a transition duration."""
        state_manager.register_fixture(1)
        state_manager.set_fixture_brightness(1, 0.2, transition_duration=0, timestamp=mock_time.time())

        # Start a transition from 0.2 to 1.0 over 2 seconds
        state_manager.set_fixture_brightness(1, 1.0, transition_duration=2.0, timestamp=mock_time.time())

        fixture = state_manager.fixtures[1]
        assert fixture.goal_brightness == 1.0
        assert fixture.current_brightness == 0.2  # Still at start
        assert fixture.start_brightness == 0.2
        assert fixture.transition_duration == 2.0
        assert fixture.transition_start is not None

    def test_update_fixture_transitions_midpoint(self, state_manager, mock_time):
        """Test transition interpolation at 50%."""
        state_manager.register_fixture(1)
        state_manager.set_fixture_brightness(1, 0.0, timestamp=mock_time.time())

        # Start transition from 0 to 1 over 2 seconds
        state_manager.set_fixture_brightness(1, 1.0, transition_duration=2.0, timestamp=mock_time.time())

        # Advance time by 1 second (50%)
        mock_time.advance(1.0)
        transitioning = state_manager.update_fixture_transitions(mock_time.time())

        fixture = state_manager.fixtures[1]
        assert transitioning == 1
        assert fixture.current_brightness == pytest.approx(0.5, abs=0.01)

    def test_update_fixture_transitions_complete(self, state_manager, mock_time):
        """Test transition completion."""
        state_manager.register_fixture(1)
        state_manager.set_fixture_brightness(1, 0.0, timestamp=mock_time.time())

        # Start transition from 0 to 1 over 2 seconds
        state_manager.set_fixture_brightness(1, 1.0, transition_duration=2.0, timestamp=mock_time.time())

        # Advance time by 2 seconds (100%)
        mock_time.advance(2.0)
        transitioning = state_manager.update_fixture_transitions(mock_time.time())

        fixture = state_manager.fixtures[1]
        assert transitioning == 0
        assert fixture.current_brightness == 1.0
        assert fixture.transition_start is None

    def test_update_fixture_transitions_overshoot(self, state_manager, mock_time):
        """Test that overshooting transition time completes correctly."""
        state_manager.register_fixture(1)
        state_manager.set_fixture_brightness(1, 0.0, timestamp=mock_time.time())

        # Start transition from 0 to 1 over 2 seconds
        state_manager.set_fixture_brightness(1, 1.0, transition_duration=2.0, timestamp=mock_time.time())

        # Advance time by 5 seconds (way past completion)
        mock_time.advance(5.0)
        transitioning = state_manager.update_fixture_transitions(mock_time.time())

        fixture = state_manager.fixtures[1]
        assert transitioning == 0
        assert fixture.current_brightness == 1.0
        assert fixture.goal_brightness == 1.0

    def test_color_temp_transition(self, state_manager, mock_time):
        """Test color temperature transition interpolation."""
        state_manager.register_fixture(1)
        state_manager.set_fixture_color_temp(1, 2700, timestamp=mock_time.time())

        # Start transition from 2700 to 6500 over 2 seconds
        state_manager.set_fixture_color_temp(1, 6500, transition_duration=2.0, timestamp=mock_time.time())

        # Advance time by 1 second (50%)
        mock_time.advance(1.0)
        state_manager.update_fixture_transitions(mock_time.time())

        fixture = state_manager.fixtures[1]
        expected_cct = 2700 + (6500 - 2700) * 0.5  # 4600K
        assert fixture.current_color_temp == pytest.approx(expected_cct, abs=50)

    def test_multiple_fixtures_transitioning(self, populated_state_manager, mock_time):
        """Test multiple fixtures transitioning simultaneously."""
        sm = populated_state_manager

        # Start transitions on all 3 fixtures
        for i in range(1, 4):
            sm.set_fixture_brightness(i, 0.0, timestamp=mock_time.time())
            sm.set_fixture_brightness(i, 1.0, transition_duration=2.0, timestamp=mock_time.time())

        # Advance time by 1 second
        mock_time.advance(1.0)
        transitioning = sm.update_fixture_transitions(mock_time.time())

        assert transitioning == 3

        for i in range(1, 4):
            assert sm.fixtures[i].current_brightness == pytest.approx(0.5, abs=0.01)


class TestStateManagerGroups:
    """Tests for group state management."""

    def test_register_group(self, state_manager):
        """Test registering a new group."""
        state_manager.register_group(1)

        assert 1 in state_manager.groups
        assert state_manager.groups[1].group_id == 1
        # Default brightness is 1.0 (pass-through multiplier)
        assert state_manager.groups[1].brightness == 1.0

    def test_add_fixture_to_group(self, state_manager):
        """Test adding a fixture to a group."""
        state_manager.register_fixture(1)
        state_manager.register_group(1)

        state_manager.add_fixture_to_group(1, 1)

        assert 1 in state_manager.fixture_group_memberships[1]

    def test_fixture_in_multiple_groups(self, state_manager):
        """Test a fixture belonging to multiple groups."""
        state_manager.register_fixture(1)
        state_manager.register_group(1)
        state_manager.register_group(2)

        state_manager.add_fixture_to_group(1, 1)
        state_manager.add_fixture_to_group(1, 2)

        memberships = state_manager.fixture_group_memberships[1]
        assert 1 in memberships
        assert 2 in memberships

    def test_set_group_brightness(self, state_manager):
        """Test setting group brightness updates group state."""
        state_manager.register_group(1)

        # Note: set_group_brightness returns count of fixtures updated (int)
        result = state_manager.set_group_brightness(1, 0.8)

        # No fixtures in group, so 0 updated, but group state should still update
        assert result == 0  # No fixtures to update
        assert state_manager.groups[1].brightness == 0.8

    def test_set_group_brightness_not_found(self, state_manager):
        """Test setting brightness for non-existent group returns 0."""
        # set_group_brightness returns 0 when group not found
        result = state_manager.set_group_brightness(999, 0.5)
        assert result == 0

    def test_set_group_circadian(self, state_manager):
        """Test setting circadian values for a group."""
        state_manager.register_group(1)

        result = state_manager.set_group_circadian(1, 0.8, 4000)

        assert result is True
        assert state_manager.groups[1].circadian_brightness == 0.8
        assert state_manager.groups[1].circadian_color_temp == 4000

    def test_remove_fixture_from_group(self, state_manager):
        """Test removing a fixture from a group."""
        state_manager.register_fixture(1)
        state_manager.register_group(1)
        state_manager.add_fixture_to_group(1, 1)

        result = state_manager.remove_fixture_from_group(1, 1)

        assert result is True
        assert 1 not in state_manager.fixture_group_memberships[1]

    def test_remove_fixture_from_group_not_member(self, state_manager):
        """Test removing fixture that's not in the group returns False."""
        state_manager.register_fixture(1)
        state_manager.register_group(1)
        # Don't add fixture to group

        result = state_manager.remove_fixture_from_group(1, 1)

        assert result is False

    def test_remove_fixture_from_group_fixture_not_registered(self, state_manager):
        """Test removing unregistered fixture returns False."""
        state_manager.register_group(1)

        result = state_manager.remove_fixture_from_group(999, 1)

        assert result is False

    def test_remove_fixture_from_one_group_keeps_others(self, state_manager):
        """Test removing from one group doesn't affect other memberships."""
        state_manager.register_fixture(1)
        state_manager.register_group(1)
        state_manager.register_group(2)
        state_manager.add_fixture_to_group(1, 1)
        state_manager.add_fixture_to_group(1, 2)

        state_manager.remove_fixture_from_group(1, 1)

        # Should still be in group 2
        assert 1 not in state_manager.fixture_group_memberships[1]
        assert 2 in state_manager.fixture_group_memberships[1]

    def test_unregister_group(self, state_manager):
        """Test unregistering a group."""
        state_manager.register_group(1)

        result = state_manager.unregister_group(1)

        assert result is True
        assert 1 not in state_manager.groups

    def test_unregister_group_not_found(self, state_manager):
        """Test unregistering non-existent group returns False."""
        result = state_manager.unregister_group(999)

        assert result is False

    def test_unregister_group_removes_memberships(self, state_manager):
        """Test unregistering group removes it from all fixture memberships."""
        state_manager.register_fixture(1)
        state_manager.register_fixture(2)
        state_manager.register_group(1)
        state_manager.register_group(2)
        state_manager.add_fixture_to_group(1, 1)
        state_manager.add_fixture_to_group(2, 1)
        state_manager.add_fixture_to_group(1, 2)

        state_manager.unregister_group(1)

        # Group 1 should be removed from all fixtures
        assert 1 not in state_manager.fixture_group_memberships[1]
        assert 1 not in state_manager.fixture_group_memberships[2]
        # Group 2 membership should still exist
        assert 2 in state_manager.fixture_group_memberships[1]

    def test_removed_fixture_not_affected_by_group_brightness(self, state_manager):
        """Test that a removed fixture is not affected by group brightness changes."""
        state_manager.register_fixture(1)
        state_manager.register_fixture(2)
        state_manager.register_group(1)
        state_manager.add_fixture_to_group(1, 1)
        state_manager.add_fixture_to_group(2, 1)

        # Set initial brightness
        state_manager.set_fixture_brightness(1, 0.5)
        state_manager.set_fixture_brightness(2, 0.5)

        # Remove fixture 1 from group
        state_manager.remove_fixture_from_group(1, 1)

        # Change group brightness
        state_manager.set_group_brightness(1, 1.0)

        # Fixture 1 should not have changed (still 0.5)
        assert state_manager.fixtures[1].goal_brightness == 0.5
        # Fixture 2 should have changed
        assert state_manager.fixtures[2].goal_brightness == 1.0


class TestStateManagerEffectiveState:
    """Tests for effective state calculation with groups and circadian."""

    def test_effective_state_no_groups(self, state_manager):
        """Test effective state for fixture not in any groups."""
        state_manager.register_fixture(1)
        state_manager.set_fixture_brightness(1, 0.8, transition_duration=0.0)
        state_manager.set_fixture_color_temp(1, 4000, transition_duration=0.0)

        effective = state_manager.get_effective_fixture_state(1)

        assert effective.current_brightness == 0.8
        assert effective.current_color_temp == 4000

    def test_effective_state_with_group_brightness(self, populated_state_manager):
        """Test effective state with group brightness multiplier."""
        sm = populated_state_manager

        # Set fixture brightness to 1.0
        sm.set_fixture_brightness(1, 1.0)

        # Set group brightness to 0.5
        sm.set_group_brightness(1, 0.5)

        effective = sm.get_effective_fixture_state(1)

        # Effective brightness = 1.0 * 0.5 = 0.5
        assert effective.current_brightness == 0.5

    def test_effective_state_with_circadian(self, populated_state_manager):
        """Test effective state with circadian enabled."""
        sm = populated_state_manager

        # Set fixture brightness to 1.0
        sm.set_fixture_brightness(1, 1.0)
        sm.set_fixture_color_temp(1, 6500)

        # Enable circadian on group
        sm.groups[1].circadian_enabled = True
        sm.set_group_circadian(1, 0.5, 3000)  # 50% brightness, 3000K
        sm.set_group_brightness(1, 1.0)

        effective = sm.get_effective_fixture_state(1)

        # Effective brightness = 1.0 * 1.0 * 0.5 = 0.5
        assert effective.current_brightness == 0.5
        # Color temp overridden by circadian
        assert effective.current_color_temp == 3000


class TestStateManagerStatistics:
    """Tests for state manager statistics."""

    def test_get_statistics_empty(self, state_manager):
        """Test statistics for empty state manager."""
        stats = state_manager.get_statistics()

        assert stats["fixture_count"] == 0
        assert stats["group_count"] == 0
        assert stats["dirty"] is False

    def test_get_statistics_populated(self, populated_state_manager):
        """Test statistics for populated state manager."""
        stats = populated_state_manager.get_statistics()

        assert stats["fixture_count"] == 3
        assert stats["group_count"] == 2
        assert stats["dirty"] is False

    def test_mark_clean(self, state_manager):
        """Test marking state as clean."""
        state_manager.register_fixture(1)
        state_manager.set_fixture_brightness(1, 0.5)

        assert state_manager.dirty is True

        state_manager.mark_clean()

        assert state_manager.dirty is False

    def test_clear(self, populated_state_manager):
        """Test clearing all state."""
        sm = populated_state_manager
        sm.set_fixture_brightness(1, 0.5)

        sm.clear()

        assert len(sm.fixtures) == 0
        assert len(sm.groups) == 0
        assert len(sm.fixture_group_memberships) == 0
        assert sm.dirty is False


class TestLerp:
    """Tests for linear interpolation helper."""

    def test_lerp_start(self, state_manager):
        """Test lerp at t=0 returns start value."""
        result = state_manager._lerp(0.0, 1.0, 0.0)
        assert result == 0.0

    def test_lerp_end(self, state_manager):
        """Test lerp at t=1 returns end value."""
        result = state_manager._lerp(0.0, 1.0, 1.0)
        assert result == 1.0

    def test_lerp_midpoint(self, state_manager):
        """Test lerp at t=0.5 returns midpoint."""
        result = state_manager._lerp(0.0, 100.0, 0.5)
        assert result == 50.0

    def test_lerp_quarter(self, state_manager):
        """Test lerp at t=0.25."""
        result = state_manager._lerp(100.0, 200.0, 0.25)
        assert result == 125.0
