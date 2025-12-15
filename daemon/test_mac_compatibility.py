#!/usr/bin/env python3
"""
Mac Compatibility Test for Tau Lighting System
Tests all Mac-specific requirements and features
"""

import sys
import platform
import subprocess
import os
import shutil
from pathlib import Path

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header():
    print(f"\n{Colors.BOLD}Tau Lighting System - macOS Compatibility Test{Colors.ENDC}")
    print("=" * 50)

def check_os():
    """Check if running on macOS"""
    print(f"\n{Colors.BLUE}Operating System:{Colors.ENDC}")

    if platform.system() != "Darwin":
        print(f"{Colors.RED}✗{Colors.ENDC} Not running on macOS (found: {platform.system()})")
        return False

    mac_version = platform.mac_ver()[0]
    print(f"{Colors.GREEN}✓{Colors.ENDC} macOS {mac_version}")

    # Check architecture
    arch = platform.machine()
    if arch == "arm64":
        print(f"{Colors.GREEN}✓{Colors.ENDC} Apple Silicon (M1/M2/M3)")
    else:
        print(f"{Colors.GREEN}✓{Colors.ENDC} Intel ({arch})")

    return True

def check_python():
    """Check Python version"""
    print(f"\n{Colors.BLUE}Python Environment:{Colors.ENDC}")

    version = sys.version_info
    if version.major == 3 and version.minor >= 11:
        print(f"{Colors.GREEN}✓{Colors.ENDC} Python {version.major}.{version.minor}.{version.micro}")
    else:
        print(f"{Colors.YELLOW}⚠{Colors.ENDC} Python {version.major}.{version.minor}.{version.micro} (3.11+ recommended)")

    # Check for virtual environment
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print(f"{Colors.GREEN}✓{Colors.ENDC} Running in virtual environment")
    else:
        print(f"{Colors.YELLOW}⚠{Colors.ENDC} Not in virtual environment (recommended)")

    return True

def check_command(command):
    """Check if command exists"""
    return shutil.which(command) is not None

def check_dependencies():
    """Check required dependencies"""
    print(f"\n{Colors.BLUE}Dependencies:{Colors.ENDC}")

    deps = {
        "brew": ("Homebrew", "Required for package management"),
        "psql": ("PostgreSQL", "Required for database"),
        "git": ("Git", "Required for version control"),
        "python3": ("Python 3", "Required for runtime"),
    }

    optional = {
        "olad": ("OLA", "Optional for DMX output"),
        "ngrok": ("ngrok", "Optional for remote access"),
    }

    all_good = True

    # Required dependencies
    for cmd, (name, desc) in deps.items():
        if check_command(cmd):
            print(f"{Colors.GREEN}✓{Colors.ENDC} {name}: {desc}")
        else:
            print(f"{Colors.RED}✗{Colors.ENDC} {name}: {desc}")
            all_good = False

    # Optional dependencies
    print(f"\n{Colors.BLUE}Optional Dependencies:{Colors.ENDC}")
    for cmd, (name, desc) in optional.items():
        if check_command(cmd):
            print(f"{Colors.GREEN}✓{Colors.ENDC} {name}: {desc}")
        else:
            print(f"{Colors.YELLOW}○{Colors.ENDC} {name}: {desc}")

    return all_good

def check_ports():
    """Check if required ports are available"""
    print(f"\n{Colors.BLUE}Network Ports:{Colors.ENDC}")

    ports = {
        3000: "Frontend server",
        8000: "Backend API",
        5432: "PostgreSQL",
        9090: "OLA Web Interface (optional)"
    }

    import socket

    for port, service in ports.items():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', port))
        sock.close()

        if result == 0:
            if port in [3000, 8000]:
                print(f"{Colors.GREEN}✓{Colors.ENDC} Port {port} ({service}): In use (expected)")
            elif port == 5432:
                print(f"{Colors.GREEN}✓{Colors.ENDC} Port {port} ({service}): PostgreSQL running")
            else:
                print(f"{Colors.YELLOW}⚠{Colors.ENDC} Port {port} ({service}): In use")
        else:
            if port in [3000, 8000]:
                print(f"{Colors.YELLOW}⚠{Colors.ENDC} Port {port} ({service}): Available (not running)")
            elif port == 5432:
                print(f"{Colors.RED}✗{Colors.ENDC} Port {port} ({service}): PostgreSQL not running")
            else:
                print(f"{Colors.GREEN}✓{Colors.ENDC} Port {port} ({service}): Available")

    return True

