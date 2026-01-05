# Tau Lighting Control - Custom Raspberry Pi Image

This directory contains the configuration and scripts to build a custom Raspberry Pi OS image with Tau Lighting Control pre-installed and ready to run.

## Overview

The custom image includes:

- **Raspberry Pi OS Lite** (64-bit, headless)
- **PostgreSQL 15** database server
- **Node.js 20 LTS** for the frontend
- **Python 3.11** with virtual environment
- **OLA (Open Lighting Architecture)** for DMX control
- **Tau Daemon** (backend) pre-configured
- **Tau Frontend** (Next.js) pre-built
- **Systemd services** for automatic startup
- **First-boot setup** for database initialization

## Prerequisites

### Hardware
- A computer running Linux, macOS, or Windows with WSL2
- At least 25GB free disk space
- 8GB+ RAM recommended
- Reliable internet connection

### Software
- **Docker Desktop** (recommended) - [Install Docker](https://docs.docker.com/get-docker/)
- **Git** - to clone this repository

For native builds (without Docker):
- Debian-based Linux distribution (Ubuntu, Debian, Raspberry Pi OS)
- `sudo` access
- Dependencies installed via `apt-get`

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/mattsoldo/tau.git
cd tau/pi-gen
```

### 2. Build the Image

```bash
# Using Docker (recommended)
./build.sh

# For a clean build (removes previous artifacts)
./build.sh --clean

# To continue a previously failed build
./build.sh --continue
```

The build process takes approximately **30-60 minutes** depending on your internet speed and computer performance.

### 3. Find the Output

After a successful build, the image will be located in:
- `pi-gen/output/tau-lighting-*.img.xz` (compressed)
- `pi-gen/pi-gen-repo/deploy/` (original output)

## Writing the Image to SD Card

### Option 1: Raspberry Pi Imager (Recommended)

1. Download [Raspberry Pi Imager](https://www.raspberrypi.com/software/)
2. Click "Choose OS" → "Use custom" → Select the `.img` file
3. Click "Choose Storage" → Select your SD card
4. Click the gear icon (⚙️) to configure:
   - Set hostname: `tau-controller`
   - Enable SSH
   - Configure WiFi (optional)
5. Click "Write"

### Option 2: Command Line (Linux/macOS)

```bash
# First, identify your SD card device
lsblk

# CAUTION: Replace /dev/sdX with your actual SD card device!
# DOUBLE-CHECK the device - this will erase all data!

# If the image is compressed (.img.xz)
xz -d tau-lighting-*.img.xz

# Write the image
sudo dd if=tau-lighting-*.img of=/dev/sdX bs=4M status=progress conv=fsync

# Sync and eject
sync
sudo eject /dev/sdX
```

### Option 3: Using balenaEtcher

1. Download [balenaEtcher](https://www.balena.io/etcher/)
2. Select the image file
3. Select your SD card
4. Click "Flash!"

## First Boot

1. Insert the SD card into your Raspberry Pi
2. Connect ethernet (recommended) or configure WiFi
3. Power on the Raspberry Pi
4. Wait 2-3 minutes for first boot setup to complete

The first boot will:
- Initialize the PostgreSQL database
- Run database migrations
- Start all Tau services

### Accessing the System

After first boot completes:

| Service | URL |
|---------|-----|
| **Web Interface** | `http://tau-controller.local/` or `http://<IP>/` |
| **API Documentation** | `http://tau-controller.local:8000/docs` |
| **OLA DMX Interface** | `http://tau-controller.local:9090` |

### SSH Access

```bash
ssh tau@tau-controller.local

# Default credentials:
# Username: tau
# Password: tau-lighting
```

**Important:** Change the default password after first login!

```bash
passwd
```

## Convenience Commands

The image includes several convenience commands:

```bash
# Show status of all Tau services
tau-status

# View live logs from daemon and frontend
tau-logs

# Restart all Tau services
tau-restart
```

## Configuration

### Environment Variables

The daemon configuration is stored in `/opt/tau-daemon/daemon/.env`:

```bash
sudo nano /opt/tau-daemon/daemon/.env
```

Key settings:
- `DATABASE_URL` - PostgreSQL connection string
- `DAEMON_PORT` - API server port (default: 8000)
- `CONTROL_LOOP_HZ` - Event loop frequency (default: 30)
- `LABJACK_MOCK` - Use mock hardware (default: false)
- `OLA_MOCK` - Use mock DMX (default: false)

### Database

```bash
# Access PostgreSQL
sudo -u postgres psql -d tau_lighting

# Reset database (WARNING: deletes all data)
sudo -u postgres dropdb tau_lighting
sudo -u postgres createdb tau_lighting -O tau_daemon
cd /opt/tau-daemon/daemon
sudo -u tau .venv/bin/alembic upgrade head
```

## Build Configuration

### Customizing the Image

Edit `pi-gen/config` to customize:

```bash
# Image name prefix
IMG_NAME="tau-lighting"

# Default hostname
TARGET_HOSTNAME="tau-controller"

# Locale and timezone
LOCALE_DEFAULT="en_US.UTF-8"
TIMEZONE_DEFAULT="America/New_York"

# First user credentials (change for security!)
FIRST_USER_NAME="tau"
FIRST_USER_PASS="tau-lighting"
```

### Adding Custom Stages

Create additional stage directories (`stage5-custom`, etc.) with:
- `packages` - APT packages to install
- `XX-run.sh` - Scripts to execute (numbered for ordering)
- `files/` - Files to copy into the image root

## Troubleshooting

### Build Fails

```bash
# Check Docker is running
docker info

# Clean and rebuild
./build.sh --clean

# Check logs in pi-gen-repo/work/
ls -la pi-gen-repo/work/
```

### Services Not Starting

```bash
# Check service status
systemctl status tau-daemon
systemctl status tau-frontend
systemctl status postgresql

# Check logs
journalctl -u tau-daemon -n 100
journalctl -u tau-frontend -n 100

# Manually run first boot setup
sudo /opt/tau-firstboot/tau-setup.sh
```

### Database Connection Issues

```bash
# Check PostgreSQL is running
systemctl status postgresql

# Verify database exists
sudo -u postgres psql -c "\l" | grep tau_lighting

# Check connection
psql -U tau_daemon -h localhost -d tau_lighting
```

### Cannot Find Pi on Network

```bash
# If tau-controller.local doesn't resolve, find IP via:

# From another Pi/Linux machine:
arp -a | grep -i raspberry

# Or check your router's DHCP client list

# Connect using IP directly:
ssh tau@192.168.1.xxx
```

## Architecture

```
pi-gen/
├── config              # Main pi-gen configuration
├── build.sh            # Build automation script
├── stage3-tau/         # Stage 3: System packages
│   ├── packages        # APT packages to install
│   ├── 00-run.sh       # Create tau user
│   ├── 01-run.sh       # Configure PostgreSQL
│   ├── 02-run.sh       # Install Node.js
│   ├── 03-run.sh       # Configure OLA
│   └── 04-run.sh       # LabJack USB permissions
├── stage4-tau/         # Stage 4: Application setup
│   ├── 00-run.sh       # Create directories
│   ├── 01-run.sh       # Copy tau source files
│   ├── 02-run.sh       # Python venv & dependencies
│   ├── 03-run.sh       # Build frontend
│   ├── 04-run.sh       # Create .env configuration
│   ├── 05-run.sh       # Install systemd services
│   ├── 06-run.sh       # First boot setup script
│   ├── 07-run.sh       # Enable services & MOTD
│   └── EXPORT_IMAGE    # Marker to export image
└── output/             # Built images (after build)
```

## Security Considerations

The default image has a known password for ease of setup. For production use:

1. **Change the default password immediately**
   ```bash
   passwd
   ```

2. **Change the database password**
   ```bash
   sudo -u postgres psql -c "ALTER USER tau_daemon WITH PASSWORD 'new_secure_password';"
   # Update /opt/tau-daemon/daemon/.env with new password
   sudo systemctl restart tau-daemon
   ```

3. **Configure firewall**
   ```bash
   sudo apt-get install ufw
   sudo ufw allow 22/tcp   # SSH
   sudo ufw allow 80/tcp   # Web UI
   sudo ufw allow 8000/tcp # API
   sudo ufw enable
   ```

4. **Disable password authentication for SSH** (after setting up keys)
   ```bash
   sudo nano /etc/ssh/sshd_config
   # Set: PasswordAuthentication no
   sudo systemctl restart ssh
   ```

## Support

- **Documentation**: See `/opt/tau-daemon/daemon/README.md` on the Pi
- **API Docs**: Visit `http://tau-controller.local:8000/docs`
- **Issues**: https://github.com/mattsoldo/tau/issues
