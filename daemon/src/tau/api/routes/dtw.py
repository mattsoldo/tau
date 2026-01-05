"""
DTW API Routes - Dim-to-warm configuration and override management
"""
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
import structlog

from tau.database import get_db_session
from tau.models.system_settings import SystemSetting
from tau.models.override import Override
from tau.models.fixtures import Fixture
from tau.models.groups import Group
from tau.models.dtw_helper import (
    get_dtw_settings,
    clear_dtw_settings_cache,
    get_active_cct_override,
    create_dtw_override,
    cancel_dtw_override,
    cancel_all_overrides_for_target,
    cleanup_expired_overrides,
    DTWSettings,
)
from tau.logic.dtw import DTWCurve, get_example_values
from sqlalchemy import select, and_

logger = structlog.get_logger(__name__)

router = APIRouter()


# ============================================================================
# DTW System Settings API
# ============================================================================

class DTWSettingsResponse(BaseModel):
    """Response model for DTW system settings."""
    enabled: bool = Field(..., description="Whether DTW is enabled globally")
    min_cct: int = Field(..., description="Minimum CCT at lowest brightness (Kelvin)")
    max_cct: int = Field(..., description="Maximum CCT at full brightness (Kelvin)")
    min_brightness: float = Field(..., description="Brightness floor for DTW curve (0.0-1.0)")
    curve: str = Field(..., description="DTW curve type (linear, log, square, incandescent)")
    override_timeout: int = Field(..., description="Override timeout in seconds")

    class Config:
        from_attributes = True


class DTWSettingsUpdateRequest(BaseModel):
    """Request model for updating DTW settings."""
    enabled: Optional[bool] = Field(None, description="Enable/disable DTW globally")
    min_cct: Optional[int] = Field(None, ge=1000, le=10000, description="Minimum CCT (Kelvin)")
    max_cct: Optional[int] = Field(None, ge=1000, le=10000, description="Maximum CCT (Kelvin)")
    min_brightness: Optional[float] = Field(None, ge=0.0, le=1.0, description="Brightness floor")
    curve: Optional[str] = Field(None, description="Curve type")
    override_timeout: Optional[int] = Field(None, ge=0, description="Override timeout (seconds)")


class DTWExampleValue(BaseModel):
    """Example CCT value at a given brightness."""
    brightness: float
    cct: int


class DTWCurveInfoResponse(BaseModel):
    """Information about DTW curves."""
    available_curves: List[str]
    current_curve: str
    example_values: List[DTWExampleValue]


@router.get(
    "/settings",
    response_model=DTWSettingsResponse,
    summary="Get DTW Settings",
    description="Get current dim-to-warm system configuration"
)
async def get_dtw_system_settings():
    """Get all DTW system settings."""
    try:
        settings = await get_dtw_settings(use_cache=False)
        return DTWSettingsResponse(
            enabled=settings.enabled,
            min_cct=settings.min_cct,
            max_cct=settings.max_cct,
            min_brightness=settings.min_brightness,
            curve=settings.curve.value,
            override_timeout=settings.override_timeout
        )
    except Exception as e:
        logger.error("get_dtw_settings_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch DTW settings: {str(e)}")


