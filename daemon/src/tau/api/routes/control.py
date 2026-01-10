"""
Control API Routes - Direct fixture and group control
"""
from typing import Optional
from fastapi import APIRouter, HTTPException
from tau.api.schemas import (
    FixtureControlRequest,
    GroupControlRequest,
    CircadianControlRequest,
)
from tau.api import get_daemon_instance
from tau.api.websocket import (
    broadcast_fixture_state_change,
    broadcast_group_state_change,
    broadcast_circadian_change,
)
from tau.logic.transitions import EasingFunction

router = APIRouter()


def parse_easing(easing_str: Optional[str]) -> Optional[EasingFunction]:
    """Parse easing string to EasingFunction enum."""
    if easing_str is None:
        return None
    try:
        return EasingFunction(easing_str)
    except ValueError:
        return None


@router.post("/fixtures/{fixture_id}")
async def control_fixture(
    fixture_id: int,
    control_data: FixtureControlRequest
):
    """Control a specific fixture with optional transition and easing.

    Transition duration can be:
    - Explicit value in seconds (0 = instant)
    - None with use_proportional_time=True: calculates duration based on change amount
    - None with use_proportional_time=False: instant change

    Easing defaults to ease_in_out for smooth transitions.
    """
    daemon = get_daemon_instance()
    if not daemon or not daemon.state_manager:
        raise HTTPException(
            status_code=503,
            detail="State manager not available"
        )

    # Verify fixture exists
    state = daemon.state_manager.get_fixture_state(fixture_id)
    if not state:
        raise HTTPException(status_code=404, detail="Fixture not found")

    # Parse easing function
    easing = parse_easing(control_data.easing)

    # Apply controls with optional transition and easing
    updated = False

    if control_data.brightness is not None:
        success = daemon.state_manager.set_fixture_brightness(
            fixture_id,
            control_data.brightness,
            transition_duration=control_data.transition_duration,
            easing=easing,
            use_proportional_time=control_data.use_proportional_time
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to set brightness")
        updated = True

    if control_data.color_temp is not None:
        success = daemon.state_manager.set_fixture_color_temp(
            fixture_id,
            control_data.color_temp,
            transition_duration=control_data.transition_duration,
            easing=easing,
            use_proportional_time=control_data.use_proportional_time
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to set color temperature")
        updated = True

    if control_data.cct_mode is not None:
        if control_data.cct_mode == "dim_to_warm":
            success = daemon.state_manager.set_fixture_cct_mode_auto(fixture_id)
            if not success:
                raise HTTPException(status_code=500, detail="Failed to set CCT mode")
        updated = True

    if not updated:
        raise HTTPException(status_code=400, detail="No control values provided")

    # Set override flag - individual fixture control bypasses group/circadian
    daemon.state_manager.set_fixture_override(
        fixture_id,
        source="fixture",
        expiry_hours=8.0
    )

    # Get updated state
    state = daemon.state_manager.get_fixture_state(fixture_id)

    # Broadcast state change via WebSocket (goal values for UI)
    await broadcast_fixture_state_change(
        fixture_id=fixture_id,
        brightness=state.goal_brightness,
        color_temp=state.goal_color_temp
    )

    # Return both goal and current state, including override info
    return {
        "message": "Fixture control applied successfully",
        "goal_brightness": state.goal_brightness,
        "goal_color_temp": state.goal_color_temp,
        "current_brightness": state.current_brightness,
        "current_color_temp": state.current_color_temp,
        "transitioning": state.is_brightness_transitioning or state.is_cct_transitioning,
        "brightness_transitioning": state.is_brightness_transitioning,
        "cct_transitioning": state.is_cct_transitioning,
        "override_active": state.override_active,
        "override_expires_at": state.override_expires_at,
    }


@router.post("/groups/{group_id}")
async def control_group(
    group_id: int,
    control_data: GroupControlRequest
):
    """Control all fixtures in a group"""
    daemon = get_daemon_instance()
    if not daemon or not daemon.state_manager:
        raise HTTPException(
            status_code=503,
            detail="State manager not available"
        )

    # Verify group exists
    state = daemon.state_manager.get_group_state(group_id)
    if not state:
        raise HTTPException(status_code=404, detail="Group not found")

    # Apply controls
    updated = False

    if control_data.brightness is not None:
        # Set brightness for all fixtures in the group
        transition = control_data.transition_duration
        fixtures_updated = daemon.state_manager.set_group_brightness(
            group_id,
            control_data.brightness,
            transition_duration=transition,
        )
        if fixtures_updated == 0:
            raise HTTPException(status_code=400, detail="No fixtures in group to update")
        updated = True

    if control_data.color_temp is not None:
        # Set CCT for all fixtures in the group directly
        transition = control_data.transition_duration
        fixtures_updated = daemon.state_manager.set_group_color_temp(
            group_id,
            control_data.color_temp,
            transition_duration=transition,
        )
        if fixtures_updated == 0:
            raise HTTPException(status_code=400, detail="No fixtures in group to update")
        updated = True

    if control_data.cct_mode is not None:
        if control_data.cct_mode == "dim_to_warm":
            fixtures_updated = daemon.state_manager.set_group_cct_mode_auto(group_id)
            if fixtures_updated == 0:
                raise HTTPException(status_code=400, detail="No fixtures in group to update")
        updated = True

    if not updated:
        raise HTTPException(status_code=400, detail="No control values provided")

    # Clear individual fixture overrides - group control takes over
    overrides_cleared = daemon.state_manager.clear_group_overrides(group_id)

    # Broadcast state change via WebSocket
    group_state = daemon.state_manager.get_group_state(group_id)
    await broadcast_group_state_change(
        group_id=group_id,
        brightness=group_state.brightness,
        color_temp=group_state.circadian_color_temp if group_state.circadian_enabled else None
    )

    return {
        "message": "Group control applied successfully",
        "overrides_cleared": overrides_cleared
    }


@router.post("/groups/{group_id}/circadian")
async def control_group_circadian(
    group_id: int,
    control_data: CircadianControlRequest
):
    """Enable or disable circadian rhythm for a group"""
    daemon = get_daemon_instance()
    if not daemon or not daemon.lighting_controller:
        raise HTTPException(
            status_code=503,
            detail="Lighting controller not available"
        )

    if control_data.enabled:
        success = await daemon.lighting_controller.enable_circadian(group_id)
        if not success:
            raise HTTPException(
                status_code=400,
                detail="Failed to enable circadian (check if profile is assigned)"
            )

        # Broadcast circadian enabled
        group_state = daemon.state_manager.get_group_state(group_id)
        await broadcast_circadian_change(
            group_id=group_id,
            enabled=True,
            brightness=group_state.circadian_brightness if group_state else None,
            color_temp=group_state.circadian_color_temp if group_state else None
        )

        return {"message": "Circadian enabled successfully"}
    else:
        success = await daemon.lighting_controller.disable_circadian(group_id)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to disable circadian")

        # Broadcast circadian disabled
        await broadcast_circadian_change(
            group_id=group_id,
            enabled=False
        )

        return {"message": "Circadian disabled successfully"}


@router.post("/all-off")
async def all_off():
    """Turn off all fixtures"""
    daemon = get_daemon_instance()
    if not daemon or not daemon.state_manager:
        raise HTTPException(
            status_code=503,
            detail="State manager not available"
        )

    # Set all fixtures to 0 brightness
    count = 0
    for fixture_id in daemon.state_manager.fixtures.keys():
        success = daemon.state_manager.set_fixture_brightness(fixture_id, 0.0)
        if success:
            count += 1

    return {
        "message": f"Turned off {count} fixtures",
        "count": count
    }


@router.post("/panic")
async def panic_mode():
    """Emergency full bright mode - turn all fixtures to 100%"""
    daemon = get_daemon_instance()
    if not daemon or not daemon.state_manager:
        raise HTTPException(
            status_code=503,
            detail="State manager not available"
        )

    # Set all fixtures to 100% brightness
    count = 0
    for fixture_id in daemon.state_manager.fixtures.keys():
        success = daemon.state_manager.set_fixture_brightness(fixture_id, 1.0)
        if success:
            count += 1

    return {
        "message": f"Panic mode: {count} fixtures at full brightness",
        "count": count
    }


# === Override Management Endpoints ===

@router.get("/overrides")
async def get_active_overrides():
    """Get list of all active fixture overrides"""
    daemon = get_daemon_instance()
    if not daemon or not daemon.state_manager:
        raise HTTPException(
            status_code=503,
            detail="State manager not available"
        )

    overrides = daemon.state_manager.get_active_overrides()
    return {
        "count": len(overrides),
        "overrides": overrides
    }


@router.delete("/overrides/fixtures/{fixture_id}")
async def remove_fixture_override(fixture_id: int):
    """Remove override from a specific fixture (returns to circadian control)"""
    daemon = get_daemon_instance()
    if not daemon or not daemon.state_manager:
        raise HTTPException(
            status_code=503,
            detail="State manager not available"
        )

    # Verify fixture exists
    state = daemon.state_manager.get_fixture_state(fixture_id)
    if not state:
        raise HTTPException(status_code=404, detail="Fixture not found")

    was_active = state.override_active
    daemon.state_manager.clear_fixture_override(fixture_id)

    # Broadcast state change
    await broadcast_fixture_state_change(
        fixture_id=fixture_id,
        brightness=state.goal_brightness,
        color_temp=state.goal_color_temp
    )

    return {
        "message": "Override removed" if was_active else "No override was active",
        "fixture_id": fixture_id,
        "was_active": was_active
    }


@router.delete("/overrides/all")
async def remove_all_overrides():
    """Remove all active overrides (returns all fixtures to circadian control)"""
    daemon = get_daemon_instance()
    if not daemon or not daemon.state_manager:
        raise HTTPException(
            status_code=503,
            detail="State manager not available"
        )

    # Get list of fixtures with active overrides before clearing
    active_fixtures = [
        f.fixture_id
        for f in daemon.state_manager.fixtures.values()
        if f.override_active
    ]

    # Clear all overrides
    cleared_count = 0
    for fixture_id in active_fixtures:
        daemon.state_manager.clear_fixture_override(fixture_id)
        cleared_count += 1

        # Broadcast state change for each fixture
        state = daemon.state_manager.get_fixture_state(fixture_id)
        await broadcast_fixture_state_change(
            fixture_id=fixture_id,
            brightness=state.goal_brightness,
            color_temp=state.goal_color_temp
        )

    return {
        "message": f"Removed {cleared_count} overrides",
        "cleared_count": cleared_count
    }
