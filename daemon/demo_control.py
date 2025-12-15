#!/usr/bin/env python3
"""
Demo script to showcase Tau Lighting Control System capabilities
Demonstrates fixture control, group management, and scene activation
"""

import asyncio
import aiohttp
import json
from typing import Dict
import time

API_URL = "http://localhost:8000"

async def demo_fixture_control():
    """Demonstrate individual fixture brightness control"""
    print("\n📡 Demo 1: Individual Fixture Control")
    print("-" * 40)

    async with aiohttp.ClientSession() as session:
        # Get all fixtures
        async with session.get(f"{API_URL}/api/fixtures/") as resp:
            fixtures = await resp.json()
            print(f"Found {len(fixtures)} fixtures:")
            for f in fixtures[:3]:  # Show first 3
                print(f"  • {f['name']} (Channel {f['dmx_channel_start']})")

        # Control first fixture
        if fixtures:
            fixture = fixtures[0]
            print(f"\n🎮 Controlling '{fixture['name']}':")

            # Turn on at 50%
            control_data = {"brightness": 0.5, "cct": 3000}
            async with session.post(
                f"{API_URL}/api/fixtures/{fixture['id']}/control",
                json=control_data
            ) as resp:
                if resp.status == 200:
                    print(f"  ✓ Set to 50% brightness at 3000K")

            await asyncio.sleep(1)

            # Turn on at 100%
            control_data = {"brightness": 1.0, "cct": 4500}
            async with session.post(
                f"{API_URL}/api/fixtures/{fixture['id']}/control",
                json=control_data
            ) as resp:
                if resp.status == 200:
                    print(f"  ✓ Set to 100% brightness at 4500K")

            await asyncio.sleep(1)

            # Turn off
            control_data = {"brightness": 0.0}
            async with session.post(
                f"{API_URL}/api/fixtures/{fixture['id']}/control",
                json=control_data
            ) as resp:
                if resp.status == 200:
                    print(f"  ✓ Turned off")

async def demo_group_control():
    """Demonstrate group control and circadian rhythm"""
    print("\n🏠 Demo 2: Group Control")
    print("-" * 40)

    async with aiohttp.ClientSession() as session:
        # Get all groups
        async with session.get(f"{API_URL}/api/groups/") as resp:
            groups = await resp.json()
            print(f"Found {len(groups)} groups:")
            for g in groups:
                circadian = "with circadian" if g.get('circadian_enabled') else "manual"
                print(f"  • {g['name']} ({circadian})")

        # Control first group
        if groups:
            group = groups[0]
            print(f"\n🎮 Controlling group '{group['name']}':")

            # Set group to 75% brightness
            control_data = {"brightness": 0.75, "cct": 3500}
            async with session.post(
                f"{API_URL}/api/groups/{group['id']}/control",
                json=control_data
            ) as resp:
                if resp.status == 200:
                    print(f"  ✓ Set group to 75% brightness at 3500K")

            await asyncio.sleep(2)

            # Turn off group
            control_data = {"brightness": 0.0}
            async with session.post(
                f"{API_URL}/api/groups/{group['id']}/control",
                json=control_data
            ) as resp:
                if resp.status == 200:
                    print(f"  ✓ Turned off group")

async def demo_scene_activation():
    """Demonstrate scene activation"""
    print("\n🎬 Demo 3: Scene Activation")
    print("-" * 40)

    async with aiohttp.ClientSession() as session:
        # Get all scenes
        async with session.get(f"{API_URL}/api/scenes/") as resp:
            scenes = await resp.json()
            print(f"Found {len(scenes)} scenes:")
            for s in scenes:
                print(f"  • {s['name']}")

        # Activate each scene briefly
        for scene in scenes:
            print(f"\n🎮 Activating scene '{scene['name']}'...")
            async with session.post(
                f"{API_URL}/api/scenes/{scene['id']}/recall"
            ) as resp:
                if resp.status == 200:
                    print(f"  ✓ Scene activated")
                    await asyncio.sleep(2)

async def demo_all_off():
    """Turn all lights off"""
    print("\n🌑 Demo 4: All Lights Off")
    print("-" * 40)

    async with aiohttp.ClientSession() as session:
        async with session.post(f"{API_URL}/api/control/all-off") as resp:
            if resp.status == 200:
                print("  ✓ All lights turned off")

async def monitor_websocket():
    """Monitor WebSocket events during demos"""
    try:
        session = aiohttp.ClientSession()
        ws = await session.ws_connect(f"ws://localhost:8000/ws")

        async def receive_messages():
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    print(f"  📨 WebSocket: {data.get('type', 'unknown')} event")
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    break

        return session, ws, asyncio.create_task(receive_messages())
    except Exception as e:
        print(f"  ⚠️ WebSocket monitoring not available: {e}")
        return None, None, None

async def main():
    print("\n" + "=" * 50)
    print("   TAU LIGHTING CONTROL SYSTEM - DEMO")
    print("=" * 50)
    print("This demo will showcase the system's capabilities")

    # Start WebSocket monitoring
    ws_session, ws, ws_task = await monitor_websocket()

    try:
        # Run demos
        await demo_fixture_control()
        await asyncio.sleep(1)

        await demo_group_control()
        await asyncio.sleep(1)

        await demo_scene_activation()
        await asyncio.sleep(1)

        await demo_all_off()

        print("\n" + "=" * 50)
        print("✅ Demo completed successfully!")
        print("\nVisit the frontend to see real-time updates:")
        print("  http://localhost:3000/test_frontend.html")
        print("=" * 50)

    finally:
        # Cleanup WebSocket
        if ws:
            await ws.close()
        if ws_session:
            await ws_session.close()
        if ws_task:
            ws_task.cancel()

if __name__ == "__main__":
    asyncio.run(main())