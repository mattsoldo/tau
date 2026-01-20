"""
Software Update API Routes - Check for and install updates
"""
from typing import Optional, List
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from tau.config import get_settings
from tau.database import get_session
from tau.services.update_service import UpdateService

logger = structlog.get_logger(__name__)


def verify_update_token(x_update_token: str | None = Header(None)) -> None:
    """
    Enforce shared-secret auth for update endpoints when configured.

    If UPDATES_AUTH_TOKEN is set, requests must provide X-Update-Token header.
    """
    token = get_settings().updates_auth_token
    if not token:
        return
    if x_update_token != token:
        raise HTTPException(status_code=401, detail="Invalid or missing update token")


router = APIRouter(dependencies=[Depends(verify_update_token)])


# Response Models
class UpdateStatusResponse(BaseModel):
    """Current update status"""

    current_version: str = Field(..., description="Current git commit hash")
    available_version: Optional[str] = Field(None, description="Latest available version")
    update_available: bool = Field(..., description="Whether updates are available")
    is_updating: bool = Field(..., description="Whether an update is currently in progress")
    last_check_at: Optional[str] = Field(None, description="Last update check timestamp")


class UpdateCheckResponse(BaseModel):
    """Update availability check result"""

    update_available: bool = Field(..., description="Whether updates are available")
    current_version: str = Field(..., description="Current git commit hash")
    latest_version: str = Field(..., description="Latest git commit hash")
    commits_behind: int = Field(..., description="Number of commits behind latest")
    changelog: str = Field(..., description="Git log of changes")


class UpdateStartResponse(BaseModel):
    """Update start confirmation"""

    message: str = Field(..., description="Status message")
    update_id: int = Field(..., description="Update log entry ID")


class UpdateHistoryEntry(BaseModel):
    """Single update history entry"""

    id: int
    version_before: Optional[str]
    version_after: Optional[str]
    status: str
    started_at: Optional[str]
    completed_at: Optional[str]
    error_message: Optional[str]
    changelog: Optional[str]
    update_type: Optional[str]


class ChangelogResponse(BaseModel):
    """Git changelog between commits"""

    changelog: str = Field(..., description="Formatted git log")
    from_commit: str = Field(..., description="Starting commit")
    to_commit: str = Field(..., description="Ending commit")


# Endpoints
@router.get(
    "/status",
    response_model=UpdateStatusResponse,
    summary="Get Update Status",
    description="Get current software version and update status",
)
async def get_update_status(db: AsyncSession = Depends(get_session)):
    """Get current update status"""
    try:
        service = UpdateService(db_session=db)
        status = await service.get_update_status()
        return UpdateStatusResponse(**status)
    except Exception as e:
        logger.error("update_status_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get update status: {str(e)}")


@router.post(
    "/check",
    response_model=UpdateCheckResponse,
    summary="Check for Updates",
    description="Check if software updates are available from git remote",
)
async def check_for_updates(db: AsyncSession = Depends(get_session)):
    """Check for available updates"""
    try:
        service = UpdateService(db_session=db)
        result = await service.check_for_updates()
        return UpdateCheckResponse(**result)
    except Exception as e:
        logger.error("update_check_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to check for updates: {str(e)}")


@router.post(
    "/start",
    response_model=UpdateStartResponse,
    summary="Start Update",
    description="Start software update process (backend and frontend)",
)
async def start_update(background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_session)):
    """Start update process"""
    try:
        service = UpdateService(db_session=db)
        result = await service.start_update(background_tasks)
        return UpdateStartResponse(**result)
    except RuntimeError as e:
        # User-friendly errors (already in progress, no updates, etc.)
        logger.warning("update_start_failed", reason=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("update_start_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to start update: {str(e)}")


@router.get(
    "/history",
    response_model=List[UpdateHistoryEntry],
    summary="Get Update History",
    description="Get recent software update history",
)
async def get_update_history(limit: int = 10, db: AsyncSession = Depends(get_session)):
    """Get update history"""
    try:
        service = UpdateService(db_session=db)
        history = await service.get_update_history(limit=limit)
        return [UpdateHistoryEntry(**entry) for entry in history]
    except Exception as e:
        logger.error("update_history_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get update history: {str(e)}")


@router.get(
    "/changelog",
    response_model=ChangelogResponse,
    summary="Get Changelog",
    description="Get git log between two commits",
)
async def get_changelog(from_commit: str, to_commit: str = "HEAD", db: AsyncSession = Depends(get_session)):
    """Get changelog between commits"""
    try:
        service = UpdateService(db_session=db)
        changelog = await service.get_changelog(from_commit, to_commit)
        return ChangelogResponse(changelog=changelog, from_commit=from_commit, to_commit=to_commit)
    except Exception as e:
        logger.error("changelog_error", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get changelog: {str(e)}")
