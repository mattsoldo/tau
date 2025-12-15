#!/usr/bin/env python3
"""
System verification script for Tau Lighting Control System
Checks all components are running and properly integrated
"""

import asyncio
import aiohttp
import json
from typing import Dict, List, Tuple
import sys

BACKEND_URL = "http://localhost:8000"
FRONTEND_URL = "http://localhost:3000"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_status(label: str, status: bool, detail: str = ""):
    """Print a colored status line"""
    symbol = "✓" if status else "✗"
    color = Colors.GREEN if status else Colors.RED
    print(f"{color}{symbol}{Colors.ENDC} {label}: {detail}")

async def check_backend() -> Tuple[bool, Dict]:
    """Check backend API is responding"""
    results = {}
    try:
        async with aiohttp.ClientSession() as session:
            # Check health endpoint
            async with session.get(f"{BACKEND_URL}/health") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results['health'] = (True, f"v{data.get('version', 'unknown')}")
                else:
                    results['health'] = (False, f"Status {resp.status}")

            # Check fixtures endpoint
            async with session.get(f"{BACKEND_URL}/api/fixtures/") as resp:
                if resp.status == 200:
                    fixtures = await resp.json()
                    results['fixtures'] = (True, f"{len(fixtures)} fixtures")
                else:
                    results['fixtures'] = (False, f"Status {resp.status}")

            # Check groups endpoint
            async with session.get(f"{BACKEND_URL}/api/groups/") as resp:
                if resp.status == 200:
                    groups = await resp.json()
                    results['groups'] = (True, f"{len(groups)} groups")
                else:
                    results['groups'] = (False, f"Status {resp.status}")

            # Check scenes endpoint
            async with session.get(f"{BACKEND_URL}/api/scenes/") as resp:
                if resp.status == 200:
                    scenes = await resp.json()
                    results['scenes'] = (True, f"{len(scenes)} scenes")
                else:
                    results['scenes'] = (False, f"Status {resp.status}")

            # Check WebSocket endpoint
            try:
                ws_url = f"ws://localhost:8000/ws"
                async with session.ws_connect(ws_url, timeout=2) as ws:
                    await ws.close()
                    results['websocket'] = (True, "Connected")
            except Exception as e:
                results['websocket'] = (False, str(e)[:30])

    except aiohttp.ClientError as e:
        results['connection'] = (False, str(e))

    return all(r[0] for r in results.values()), results

async def check_frontend() -> Tuple[bool, Dict]:
    """Check frontend is being served"""
    results = {}
    try:
        async with aiohttp.ClientSession() as session:
            # Check main page
            async with session.get(f"{FRONTEND_URL}/") as resp:
                if resp.status == 200:
                    results['dashboard'] = (True, "Available")
                else:
                    results['dashboard'] = (False, f"Status {resp.status}")

            # Check test frontend
            async with session.get(f"{FRONTEND_URL}/test_frontend.html") as resp:
                if resp.status == 200:
                    results['control'] = (True, "Available")
                else:
                    results['control'] = (False, f"Status {resp.status}")

            # Check OLA mock interface
            async with session.get(f"{FRONTEND_URL}/ola_mock_interface.html") as resp:
                if resp.status == 200:
                    results['ola_mock'] = (True, "Available")
                else:
                    results['ola_mock'] = (False, f"Status {resp.status}")

    except aiohttp.ClientError as e:
        results['connection'] = (False, str(e))

    return all(r[0] for r in results.values()), results

async def main():
    print(f"\n{Colors.BOLD}Tau Lighting Control System - Verification{Colors.ENDC}")
    print("=" * 50)

    # Check Backend
    print(f"\n{Colors.BLUE}Backend API (port 8000):{Colors.ENDC}")
    backend_ok, backend_results = await check_backend()

    if 'connection' in backend_results:
        print_status("Connection", False, backend_results['connection'][1])
    else:
        print_status("Health Check", *backend_results.get('health', (False, 'N/A')))
        print_status("Fixtures API", *backend_results.get('fixtures', (False, 'N/A')))
        print_status("Groups API", *backend_results.get('groups', (False, 'N/A')))
        print_status("Scenes API", *backend_results.get('scenes', (False, 'N/A')))
        print_status("WebSocket", *backend_results.get('websocket', (False, 'N/A')))

    # Check Frontend
    print(f"\n{Colors.BLUE}Frontend Server (port 3000):{Colors.ENDC}")
    frontend_ok, frontend_results = await check_frontend()

    if 'connection' in frontend_results:
        print_status("Connection", False, frontend_results['connection'][1])
    else:
        print_status("Main Dashboard", *frontend_results.get('dashboard', (False, 'N/A')))
        print_status("Lighting Control", *frontend_results.get('control', (False, 'N/A')))
        print_status("OLA Mock Interface", *frontend_results.get('ola_mock', (False, 'N/A')))

    # Print URLs
    if backend_ok and frontend_ok:
        print(f"\n{Colors.GREEN}✓ System fully operational!{Colors.ENDC}")
        print(f"\n{Colors.BLUE}Access URLs:{Colors.ENDC}")
        print(f"  • Main Dashboard:    {FRONTEND_URL}/")
        print(f"  • Lighting Control:  {FRONTEND_URL}/test_frontend.html")
        print(f"  • OLA Mock:          {FRONTEND_URL}/ola_mock_interface.html")
        print(f"  • API Documentation: {BACKEND_URL}/docs")
        print(f"  • System Status:     {BACKEND_URL}/status")
        sys.exit(0)
    else:
        print(f"\n{Colors.RED}✗ Some components are not working properly{Colors.ENDC}")
        if not backend_ok:
            print(f"  • Check if daemon is running: python -m tau.main")
        if not frontend_ok:
            print(f"  • Check if frontend server is running: python -m http.server 3000")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())