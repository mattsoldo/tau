"""
Control API Routes - Direct fixture and group control
"""
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

router = APIRouter()


@router.post("/fixtures/{fixture_id}")
async def control_fixture(
    fixture_id: int,
    control_data: FixtureControlRequest
):
    """Control a specific fixture"""
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

    # Apply controls with optional transition
    updated = False
    transition = control_data.transition_duration

    if control_data.brightness is not None:
        success = daemon.state_manager.set_fixture_brightness(
            fixture_id,
            control_data.brightness,
            transition_duration=transition
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to set brightness")
        updated = True

    if control_data.color_temp is not None:
        success = daemon.state_manager.set_fixture_color_temp(
            fixture_id,
            control_data.color_temp,
            transition_duration=transition
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to set color temperature")
        updated = True

    if not updated:
        raise HTTPException(status_code=400, detail="No control values provided")

    # Get updated state
    state = daemon.state_manager.get_fixture_state(fixture_id)

    # Broadcast state change via WebSocket (goal values for UI)
    await broadcast_fixture_state_change(
        fixture_id=fixture_id,
        brightness=state.goal_brightness,
        color_temp=state.goal_color_temp
    )

    # Return both goal and current state
    return {
        "message": "Fixture control applied successfully",
        "goal_brightness": state.goal_brightness,
        "goal_color_temp": state.goal_color_temp,
        "current_brightness": state.current_brightness,
        "current_color_temp": state.current_color_temp,
        "transitioning": state.transition_start is not None,
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
        success = daemon.state_manager.set_group_brightness(
            group_id,
            control_data.brightness
        )
        if not success:
            raise HTTPException(status_code=500, detail="Failed to set brightness")
        updated = True

    if control_data.color_temp is not None:
        # Note: Group color temp would need to be implemented in StateManager
        # For now, apply to circadian color temp if circadian is enabled
        group_state = daemon.state_manager.get_group_state(group_id)
        if group_state.circadian_enabled:
            success = daemon.state_manager.set_group_circadian(
                group_id,
                group_state.circadian_brightness,
                control_data.color_temp
            )
            if not success:
                raise HTTPException(status_code=500, detail="Failed to set color temperature")
        updated = True

    if not updated:
        raise HTTPException(status_code=400, detail="No control values provided")

    # Broadcast state change via WebSocket
    group_state = daemon.state_manager.get_group_state(group_id)
    await broadcast_group_state_change(
        group_id=group_id,
        brightness=group_state.brightness,
        color_temp=group_state.circadian_color_temp if group_state.circadian_enabled else None
    )

    return {"message": "Group control applied successfully"}


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
