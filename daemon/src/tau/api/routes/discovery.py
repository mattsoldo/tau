"""
RDM Discovery API Routes - Discover DMX fixtures via RDM protocol

Uses OLA (Open Lighting Architecture) CLI tools for real RDM discovery.
Requires olad daemon running with RDM-capable hardware (e.g., ENTTEC USB Pro).
"""
import uuid
import asyncio
import subprocess
import structlog
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()
logger = structlog.get_logger(__name__)

# In-memory storage for discovery sessions
_discovery_sessions: Dict[str, dict] = {}


class DiscoveryStartRequest(BaseModel):
    """Request to start RDM discovery"""
    universe: int = Field(default=0, ge=0, le=3, description="DMX universe to scan")


class DiscoveryStartResponse(BaseModel):
    """Response from starting discovery"""
    discovery_id: str
    status: str


class DiscoveryProgressResponse(BaseModel):
    """Progress of an ongoing discovery"""
    discovery_id: str
    status: str  # scanning, complete, error, cancelled
    progress_percent: int
    devices_found: int
    error_message: Optional[str] = None


class RDMDeviceInfo(BaseModel):
    """Information about a discovered RDM device (expanded per channel)"""
    rdm_uid: str
    manufacturer_id: int
    device_id: int
    manufacturer_name: str
    model_name: str
    dmx_address: int
    dmx_footprint: int  # Always 1 after expansion (single channel per fixture)
    device_label: Optional[str] = None
    product_category: Optional[str] = None
    software_version: Optional[int] = None
    # Expansion fields
    channel_number: Optional[int] = None  # Which channel of the original device (1-indexed)
    total_channels: Optional[int] = None  # Total channels in the original device
    suggested_name: Optional[str] = None  # Suggested fixture name


class DiscoveryResultsResponse(BaseModel):
    """Results of a completed discovery"""
    discovery_id: str
    status: str
    devices: List[RDMDeviceInfo]


class BulkFixtureConfig(BaseModel):
    """Configuration for a single fixture to create"""
    rdm_uid: str
    name: str
    fixture_model_id: int
    dmx_channel_start: int
    secondary_dmx_channel: Optional[int] = None


class BulkFixtureCreateRequest(BaseModel):
    """Request to create multiple fixtures"""
    fixtures: List[BulkFixtureConfig]


async def _run_ola_command(cmd: List[str], timeout: float = 10.0) -> tuple[bool, str]:
    """Run an OLA CLI command and return (success, output)"""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

        if proc.returncode == 0:
            return True, stdout.decode().strip()
        else:
            error_msg = stderr.decode().strip() or stdout.decode().strip()
            return False, error_msg
    except asyncio.TimeoutError:
        return False, "Command timed out"
    except FileNotFoundError:
        return False, "OLA command not found. Is OLA installed?"
    except Exception as e:
        return False, str(e)


async def _get_rdm_device_info(universe: int, uid: str) -> Optional[RDMDeviceInfo]:
    """Get detailed info for a single RDM device"""
    try:
        # Parse UID (format: MMMM:DDDDDDDD)
        parts = uid.split(":")
        if len(parts) != 2:
            logger.warning("invalid_rdm_uid", uid=uid)
            return None

        manufacturer_id = int(parts[0], 16)
        device_id = int(parts[1], 16)

        # Get device info
        success, output = await _run_ola_command([
            "ola_rdm_get", "-u", str(universe), "--uid", uid, "device_info"
        ])

        if not success:
            logger.warning("rdm_device_info_failed", uid=uid, error=output)
            return None

        # Parse device info output
        device_info = {}
        for line in output.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                device_info[key.strip()] = value.strip()

        dmx_footprint = int(device_info.get("DMX Footprint", "1"))
        dmx_address = int(device_info.get("DMX Start Address", "1"))
        product_category = device_info.get("Product Category", "Unknown")
        software_version = None
        if "Software Version" in device_info:
            try:
                software_version = int(device_info["Software Version"])
            except ValueError:
                pass

        # Get manufacturer label
        success, manufacturer_name = await _run_ola_command([
            "ola_rdm_get", "-u", str(universe), "--uid", uid, "manufacturer_label"
        ])
        if not success:
            manufacturer_name = f"Manufacturer {manufacturer_id:04X}"

        # Get model description
        success, model_name = await _run_ola_command([
            "ola_rdm_get", "-u", str(universe), "--uid", uid, "device_model_description"
        ])
        if not success:
            model_name = f"Device {device_id:08X}"

        # Get device label (optional, may not be supported)
        success, device_label = await _run_ola_command([
            "ola_rdm_get", "-u", str(universe), "--uid", uid, "device_label"
        ])
        if not success:
            device_label = None

        return RDMDeviceInfo(
            rdm_uid=uid,
            manufacturer_id=manufacturer_id,
            device_id=device_id,
            manufacturer_name=manufacturer_name,
            model_name=model_name,
            dmx_address=dmx_address,
            dmx_footprint=dmx_footprint,
            device_label=device_label,
            product_category=product_category,
            software_version=software_version,
        )

    except Exception as e:
        logger.error("rdm_device_info_error", uid=uid, error=str(e))
        return None


