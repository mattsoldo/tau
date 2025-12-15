#!/usr/bin/env python3
"""Test API database query directly"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from tau.database import init_database, get_db_session
from tau.models.fixtures import Fixture
from sqlalchemy import select
import os


async def test_query():
    # Initialize database
    database_url = os.environ.get("DATABASE_URL", "postgresql://tau_daemon:tau_password@localhost/tau_lighting")
    await init_database(database_url)

    print(f"Database URL: {database_url}")

    # Query fixtures using get_db_session
    async with get_db_session() as session:
        result = await session.execute(select(Fixture))
        fixtures = result.scalars().all()

        print(f"\nFound {len(fixtures)} fixtures:")
        for fixture in fixtures:
            print(f"  - {fixture.id}: {fixture.name} (channel {fixture.dmx_channel_start})")

    # Also test with a fresh session to simulate API call
    print("\n--- Testing with fresh session (like API) ---")
    async with get_db_session() as session:
        # This is exactly what the API does
        result = await session.execute(select(Fixture))
        fixtures = result.scalars().all()
        print(f"API would return {len(fixtures)} fixtures")

        # Check if we can access fixture attributes
        if fixtures:
            first = fixtures[0]
            print(f"First fixture: id={first.id}, name={first.name}")


if __name__ == "__main__":
    asyncio.run(test_query())