@router.put(
    "/settings",
    response_model=DTWSettingsResponse,
    summary="Update DTW Settings",
    description="Update dim-to-warm system configuration"
)
async def update_dtw_system_settings(update: DTWSettingsUpdateRequest):
    """Update DTW system settings."""
    async with get_db_session() as session:
        try:
            # Validate min_cct < max_cct if both provided
            if update.min_cct is not None and update.max_cct is not None:
                if update.min_cct >= update.max_cct:
                    raise HTTPException(
                        status_code=400,
                        detail="min_cct must be less than max_cct"
                    )

            # Validate curve if provided
            if update.curve is not None:
                try:
                    DTWCurve(update.curve.lower())
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid curve type. Must be one of: linear, log, square, incandescent"
                    )

            # Update each setting that was provided
            settings_map = {
                'dtw_enabled': ('bool', update.enabled),
                'dtw_min_cct': ('int', update.min_cct),
                'dtw_max_cct': ('int', update.max_cct),
                'dtw_min_brightness': ('float', update.min_brightness),
                'dtw_curve': ('str', update.curve.lower() if update.curve else None),
                'dtw_override_timeout': ('int', update.override_timeout),
            }

            for key, (_, value) in settings_map.items():
                if value is not None:
                    result = await session.execute(
                        select(SystemSetting).where(SystemSetting.key == key)
                    )
                    setting = result.scalar_one_or_none()
                    if setting:
                        setting.value = str(value).lower() if isinstance(value, bool) else str(value)

            await session.commit()

            # Clear the cache
            clear_dtw_settings_cache()

            # Return updated settings
            settings = await get_dtw_settings(session, use_cache=False)
            return DTWSettingsResponse(
                enabled=settings.enabled,
                min_cct=settings.min_cct,
                max_cct=settings.max_cct,
                min_brightness=settings.min_brightness,
                curve=settings.curve.value,
                override_timeout=settings.override_timeout
            )

        except HTTPException:
            raise
        except Exception as e:
            await session.rollback()
            logger.error("update_dtw_settings_error", error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to update DTW settings: {str(e)}")


@router.get(
    "/curves",
    response_model=DTWCurveInfoResponse,
    summary="Get DTW Curve Info",
    description="Get available DTW curves and example values"
)
async def get_dtw_curve_info():
    """Get information about available DTW curves."""
    try:
        settings = await get_dtw_settings()

        # Get example values for current curve
        examples = get_example_values(
            min_cct=settings.min_cct,
            max_cct=settings.max_cct,
            curve=settings.curve
        )

        return DTWCurveInfoResponse(
            available_curves=[c.value for c in DTWCurve],
            current_curve=settings.curve.value,
            example_values=[
                DTWExampleValue(brightness=b, cct=cct)
                for b, cct in examples
            ]
        )
    except Exception as e:
        logger.error("get_dtw_curves_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch DTW curves: {str(e)}")


# ============================================================================
# Fixture DTW Settings API
# ============================================================================

class FixtureDTWSettingsResponse(BaseModel):
    """Response model for fixture DTW settings."""
    fixture_id: int
    dtw_ignore: bool
    dtw_min_cct_override: Optional[int]
    dtw_max_cct_override: Optional[int]
    has_active_override: bool
    override_cct: Optional[int]
    override_expires_at: Optional[datetime]


class FixtureDTWSettingsUpdateRequest(BaseModel):
    """Request model for updating fixture DTW settings."""
    dtw_ignore: Optional[bool] = Field(None, description="Exempt fixture from DTW")
    dtw_min_cct_override: Optional[int] = Field(None, ge=1000, le=10000, description="Per-fixture min CCT")
    dtw_max_cct_override: Optional[int] = Field(None, ge=1000, le=10000, description="Per-fixture max CCT")


@router.get(
    "/fixtures/{fixture_id}",
    response_model=FixtureDTWSettingsResponse,
    summary="Get Fixture DTW Settings",
    description="Get DTW configuration for a specific fixture"
)
async def get_fixture_dtw_settings(fixture_id: int):
    """Get DTW settings for a fixture."""
    async with get_db_session() as session:
        try:
            # Get fixture
            result = await session.execute(
                select(Fixture).where(Fixture.id == fixture_id)
            )
            fixture = result.scalar_one_or_none()

            if fixture is None:
                raise HTTPException(status_code=404, detail=f"Fixture {fixture_id} not found")

            # Check for active override
            override = await get_active_cct_override('fixture', fixture_id, session)

            return FixtureDTWSettingsResponse(
                fixture_id=fixture_id,
                dtw_ignore=fixture.dtw_ignore or False,
                dtw_min_cct_override=fixture.dtw_min_cct_override,
                dtw_max_cct_override=fixture.dtw_max_cct_override,
                has_active_override=override is not None,
                override_cct=int(override.value) if override else None,
                override_expires_at=override.expires_at if override else None
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error("get_fixture_dtw_error", fixture_id=fixture_id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to fetch fixture DTW settings: {str(e)}")


@router.put(
    "/fixtures/{fixture_id}",
    response_model=FixtureDTWSettingsResponse,
    summary="Update Fixture DTW Settings",
    description="Update DTW configuration for a specific fixture"
)
async def update_fixture_dtw_settings(fixture_id: int, update: FixtureDTWSettingsUpdateRequest):
    """Update DTW settings for a fixture."""
    async with get_db_session() as session:
        try:
            # Get fixture
            result = await session.execute(
                select(Fixture).where(Fixture.id == fixture_id)
            )
            fixture = result.scalar_one_or_none()

            if fixture is None:
                raise HTTPException(status_code=404, detail=f"Fixture {fixture_id} not found")

            # Validate min < max if both provided
            min_cct = update.dtw_min_cct_override if update.dtw_min_cct_override is not None else fixture.dtw_min_cct_override
            max_cct = update.dtw_max_cct_override if update.dtw_max_cct_override is not None else fixture.dtw_max_cct_override
            if min_cct is not None and max_cct is not None and min_cct >= max_cct:
                raise HTTPException(
                    status_code=400,
                    detail="dtw_min_cct_override must be less than dtw_max_cct_override"
                )

            # Update fields
            if update.dtw_ignore is not None:
                fixture.dtw_ignore = update.dtw_ignore
            if update.dtw_min_cct_override is not None:
                fixture.dtw_min_cct_override = update.dtw_min_cct_override
            if update.dtw_max_cct_override is not None:
                fixture.dtw_max_cct_override = update.dtw_max_cct_override

            await session.commit()

            # Check for active override
            override = await get_active_cct_override('fixture', fixture_id, session)

            return FixtureDTWSettingsResponse(
                fixture_id=fixture_id,
                dtw_ignore=fixture.dtw_ignore or False,
                dtw_min_cct_override=fixture.dtw_min_cct_override,
                dtw_max_cct_override=fixture.dtw_max_cct_override,
                has_active_override=override is not None,
                override_cct=int(override.value) if override else None,
                override_expires_at=override.expires_at if override else None
            )

        except HTTPException:
            raise
        except Exception as e:
            await session.rollback()
            logger.error("update_fixture_dtw_error", fixture_id=fixture_id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to update fixture DTW settings: {str(e)}")


# ============================================================================
# Group DTW Settings API
# ============================================================================

class GroupDTWSettingsResponse(BaseModel):
    """Response model for group DTW settings."""
    group_id: int
    dtw_ignore: bool
    dtw_min_cct_override: Optional[int]
    dtw_max_cct_override: Optional[int]
    has_active_override: bool
    override_cct: Optional[int]
    override_expires_at: Optional[datetime]


class GroupDTWSettingsUpdateRequest(BaseModel):
    """Request model for updating group DTW settings."""
    dtw_ignore: Optional[bool] = Field(None, description="Exempt group from DTW")
    dtw_min_cct_override: Optional[int] = Field(None, ge=1000, le=10000, description="Per-group min CCT")
    dtw_max_cct_override: Optional[int] = Field(None, ge=1000, le=10000, description="Per-group max CCT")


@router.get(
    "/groups/{group_id}",
    response_model=GroupDTWSettingsResponse,
    summary="Get Group DTW Settings",
    description="Get DTW configuration for a specific group"
)
async def get_group_dtw_settings(group_id: int):
    """Get DTW settings for a group."""
    async with get_db_session() as session:
        try:
            # Get group
            result = await session.execute(
                select(Group).where(Group.id == group_id)
            )
            group = result.scalar_one_or_none()

            if group is None:
                raise HTTPException(status_code=404, detail=f"Group {group_id} not found")

            # Check for active override
            override = await get_active_cct_override('group', group_id, session)

            return GroupDTWSettingsResponse(
                group_id=group_id,
                dtw_ignore=group.dtw_ignore or False,
                dtw_min_cct_override=group.dtw_min_cct_override,
                dtw_max_cct_override=group.dtw_max_cct_override,
                has_active_override=override is not None,
                override_cct=int(override.value) if override else None,
                override_expires_at=override.expires_at if override else None
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error("get_group_dtw_error", group_id=group_id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to fetch group DTW settings: {str(e)}")


@router.put(
    "/groups/{group_id}",
    response_model=GroupDTWSettingsResponse,
    summary="Update Group DTW Settings",
    description="Update DTW configuration for a specific group"
)
async def update_group_dtw_settings(group_id: int, update: GroupDTWSettingsUpdateRequest):
    """Update DTW settings for a group."""
    async with get_db_session() as session:
        try:
            # Get group
            result = await session.execute(
                select(Group).where(Group.id == group_id)
            )
            group = result.scalar_one_or_none()

            if group is None:
                raise HTTPException(status_code=404, detail=f"Group {group_id} not found")

            # Validate min < max if both provided
            min_cct = update.dtw_min_cct_override if update.dtw_min_cct_override is not None else group.dtw_min_cct_override
            max_cct = update.dtw_max_cct_override if update.dtw_max_cct_override is not None else group.dtw_max_cct_override
            if min_cct is not None and max_cct is not None and min_cct >= max_cct:
                raise HTTPException(
                    status_code=400,
                    detail="dtw_min_cct_override must be less than dtw_max_cct_override"
                )

            # Update fields
            if update.dtw_ignore is not None:
                group.dtw_ignore = update.dtw_ignore
            if update.dtw_min_cct_override is not None:
                group.dtw_min_cct_override = update.dtw_min_cct_override
            if update.dtw_max_cct_override is not None:
                group.dtw_max_cct_override = update.dtw_max_cct_override

            await session.commit()

            # Check for active override
            override = await get_active_cct_override('group', group_id, session)

            return GroupDTWSettingsResponse(
                group_id=group_id,
                dtw_ignore=group.dtw_ignore or False,
                dtw_min_cct_override=group.dtw_min_cct_override,
                dtw_max_cct_override=group.dtw_max_cct_override,
                has_active_override=override is not None,
                override_cct=int(override.value) if override else None,
                override_expires_at=override.expires_at if override else None
            )

        except HTTPException:
            raise
        except Exception as e:
            await session.rollback()
            logger.error("update_group_dtw_error", group_id=group_id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to update group DTW settings: {str(e)}")


# ============================================================================
# Override Management API
# ============================================================================

class OverrideResponse(BaseModel):
    """Response model for an override."""
    id: int
    target_type: str
    target_id: int
    override_type: str
    property: str
    value: str
    created_at: datetime
    expires_at: datetime
    source: str
    time_remaining_seconds: Optional[float]

    class Config:
        from_attributes = True


class OverrideCreateRequest(BaseModel):
    """Request model for creating an override."""
    target_type: str = Field(..., description="Target type ('fixture' or 'group')")
    target_id: int = Field(..., description="Target ID")
    property: str = Field(default="cct", description="Property to override (default: 'cct')")
    value: int = Field(..., description="Override value (CCT in Kelvin)")
    timeout_seconds: Optional[int] = Field(None, ge=0, description="Override timeout (uses system default if not specified)")


@router.get(
    "/overrides",
    response_model=List[OverrideResponse],
    summary="List Overrides",
    description="Get all active overrides, optionally filtered"
)
async def list_overrides(
    target_type: Optional[str] = Query(None, description="Filter by target type"),
    target_id: Optional[int] = Query(None, description="Filter by target ID"),
    active_only: bool = Query(True, description="Only return non-expired overrides")
):
    """List all overrides."""
    async with get_db_session() as session:
        try:
            query = select(Override)

            # Build filters
            filters = []
            if target_type:
                filters.append(Override.target_type == target_type)
            if target_id is not None:
                filters.append(Override.target_id == target_id)
            if active_only:
                filters.append(Override.expires_at > datetime.now())

            if filters:
                query = query.where(and_(*filters))

            query = query.order_by(Override.created_at.desc())

            result = await session.execute(query)
            overrides = result.scalars().all()

            now = datetime.now()
            return [
                OverrideResponse(
                    id=o.id,
                    target_type=o.target_type,
                    target_id=o.target_id,
                    override_type=o.override_type,
                    property=o.property,
                    value=o.value,
                    created_at=o.created_at,
                    expires_at=o.expires_at,
                    source=o.source,
                    time_remaining_seconds=max(0, (o.expires_at - now).total_seconds()) if o.expires_at > now else 0
                )
                for o in overrides
            ]

        except Exception as e:
            logger.error("list_overrides_error", error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to list overrides: {str(e)}")


@router.post(
    "/overrides",
    response_model=OverrideResponse,
    summary="Create Override",
    description="Create a new CCT override for a fixture or group"
)
async def create_override(request: OverrideCreateRequest):
    """Create a new override."""
    # Validate target type
    if request.target_type not in ('fixture', 'group'):
        raise HTTPException(
            status_code=400,
            detail="target_type must be 'fixture' or 'group'"
        )

    # Validate property
    if request.property != 'cct':
        raise HTTPException(
            status_code=400,
            detail="Only 'cct' property overrides are currently supported"
        )

    # Validate CCT value
    if request.value < 1000 or request.value > 10000:
        raise HTTPException(
            status_code=400,
            detail="CCT value must be between 1000 and 10000 Kelvin"
        )

    async with get_db_session() as session:
        try:
            # Verify target exists
            if request.target_type == 'fixture':
                result = await session.execute(
                    select(Fixture).where(Fixture.id == request.target_id)
                )
                if result.scalar_one_or_none() is None:
                    raise HTTPException(status_code=404, detail=f"Fixture {request.target_id} not found")
            else:
                result = await session.execute(
                    select(Group).where(Group.id == request.target_id)
                )
                if result.scalar_one_or_none() is None:
                    raise HTTPException(status_code=404, detail=f"Group {request.target_id} not found")

            # Create override
            override = await create_dtw_override(
                target_type=request.target_type,
                target_id=request.target_id,
                cct_value=request.value,
                source='api',
                timeout_seconds=request.timeout_seconds,
                session=session
            )

            if override is None:
                raise HTTPException(status_code=500, detail="Failed to create override")

            now = datetime.now()
            return OverrideResponse(
                id=override.id,
                target_type=override.target_type,
                target_id=override.target_id,
                override_type=override.override_type,
                property=override.property,
                value=override.value,
                created_at=override.created_at,
                expires_at=override.expires_at,
                source=override.source,
                time_remaining_seconds=max(0, (override.expires_at - now).total_seconds())
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error("create_override_error", error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to create override: {str(e)}")


@router.delete(
    "/overrides/{override_id}",
    summary="Delete Override",
    description="Delete a specific override by ID"
)
async def delete_override(override_id: int):
    """Delete a specific override."""
    async with get_db_session() as session:
        try:
            from sqlalchemy import delete

            result = await session.execute(
                delete(Override).where(Override.id == override_id)
            )
            await session.commit()

            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"Override {override_id} not found")

            return {"message": f"Override {override_id} deleted"}

        except HTTPException:
            raise
        except Exception as e:
            await session.rollback()
            logger.error("delete_override_error", override_id=override_id, error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to delete override: {str(e)}")


@router.delete(
    "/overrides",
    summary="Bulk Delete Overrides",
    description="Delete all overrides matching the filter criteria"
)
async def bulk_delete_overrides(
    target_type: str = Query(..., description="Target type ('fixture' or 'group')"),
    target_id: int = Query(..., description="Target ID")
):
    """Bulk delete overrides for a target."""
    count = await cancel_all_overrides_for_target(target_type, target_id)
    return {"message": f"Deleted {count} override(s)", "count": count}


@router.post(
    "/overrides/cleanup",
    summary="Cleanup Expired Overrides",
    description="Delete all expired overrides from the database"
)
async def cleanup_overrides():
    """Cleanup expired overrides."""
    count = await cleanup_expired_overrides()
    return {"message": f"Cleaned up {count} expired override(s)", "count": count}