async def _run_real_discovery(discovery_id: str) -> None:
    """Run real RDM discovery using OLA CLI tools"""
    session = _discovery_sessions.get(discovery_id)
    if not session:
        return

    universe = session.get("universe", 0)

    try:
        # Update progress - starting discovery
        session["progress_percent"] = 10
        logger.info("rdm_discovery_starting", discovery_id=discovery_id, universe=universe)

        # Run ola_rdm_discover to get list of UIDs
        success, output = await _run_ola_command(
            ["ola_rdm_discover", "-u", str(universe)],
            timeout=30.0  # Discovery can take time
        )

        if session.get("cancelled"):
            session["status"] = "cancelled"
            return

        if not success:
            session["status"] = "error"
            session["error_message"] = output
            logger.error("rdm_discovery_failed", error=output)
            return

        # Parse discovered UIDs
        uids = [uid.strip() for uid in output.split("\n") if uid.strip()]
        session["progress_percent"] = 30
        session["devices_found"] = len(uids)

        logger.info("rdm_discovery_uids_found", count=len(uids), uids=uids)

        if not uids:
            session["status"] = "complete"
            session["progress_percent"] = 100
            session["devices"] = []
            return

        # Get detailed info for each device and expand by footprint
        devices: List[dict] = []
        for i, uid in enumerate(uids):
            if session.get("cancelled"):
                session["status"] = "cancelled"
                return

            # Update progress
            progress = 30 + int((i + 1) / len(uids) * 60)
            session["progress_percent"] = progress

            device_info = await _get_rdm_device_info(universe, uid)
            if device_info:
                logger.info(
                    "rdm_device_discovered",
                    uid=uid,
                    manufacturer=device_info.manufacturer_name,
                    model=device_info.model_name,
                    dmx_address=device_info.dmx_address,
                    dmx_footprint=device_info.dmx_footprint,
                )

                # Expand device into individual fixtures based on footprint
                # Each channel becomes a separate fixture with footprint=1
                base_address = device_info.dmx_address
                for channel in range(device_info.dmx_footprint):
                    channel_num = channel + 1  # 1-indexed for display
                    fixture_entry = device_info.model_dump()
                    # Make rdm_uid unique for each channel by appending channel number
                    fixture_entry["rdm_uid"] = f"{uid}:ch{channel_num}"
                    fixture_entry["dmx_address"] = base_address + channel
                    fixture_entry["dmx_footprint"] = 1  # Single channel per fixture
                    fixture_entry["channel_number"] = channel_num
                    fixture_entry["total_channels"] = device_info.dmx_footprint
                    # Suggested name includes channel number
                    fixture_entry["suggested_name"] = f"{device_info.model_name} Ch {channel_num}"
                    devices.append(fixture_entry)

        # Sort by DMX address
        devices.sort(key=lambda d: d["dmx_address"])

        # Complete the discovery
        session["status"] = "complete"
        session["progress_percent"] = 100
        session["devices_found"] = len(devices)
        session["devices"] = devices

        logger.info(
            "rdm_discovery_complete",
            discovery_id=discovery_id,
            devices_found=len(devices),
        )

    except Exception as e:
        session["status"] = "error"
        session["error_message"] = str(e)
        logger.error("rdm_discovery_error", error=str(e), exc_info=True)


@router.post("/start", response_model=DiscoveryStartResponse)
async def start_discovery(request: DiscoveryStartRequest):
    """
    Start RDM device discovery on a DMX universe.

    Requires OLA daemon (olad) running with RDM-capable hardware.
    Returns a discovery_id that can be used to poll progress and retrieve results.
    """
    discovery_id = str(uuid.uuid4())

    _discovery_sessions[discovery_id] = {
        "status": "scanning",
        "progress_percent": 0,
        "devices_found": 0,
        "devices": [],
        "universe": request.universe,
        "cancelled": False,
        "error_message": None,
    }

    # Start real RDM discovery in the background
    asyncio.create_task(_run_real_discovery(discovery_id))

    return DiscoveryStartResponse(
        discovery_id=discovery_id,
        status="scanning"
    )