def check_files():
    """Check required files exist"""
    print(f"\n{Colors.BLUE}Project Files:{Colors.ENDC}")

    required_files = [
        "requirements.txt",
        "src/tau/main.py",
        "index.html",
        "test_frontend.html",
    ]

    optional_files = [
        ".env",
        "TauLighting.command",
        "setup_mac.sh",
        "com.tau.daemon.plist",
    ]

    all_good = True

    for file in required_files:
        if Path(file).exists():
            print(f"{Colors.GREEN}✓{Colors.ENDC} {file}")
        else:
            print(f"{Colors.RED}✗{Colors.ENDC} {file} (missing)")
            all_good = False

    print(f"\n{Colors.BLUE}Configuration Files:{Colors.ENDC}")
    for file in optional_files:
        if Path(file).exists():
            print(f"{Colors.GREEN}✓{Colors.ENDC} {file}")
        else:
            print(f"{Colors.YELLOW}○{Colors.ENDC} {file} (optional)")

    return all_good

def check_permissions():
    """Check file permissions"""
    print(f"\n{Colors.BLUE}Permissions:{Colors.ENDC}")

    executables = [
        "TauLighting.command",
        "setup_mac.sh",
        "start_tau.sh",
        "stop_tau.sh",
    ]

    for file in executables:
        if Path(file).exists():
            if os.access(file, os.X_OK):
                print(f"{Colors.GREEN}✓{Colors.ENDC} {file} is executable")
            else:
                print(f"{Colors.YELLOW}⚠{Colors.ENDC} {file} is not executable (run: chmod +x {file})")
        else:
            print(f"{Colors.YELLOW}○{Colors.ENDC} {file} not found")

    return True

def check_labjack():
    """Check LabJack compatibility"""
    print(f"\n{Colors.BLUE}Hardware Support:{Colors.ENDC}")

    try:
        # Try importing the mock first
        from tau.hardware.labjack import LabJackManager
        print(f"{Colors.GREEN}✓{Colors.ENDC} LabJack mock interface available")

        # Check for real LabJack library
        try:
            import labjack
            print(f"{Colors.GREEN}✓{Colors.ENDC} LabJack Python library installed")
        except ImportError:
            print(f"{Colors.YELLOW}○{Colors.ENDC} LabJack library not installed (using mock)")
    except ImportError:
        print(f"{Colors.YELLOW}⚠{Colors.ENDC} Could not import LabJack interface")

    return True

def print_summary(all_checks_passed):
    """Print summary and recommendations"""
    print(f"\n{Colors.BOLD}Summary:{Colors.ENDC}")
    print("=" * 50)

    if all_checks_passed:
        print(f"{Colors.GREEN}✅ Your Mac is ready to run Tau Lighting System!{Colors.ENDC}")
        print("\nTo start the system:")
        print("  1. Double-click TauLighting.command")
        print("     OR")
        print("  2. Run: ./start_tau.sh")
        print("     OR")
        print("  3. Run: python -m tau.main")
    else:
        print(f"{Colors.YELLOW}⚠️ Some requirements are missing{Colors.ENDC}")
        print("\nTo complete setup:")
        print("  1. Run: ./setup_mac.sh")
        print("  2. Follow the prompts")
        print("  3. Run this test again")

    print(f"\n{Colors.BLUE}Quick Start Commands:{Colors.ENDC}")
    print("  Setup:    ./setup_mac.sh")
    print("  Start:    ./TauLighting.command")
    print("  Verify:   python verify_system.py")
    print("  Demo:     python demo_control.py")
    print("  Docs:     open MAC_DEPLOYMENT.md")

def main():
    print_header()

    # Run all checks
    checks = [
        ("OS", check_os()),
        ("Python", check_python()),
        ("Dependencies", check_dependencies()),
        ("Ports", check_ports()),
        ("Files", check_files()),
        ("Permissions", check_permissions()),
        ("Hardware", check_labjack()),
    ]

    all_passed = all(result for _, result in checks)

    print_summary(all_passed)

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())