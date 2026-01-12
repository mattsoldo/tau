"""
Software Update API Routes - GitHub Releases-based OTA updates

Provides endpoints for:
- Checking for updates
- Getting update status
- Applying updates
- Rolling back to previous versions
- Managing version history
- Configuring update settings
"""
from typing import Optional, List, AsyncGenerator
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from tau.database import get_session
from tau.services.software_update_service import SoftwareUpdateService, UpdateError, RollbackError

logger = structlog.get_logger(__name__)

router = APIRouter()


# Request/Response Models
class UpdateStatusResponse(BaseModel):
    """Current update status"""

    current_version: str = Field(..., description="Currently installed version")
    installed_at: str = Field(..., description="When current version was installed")
    install_method: Optional[str] = Field(None, description="How current version was installed")
    update_available: bool = Field(..., description="Whether an update is available")
    available_version: Optional[str] = Field(None, description="Latest available version")
    release_notes: Optional[str] = Field(None, description="Release notes for available update")
    last_check_at: Optional[str] = Field(None, description="When updates were last checked")
    state: str = Field(..., description="Current update state")
    progress: dict = Field(default_factory=dict, description="Update progress information")


class UpdateCheckResponse(BaseModel):
    """Update check result"""

    update_available: bool = Field(..., description="Whether an update is available")
    current_version: str = Field(..., description="Currently installed version")
    latest_version: str = Field(..., description="Latest available version")
    release_notes: str = Field(..., description="Release notes for latest version")
    published_at: Optional[str] = Field(None, description="When latest version was published")
    prerelease: bool = Field(..., description="Whether latest is a pre-release")


class ApplyUpdateRequest(BaseModel):
    """Request to apply an update"""

    target_version: str = Field(..., description="Version to update to")


class ApplyUpdateResponse(BaseModel):
    """Update application result"""

    success: bool = Field(..., description="Whether update was successful")
    from_version: str = Field(..., description="Version before update")
    to_version: str = Field(..., description="Version after update")
    message: str = Field(..., description="Status message")


class RollbackRequest(BaseModel):
    """Request to rollback"""

    target_version: Optional[str] = Field(None, description="Version to rollback to, or None for most recent")


class RollbackResponse(BaseModel):
    """Rollback result"""

    success: bool = Field(..., description="Whether rollback was successful")
    from_version: str = Field(..., description="Version before rollback")
    to_version: str = Field(..., description="Version after rollback")
    message: str = Field(..., description="Status message")
    schema_revision: Optional[str] = Field(None, description="Database schema revision after rollback")


class DowngradeRequest(BaseModel):
    """Request to downgrade to an older version"""

    target_version: str = Field(..., description="Version to downgrade to")


class DowngradeResponse(BaseModel):
    """Downgrade result"""

    success: bool = Field(..., description="Whether downgrade was successful")
    from_version: str = Field(..., description="Version before downgrade")
    to_version: str = Field(..., description="Version after downgrade")
    schema_revision: Optional[str] = Field(None, description="Database schema revision after downgrade")
    message: str = Field(..., description="Status message")


class ReleaseInfo(BaseModel):
    """Information about a release"""

    version: str
    tag_name: str
    published_at: str
    release_notes: Optional[str]
    asset_url: Optional[str]
    asset_name: Optional[str]
    asset_size: Optional[int]
    prerelease: bool
    has_asset: bool


class VersionHistoryEntry(BaseModel):
    """Version history entry"""

    version: str
    installed_at: str
    uninstalled_at: Optional[str]
    backup_path: Optional[str]
    backup_valid: bool
    can_rollback: bool
    is_current: bool
    release_notes: Optional[str]


class BackupInfo(BaseModel):
    """Backup information"""

    version: str
    backup_path: str
    created_at: str
    size_bytes: int
    size_mb: float
    valid: bool


