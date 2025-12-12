#!/usr/bin/env python3
"""
Quick test script to verify ORM models work with the database
"""
import asyncio
import sys

from sqlalchemy import select
from tau.config import get_settings
from tau.database import init_database, get_session
from tau.models import (
    FixtureModel,
    CircadianProfile,
    Group,
)


async def test_models():
    """Test that ORM models can query the database"""
    print("Testing ORM models...")

    # Initialize database
    settings = get_settings()
    await init_database(settings.database_url)
    print("✓ Database initialized")

    # Test querying circadian profiles (we know there are 2 default profiles)
    async with get_session() as session:
        result = await session.execute(select(CircadianProfile))
        profiles = result.scalars().all()
        print(f"✓ Found {len(profiles)} circadian profiles")
        for profile in profiles:
            print(f"  - {profile.name}: {len(profile.curve_points)} curve points")

    # Test querying fixture models (should be empty)
    async with get_session() as session:
        result = await session.execute(select(FixtureModel))
        models = result.scalars().all()
        print(f"✓ Found {len(models)} fixture models (expected 0)")

    # Test querying groups (should be empty)
    async with get_session() as session:
        result = await session.execute(select(Group))
        groups = result.scalars().all()
        print(f"✓ Found {len(groups)} groups (expected 0)")

    # Test creating a fixture model
    async with get_session() as session:
        test_model = FixtureModel(
            manufacturer="Test Manufacturer",
            model="Test Model",
            description="Test fixture model for ORM testing",
            type="tunable_white",
            dmx_footprint=2,
            cct_min_kelvin=2700,
            cct_max_kelvin=6500,
            mixing_type="linear",
        )
        session.add(test_model)
        await session.commit()
        print(f"✓ Created test fixture model with id={test_model.id}")

    # Verify we can read it back
    async with get_session() as session:
        result = await session.execute(
            select(FixtureModel).where(FixtureModel.manufacturer == "Test Manufacturer")
        )
        model = result.scalar_one_or_none()
        if model:
            print(f"✓ Successfully read back test fixture model: {model}")
        else:
            print("✗ Failed to read back test fixture model")
            return False

    # Clean up - delete the test model
    async with get_session() as session:
        result = await session.execute(
            select(FixtureModel).where(FixtureModel.manufacturer == "Test Manufacturer")
        )
        model = result.scalar_one_or_none()
        if model:
            await session.delete(model)
            await session.commit()
            print("✓ Cleaned up test fixture model")

    print("\n✅ All ORM model tests passed!")
    return True


if __name__ == "__main__":
    success = asyncio.run(test_models())
    sys.exit(0 if success else 1)