@router.get("/progress/{discovery_id}", response_model=DiscoveryProgressResponse)
async def get_discovery_progress(discovery_id: str):
    """
    Get the progress of an ongoing discovery scan.

    Poll this endpoint to track discovery progress.
    """
    session = _discovery_sessions.get(discovery_id)
    if not session:
        raise HTTPException(status_code=404, detail="Discovery session not found")

    return DiscoveryProgressResponse(
        discovery_id=discovery_id,
        status=session["status"],
        progress_percent=session["progress_percent"],
        devices_found=session["devices_found"],
        error_message=session.get("error_message"),
    )


@router.get("/results/{discovery_id}", response_model=DiscoveryResultsResponse)
async def get_discovery_results(discovery_id: str):
    """
    Get the results of a completed discovery scan.

    Returns the list of discovered RDM devices.
    """
    session = _discovery_sessions.get(discovery_id)
    if not session:
        raise HTTPException(status_code=404, detail="Discovery session not found")

    if session["status"] == "error":
        raise HTTPException(
            status_code=500,
            detail=f"Discovery failed: {session.get('error_message', 'Unknown error')}"
        )

    if session["status"] != "complete":
        raise HTTPException(
            status_code=400,
            detail=f"Discovery not complete. Current status: {session['status']}"
        )

    devices = [RDMDeviceInfo(**d) for d in session["devices"]]

    return DiscoveryResultsResponse(
        discovery_id=discovery_id,
        status="complete",
        devices=devices,
    )


@router.post("/cancel/{discovery_id}")
async def cancel_discovery(discovery_id: str):
    """
    Cancel an ongoing discovery scan.
    """
    session = _discovery_sessions.get(discovery_id)
    if not session:
        raise HTTPException(status_code=404, detail="Discovery session not found")

    session["cancelled"] = True

    return {"status": "cancelled", "discovery_id": discovery_id}


@router.post("/bulk-create")
async def bulk_create_fixtures(request: BulkFixtureCreateRequest):
    """
    Create multiple fixtures from discovered devices.

    This endpoint creates fixtures in bulk, typically after RDM discovery.
    """
    from tau.database import get_session
    from tau.models.fixtures import Fixture, FixtureModel
    from tau.models.state import FixtureState
    from sqlalchemy import select

    # Get a database session
    from tau.database import async_session_maker
    if async_session_maker is None:
        raise HTTPException(status_code=500, detail="Database not initialized")

    created_fixtures = []
    errors = []

    async with async_session_maker() as session:
        for config in request.fixtures:
            try:
                # Verify fixture model exists
                model = await session.get(FixtureModel, config.fixture_model_id)
                if not model:
                    errors.append({
                        "rdm_uid": config.rdm_uid,
                        "error": f"Fixture model {config.fixture_model_id} not found"
                    })
                    continue

                # Check if DMX channel is already in use
                result = await session.execute(
                    select(Fixture).where(Fixture.dmx_channel_start == config.dmx_channel_start)
                )
                existing = result.scalar_one_or_none()
                if existing:
                    errors.append({
                        "rdm_uid": config.rdm_uid,
                        "error": f"DMX channel {config.dmx_channel_start} already in use"
                    })
                    continue

                # Create the fixture
                fixture = Fixture(
                    name=config.name,
                    fixture_model_id=config.fixture_model_id,
                    dmx_channel_start=config.dmx_channel_start,
                    secondary_dmx_channel=config.secondary_dmx_channel,
                )
                session.add(fixture)
                await session.flush()  # Get the fixture ID

                # Create initial state
                state = FixtureState(
                    fixture_id=fixture.id,
                    current_brightness=0,
                    current_cct=2700,
                    is_on=False
                )
                session.add(state)

                created_fixtures.append({
                    "id": fixture.id,
                    "name": fixture.name,
                    "rdm_uid": config.rdm_uid,
                    "dmx_channel_start": fixture.dmx_channel_start,
                })

            except Exception as e:
                errors.append({
                    "rdm_uid": config.rdm_uid,
                    "error": str(e)
                })

        await session.commit()

    return {
        "created": created_fixtures,
        "errors": errors,
        "total_created": len(created_fixtures),
        "total_errors": len(errors),
    }
