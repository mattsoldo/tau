"""
API Schemas - Pydantic models for request/response validation
"""
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


# Fixture Schemas
class FixtureModelBase(BaseModel):
    manufacturer: str = Field(..., max_length=100)
    model: str = Field(..., max_length=100)
    description: Optional[str] = None
    type: str = Field(..., pattern="^(simple_dimmable|tunable_white|dim_to_warm|non_dimmable|other)$")
    dmx_footprint: int = Field(default=1, ge=1, le=512)
    cct_min_kelvin: Optional[int] = Field(default=1800, ge=1000, le=10000)
    cct_max_kelvin: Optional[int] = Field(default=4000, ge=1000, le=10000)
    # Planckian Locus Color Mixing Parameters (for tunable_white)
    warm_xy_x: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    warm_xy_y: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    cool_xy_x: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    cool_xy_y: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    warm_lumens: Optional[int] = Field(default=None, ge=1, le=100000)
    cool_lumens: Optional[int] = Field(default=None, ge=1, le=100000)
    gamma: Optional[float] = Field(default=2.2, ge=1.0, le=4.0)


class FixtureModelCreate(FixtureModelBase):
    pass


class FixtureModelUpdate(BaseModel):
    manufacturer: Optional[str] = Field(None, max_length=100)
    model: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    type: Optional[str] = Field(None, pattern="^(simple_dimmable|tunable_white|dim_to_warm|non_dimmable|other)$")
    dmx_footprint: Optional[int] = Field(None, ge=1, le=512)
    cct_min_kelvin: Optional[int] = Field(None, ge=1000, le=10000)
    cct_max_kelvin: Optional[int] = Field(None, ge=1000, le=10000)
    # Planckian Locus Color Mixing Parameters (for tunable_white)
    warm_xy_x: Optional[float] = Field(None, ge=0.0, le=1.0)
    warm_xy_y: Optional[float] = Field(None, ge=0.0, le=1.0)
    cool_xy_x: Optional[float] = Field(None, ge=0.0, le=1.0)
    cool_xy_y: Optional[float] = Field(None, ge=0.0, le=1.0)
    warm_lumens: Optional[int] = Field(None, ge=1, le=100000)
    cool_lumens: Optional[int] = Field(None, ge=1, le=100000)
    gamma: Optional[float] = Field(None, ge=1.0, le=4.0)


class FixtureModelResponse(FixtureModelBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class FixtureBase(BaseModel):
    name: str = Field(..., max_length=100)
    fixture_model_id: int = Field(..., gt=0)
    dmx_channel_start: int = Field(..., ge=1, le=512)
    secondary_dmx_channel: Optional[int] = Field(None, ge=1, le=512)


class FixtureCreate(FixtureBase):
    pass


class FixtureUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    fixture_model_id: Optional[int] = Field(None, gt=0)
    dmx_channel_start: Optional[int] = Field(None, ge=1, le=512)
    secondary_dmx_channel: Optional[int] = Field(None, ge=1, le=512)


class FixtureMergeRequest(BaseModel):
    """Request to merge two fixtures into one tunable white fixture"""
    primary_fixture_id: int = Field(..., gt=0, description="Fixture to keep")
    secondary_fixture_id: int = Field(..., gt=0, description="Fixture to merge in (will be deleted)")
    target_model_id: Optional[int] = Field(None, gt=0, description="Optional tunable white model to apply")


class FixtureResponse(FixtureBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class FixtureStateResponse(BaseModel):
    fixture_id: int
    current_brightness: int = Field(..., ge=0, le=1000)
    current_cct: Optional[int] = Field(None, ge=1000, le=10000)
    is_on: bool
    last_updated: datetime

    class Config:
        from_attributes = True


# Group Schemas
class GroupBase(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    circadian_enabled: bool = False
    circadian_profile_id: Optional[int] = None


class GroupCreate(GroupBase):
    pass


class GroupUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    circadian_enabled: Optional[bool] = None
    circadian_profile_id: Optional[int] = None


class GroupResponse(GroupBase):
    id: int
    is_system: Optional[bool] = False
    created_at: datetime

    class Config:
        from_attributes = True


class GroupFixtureAdd(BaseModel):
    fixture_id: int = Field(..., gt=0)


class GroupStateResponse(BaseModel):
    group_id: int
    circadian_suspended: bool
    circadian_suspended_at: Optional[datetime] = None
    last_active_scene_id: Optional[int] = None

    class Config:
        from_attributes = True


# Scene Schemas
class SceneBase(BaseModel):
    name: str = Field(..., max_length=100)
    scope_group_id: Optional[int] = None


class SceneCreate(SceneBase):
    pass


class SceneUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)


class SceneValueResponse(BaseModel):
    fixture_id: int
    target_brightness: Optional[int] = Field(None, ge=0, le=1000)
    target_cct_kelvin: Optional[int] = Field(None, ge=1000, le=10000)

    class Config:
        from_attributes = True


class SceneResponse(SceneBase):
    id: int
    values: List[SceneValueResponse] = []

    class Config:
        from_attributes = True


class SceneCaptureRequest(BaseModel):
    name: str = Field(..., max_length=100)
    fixture_ids: Optional[List[int]] = None
    scope_group_id: Optional[int] = None


class SceneRecallRequest(BaseModel):
    scene_id: int = Field(..., gt=0)
    fade_duration: float = Field(default=0.0, ge=0.0, le=10.0)


# Control Schemas
class FixtureControlRequest(BaseModel):
    brightness: Optional[float] = Field(None, ge=0.0, le=1.0)
    color_temp: Optional[int] = Field(None, ge=1000, le=10000)
    transition_duration: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=60.0,
        description="Transition time in seconds. If None, uses proportional time based on change amount. If 0, instant change."
    )
    easing: Optional[str] = Field(
        default=None,
        pattern="^(linear|ease_in|ease_out|ease_in_out|ease_in_cubic|ease_out_cubic|ease_in_out_cubic)$",
        description="Easing function for transition. Defaults to ease_in_out."
    )
    use_proportional_time: bool = Field(
        default=True,
        description="If True and transition_duration is None, calculate duration based on amount of change"
    )


class GroupControlRequest(BaseModel):
    brightness: Optional[float] = Field(None, ge=0.0, le=1.0)
    color_temp: Optional[int] = Field(None, ge=1000, le=10000)
    transition_duration: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=60.0,
        description="Transition time in seconds. If None, uses proportional time based on change amount. If 0, instant change."
    )
    easing: Optional[str] = Field(
        default=None,
        pattern="^(linear|ease_in|ease_out|ease_in_out|ease_in_cubic|ease_out_cubic|ease_in_out_cubic)$",
        description="Easing function for transition. Defaults to ease_in_out."
    )
    use_proportional_time: bool = Field(
        default=True,
        description="If True and transition_duration is None, calculate duration based on amount of change"
    )


