"""
RDM Discovery API Routes - Discover DMX fixtures via RDM protocol
"""
import uuid
import asyncio
import random
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

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


class RDMDeviceInfo(BaseModel):
    """Information about a discovered RDM device"""
    rdm_uid: str
    manufacturer_id: int
    device_id: int
    manufacturer_name: str
    model_name: str
    dmx_address: int
    dmx_footprint: int
    device_label: Optional[str] = None


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


# Mock device library for simulated discovery
MOCK_DEVICE_LIBRARY = [
    {"manufacturer_name": "GDS", "model_name": "Arc LED Par", "dmx_footprint": 1},
    {"manufacturer_name": "GDS", "model_name": "Arc LED Flood", "dmx_footprint": 2},
    {"manufacturer_name": "Lutron", "model_name": "Ketra S38", "dmx_footprint": 2},
    {"manufacturer_name": "Lutron", "model_name": "Ketra A19", "dmx_footprint": 2},
    {"manufacturer_name": "Cree", "model_name": "LMH2", "dmx_footprint": 1},
    {"manufacturer_name": "ETC", "model_name": "Source Four LED S2", "dmx_footprint": 2},
    {"manufacturer_name": "ETC", "model_name": "ColorSource Spot", "dmx_footprint": 1},
    {"manufacturer_name": "Philips", "model_name": "Hue White Ambiance", "dmx_footprint": 2},
    {"manufacturer_name": "Philips", "model_name": "Hue White", "dmx_footprint": 1},
    {"manufacturer_name": "Clay Paky", "model_name": "Stormy CC", "dmx_footprint": 2},
]


async def _run_mock_discovery(discovery_id: str) -> None:
    """Run a mock discovery scan with simulated progress"""
    session = _discovery_sessions.get(discovery_id)
    if not session:
        return

    # Simulate discovery taking 2-4 seconds
    total_steps = 20
    delay_per_step = random.uniform(0.1, 0.2)

    devices: List[RDMDeviceInfo] = []
    num_devices = random.randint(3, 8)

    # Generate random devices
    used_addresses: set = set()
    for i in range(num_devices):
        device_template = random.choice(MOCK_DEVICE_LIBRARY)

        # Find unused DMX address
        dmx_address = random.randint(1, 400)
        while dmx_address in used_addresses:
            dmx_address = random.randint(1, 400)
        used_addresses.add(dmx_address)

        # Generate unique RDM UID
        manufacturer_id = random.randint(0x1000, 0xFFFF)
        device_id = random.randint(0x10000000, 0xFFFFFFFF)

        devices.append(RDMDeviceInfo(
            rdm_uid=f"{manufacturer_id:04X}:{device_id:08X}",
            manufacturer_id=manufacturer_id,
            device_id=device_id,
            manufacturer_name=device_template["manufacturer_name"],
            model_name=device_template["model_name"],
            dmx_address=dmx_address,
            dmx_footprint=device_template["dmx_footprint"],
            device_label=f"{device_template['manufacturer_name']} {device_template['model_name']} @ {dmx_address}",
        ))

    # Sort by DMX address
    devices.sort(key=lambda d: d.dmx_address)

    # Simulate progress updates
    for step in range(total_steps):
        if session.get("cancelled"):
            session["status"] = "cancelled"
            return

        progress = int((step + 1) / total_steps * 100)
        # Gradually "discover" devices
        discovered_count = min(len(devices), int(len(devices) * (step + 1) / total_steps) + 1)

        session["progress_percent"] = progress
        session["devices_found"] = discovered_count

        await asyncio.sleep(delay_per_step)

    # Complete the discovery
    session["status"] = "complete"
    session["progress_percent"] = 100
    session["devices_found"] = len(devices)
    session["devices"] = [d.model_dump() for d in devices]


@router.post("/start", response_model=DiscoveryStartResponse)
async def start_discovery(request: DiscoveryStartRequest):
    """
    Start RDM device discovery on a DMX universe.

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
    }

    # Start the mock discovery in the background
    asyncio.create_task(_run_mock_discovery(discovery_id))

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