class UpdateConfigResponse(BaseModel):
    """Update configuration"""

    auto_check_enabled: str
    check_interval_hours: str
    include_prereleases: str
    max_backups: str
    github_repo: str
    github_token: str
    backup_location: str
    min_free_space_mb: str
    download_timeout_seconds: str
    verify_after_install: str
    rollback_on_service_failure: str


class UpdateConfigRequest(BaseModel):
    """Request to update configuration"""

    key: str = Field(..., description="Configuration key to update")
    value: str = Field(..., description="New value")


# Helper to get service with proper session management
async def get_update_service(
    db: AsyncSession = Depends(get_session),
) -> AsyncGenerator[SoftwareUpdateService, None]:
    """
    Get SoftwareUpdateService instance with proper lifecycle management.

    Uses yield pattern to ensure service is properly cleaned up after request.
    The database session is managed by the get_session dependency.
    """
    service = SoftwareUpdateService(db_session=db)
    try:
        yield service
    finally:
        # Clean up any cached resources
        if service._github_client:
            await service._github_client.close()


# Endpoints
@router.get(
    "/status",
    response_model=UpdateStatusResponse,
    summary="Get Update Status",
    description="Get current software version and update status",
)
async def get_update_status(
    service: SoftwareUpdateService = Depends(get_update_service),
):
    """Get current update status"""
    try:
        status = await service.get_update_status()
        return UpdateStatusResponse(**status)
    except Exception as e:
        logger.error("get_status_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get update status: {str(e)}")


@router.get(
    "/check",
    response_model=UpdateCheckResponse,
    summary="Check for Updates",
    description="Check if software updates are available from GitHub Releases",
)
@router.post(
    "/check",
    response_model=UpdateCheckResponse,
    summary="Check for Updates (Legacy)",
    description="Check if software updates are available (POST for backwards compatibility)",
    include_in_schema=False,  # Hide from OpenAPI docs
)
async def check_for_updates(
    service: SoftwareUpdateService = Depends(get_update_service),
):
    """Check for available updates"""
    try:
        result = await service.check_for_updates(source="manual")
        return UpdateCheckResponse(**result)
    except UpdateError as e:
        logger.warning("update_check_failed", error=str(e))
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("update_check_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to check for updates: {str(e)}")


@router.post(
    "/apply",
    response_model=ApplyUpdateResponse,
    summary="Apply Update",
    description="Apply an update to a specific version",
)
async def apply_update(
    request: ApplyUpdateRequest,
    background_tasks: BackgroundTasks,
    service: SoftwareUpdateService = Depends(get_update_service),
):
    """
    Apply an update to the specified version.

    This will:
    1. Download the update package
    2. Verify the checksum
    3. Create a backup of the current installation
    4. Stop services
    5. Install the new version
    6. Run database migrations
    7. Start services
    8. Verify the installation

    If any step fails, an automatic rollback will be attempted.
    """
    try:
        result = await service.apply_update(target_version=request.target_version)
        return ApplyUpdateResponse(**result)
    except UpdateError as e:
        logger.warning("update_apply_failed", error=str(e), target=request.target_version)
        raise HTTPException(status_code=400, detail=str(e))
    except RollbackError as e:
        logger.error("update_and_rollback_failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"CRITICAL: Update failed and rollback also failed. Manual intervention required. {str(e)}",
        )
    except Exception as e:
        logger.error("update_apply_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to apply update: {str(e)}")