class CircadianControlRequest(BaseModel):
    enabled: bool


# Circadian Profile Schemas
class CircadianKeyframeSchema(BaseModel):
    time: str = Field(..., pattern="^([0-1][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]$")
    brightness: float = Field(..., ge=0.0, le=1.0)
    cct: int = Field(..., ge=1000, le=10000)


class CircadianProfileBase(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = None
    keyframes: List[CircadianKeyframeSchema] = Field(..., min_length=2)


class CircadianProfileCreate(CircadianProfileBase):
    pass


class CircadianProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    keyframes: Optional[List[CircadianKeyframeSchema]] = Field(None, min_length=2)


class CircadianProfileResponse(CircadianProfileBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# Switch Model Schemas
class SwitchModelBase(BaseModel):
    manufacturer: str = Field(..., max_length=100)
    model: str = Field(..., max_length=100)
    input_type: str = Field(..., pattern="^(retractive|rotary_abs|paddle_composite|switch_simple)$")
    debounce_ms: Optional[int] = Field(default=500, ge=0, le=10000)
    dimming_curve: Optional[str] = Field(default="logarithmic", pattern="^(linear|logarithmic)$")
    requires_digital_pin: Optional[bool] = Field(default=True)
    requires_analog_pin: Optional[bool] = Field(default=False)


class SwitchModelCreate(SwitchModelBase):
    pass


class SwitchModelUpdate(BaseModel):
    manufacturer: Optional[str] = Field(None, max_length=100)
    model: Optional[str] = Field(None, max_length=100)
    input_type: Optional[str] = Field(None, pattern="^(retractive|rotary_abs|paddle_composite|switch_simple)$")
    debounce_ms: Optional[int] = Field(None, ge=0, le=10000)
    dimming_curve: Optional[str] = Field(None, pattern="^(linear|logarithmic)$")
    requires_digital_pin: Optional[bool] = None
    requires_analog_pin: Optional[bool] = None


class SwitchModelResponse(SwitchModelBase):
    id: int

    class Config:
        from_attributes = True


# Switch Schemas
class SwitchBase(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    switch_model_id: int = Field(..., gt=0)
    labjack_digital_pin: Optional[int] = Field(None, ge=0, le=15)
    labjack_analog_pin: Optional[int] = Field(None, ge=0, le=15)
    target_group_id: Optional[int] = None
    target_fixture_id: Optional[int] = None
    photo_url: Optional[str] = None


class SwitchCreate(SwitchBase):
    pass


class SwitchUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    switch_model_id: Optional[int] = Field(None, gt=0)
    labjack_digital_pin: Optional[int] = Field(None, ge=0, le=15)
    labjack_analog_pin: Optional[int] = Field(None, ge=0, le=15)
    target_group_id: Optional[int] = None
    target_fixture_id: Optional[int] = None
    photo_url: Optional[str] = None


class SwitchResponse(SwitchBase):
    id: int

    class Config:
        from_attributes = True


# Status Response
class SystemStatusResponse(BaseModel):
    status: str
    version: str
    service: str
    event_loop: Optional[dict] = None
    scheduled_tasks: Optional[dict] = None
    state_manager: Optional[dict] = None
    persistence: Optional[dict] = None
    hardware: Optional[dict] = None
    lighting: Optional[dict] = None