@router.post(
    "/rollback",
    response_model=RollbackResponse,
    summary="Rollback to Previous Version",
    description="Rollback to a previous version using a backup",
)
async def rollback(
    request: RollbackRequest,
    service: SoftwareUpdateService = Depends(get_update_service),
):
    """
    Rollback to a previous version.

    If target_version is not specified, rolls back to the most recent valid backup.
    """
    try:
        result = await service.rollback(target_version=request.target_version)
        return RollbackResponse(**result)
    except UpdateError as e:
        logger.warning("rollback_no_backup", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except RollbackError as e:
        logger.error("rollback_failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"CRITICAL: Rollback failed. Manual intervention required. {str(e)}",
        )
    except Exception as e:
        logger.error("rollback_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to rollback: {str(e)}")


@router.post(
    "/downgrade",
    response_model=DowngradeResponse,
    summary="Downgrade to Older Version",
    description="Downgrade to a specific older version, downloading from GitHub if needed",
)
async def downgrade(
    request: DowngradeRequest,
    service: SoftwareUpdateService = Depends(get_update_service),
):
    """
    Downgrade to a specific older version.

    This will:
    1. Check for local backup (use if available)
    2. Otherwise download the release from GitHub
    3. Create backup of current installation
    4. Downgrade database schema (before code change)
    5. Install the older version
    6. Restart services

    If the target version has a local backup, this is equivalent to rollback.
    If not, the release is downloaded from GitHub.

    Database schema is downgraded BEFORE installing old code to ensure
    compatibility (we need the current migration files to downgrade).
    """
    try:
        result = await service.downgrade(target_version=request.target_version)
        return DowngradeResponse(**result)
    except UpdateError as e:
        logger.warning("downgrade_failed", error=str(e), target=request.target_version)
        raise HTTPException(status_code=400, detail=str(e))
    except RollbackError as e:
        logger.error("downgrade_and_rollback_failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"CRITICAL: Downgrade failed and rollback also failed. Manual intervention required. {str(e)}",
        )
    except Exception as e:
        logger.error("downgrade_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to downgrade: {str(e)}")


@router.get(
    "/releases",
    response_model=List[ReleaseInfo],
    summary="Get Available Releases",
    description="Get list of available releases from cache",
)
async def get_releases(
    service: SoftwareUpdateService = Depends(get_update_service),
):
    """Get cached available releases"""
    try:
        releases = await service.get_available_releases()
        return [ReleaseInfo(**r) for r in releases]
    except Exception as e:
        logger.error("get_releases_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get releases: {str(e)}")


@router.get(
    "/history",
    response_model=List[VersionHistoryEntry],
    summary="Get Version History",
    description="Get history of installed versions with rollback capability",
)
async def get_version_history(
    limit: int = 10,
    service: SoftwareUpdateService = Depends(get_update_service),
):
    """Get version history"""
    try:
        history = await service.get_version_history(limit=limit)
        return [VersionHistoryEntry(**h) for h in history]
    except Exception as e:
        logger.error("get_history_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get version history: {str(e)}")


@router.get(
    "/backups",
    response_model=List[BackupInfo],
    summary="Get Backups",
    description="Get list of available backups",
)
async def get_backups(
    service: SoftwareUpdateService = Depends(get_update_service),
):
    """Get list of backups"""
    try:
        backups = await service.get_backups()
        return [BackupInfo(**b) for b in backups]
    except Exception as e:
        logger.error("get_backups_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get backups: {str(e)}")


@router.get(
    "/config",
    response_model=UpdateConfigResponse,
    summary="Get Update Configuration",
    description="Get current update system configuration",
)
async def get_config(
    service: SoftwareUpdateService = Depends(get_update_service),
):
    """Get update configuration"""
    try:
        config = await service.get_config()
        return UpdateConfigResponse(**config)
    except Exception as e:
        logger.error("get_config_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get configuration: {str(e)}")


@router.put(
    "/config",
    response_model=UpdateConfigResponse,
    summary="Update Configuration",
    description="Update a configuration setting",
)
async def update_config(
    request: UpdateConfigRequest,
    service: SoftwareUpdateService = Depends(get_update_service),
):
    """Update a configuration setting"""
    try:
        config = await service.update_config(key=request.key, value=request.value)
        return UpdateConfigResponse(**config)
    except UpdateError as e:
        logger.warning("config_update_failed", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("config_update_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update configuration: {str(e)}")
