# Raspberry Pi Deployment Guide

Complete guide for deploying Tau Lighting Control on Raspberry Pi with LabJack U3 connected via USB.

## Hardware Requirements

### Recommended Setup
- **Raspberry Pi 4** (2GB RAM minimum, 4GB recommended)
- **LabJack U3-HV** connected via USB
- **USB-to-DMX adapter** (Enttec, DMXKing, or OLA-compatible)
- **MicroSD card** (16GB+, Class 10)
- **Power supply** (Official 5V 3A recommended)

### Also Works On
- Raspberry Pi 3 B+ (reduce CONTROL_LOOP_HZ to 20)
- Raspberry Pi 5 (tested and working)

## Quick Start (Automated)

The easiest way to install on a fresh Raspberry Pi:

```bash
# Download and run setup script
cd ~
git clone https://github.com/mattsoldo/tau.git
cd tau/daemon
chmod +x setup_pi.sh
sudo ./setup_pi.sh
```

The script will interactively install:
1. **Backend** (required):
   - System dependencies (PostgreSQL, OLA, Python 3.11)
   - LabJack USB permissions
   - Tau daemon and database
   - Python dependencies
   - Systemd service

2. **Frontend** (optional):
   - Node.js 20.x LTS
   - Next.js web interface
   - Automatic build with Pi's IP
   - Systemd service

After installation:
- **Web UI**: `http://<pi-ip>:3000` (if frontend installed)
- **API**: `http://<pi-ip>:8000`
- **API Docs**: `http://<pi-ip>:8000/docs`
- **OLA**: `http://<pi-ip>:9090`

## Manual Installation

### 1. Prepare Raspberry Pi OS

```bash
# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install prerequisites
sudo apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    postgresql \
    postgresql-contrib \
    gcc \
    libusb-1.0-0-dev \
    git
```

### 2. Install OLA (DMX Output)

```bash
# Install OLA from package manager
sudo apt-get install -y ola

# Enable and start OLA daemon
sudo systemctl enable olad
sudo systemctl start olad

# Verify installation
ola_dev_info

# Access web UI at http://<pi-ip>:9090
```

### 3. Configure LabJack USB Permissions

**Why needed:** By default, USB devices require root access. This allows the `tau` user to access LabJack.

```bash
# Create udev rule
sudo tee /etc/udev/rules.d/99-labjack.rules > /dev/null <<EOF
SUBSYSTEM=="usb", ATTR{idVendor}=="0cd5", ATTR{idProduct}=="0009", MODE="0666", GROUP="plugdev"
EOF

# Reload udev rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# Verify LabJack is detected
lsusb | grep "0cd5:0009"
# Should show: Bus XXX Device XXX: ID 0cd5:0009 LabJack Corporation U3-HV
```

### 4. Create Tau User

```bash
# Create system user with plugdev group access
sudo useradd -r -s /bin/false -G plugdev tau

# Create installation directory
sudo mkdir -p /opt/tau-daemon
sudo chown tau:tau /opt/tau-daemon
```

### 5. Clone Repository

```bash
# Clone to installation directory
cd /opt/tau-daemon
sudo -u tau git clone https://github.com/mattsoldo/tau.git .
```

### 6. Python Environment

```bash
# Navigate to daemon directory
cd /opt/tau-daemon/daemon

# Create virtual environment
sudo -u tau python3.11 -m venv .venv

# Install dependencies
sudo -u tau .venv/bin/pip install --upgrade pip
sudo -u tau .venv/bin/pip install -r requirements.txt

# Install OLA Python bindings
sudo -u tau .venv/bin/pip install ola
```

### 7. PostgreSQL Database

```bash
# Create database user and database
sudo -u postgres createuser tau_daemon
sudo -u postgres createdb tau_lighting -O tau_daemon

# Set password (use a strong password!)
sudo -u postgres psql -c "ALTER USER tau_daemon WITH PASSWORD 'your_secure_password';"
```

### 8. Environment Configuration

```bash
# Create .env file
cd /opt/tau-daemon/daemon
sudo -u tau tee .env > /dev/null <<EOF
DATABASE_URL=postgresql://tau_daemon:your_secure_password@localhost/tau_lighting
DAEMON_PORT=8000
DAEMON_HOST=0.0.0.0
LOG_LEVEL=INFO
CONTROL_LOOP_HZ=30
USE_GPIO=false
CORS_ALLOW_ALL=true
EOF

# Secure the file (contains password)
sudo chmod 600 .env
```

### 9. Database Migrations

```bash
# Run migrations to create database schema
cd /opt/tau-daemon/daemon
sudo -u tau bash -c "source .env && .venv/bin/alembic upgrade head"
```

### 10. Load Example Configuration (Optional)

```bash
# Load example fixtures, groups, scenes
sudo -u tau bash -c "source .env && .venv/bin/python scripts/load_example_config.py"
```

### 11. Install Systemd Services

**Backend Service:**

```bash
# Copy service file
sudo cp /opt/tau-daemon/daemon/deployment/tau-daemon.service /etc/systemd/system/

# Update with your database password
sudo sed -i 's/tau_password/your_secure_password/g' /etc/systemd/system/tau-daemon.service

# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable tau-daemon
```

**Frontend Service (Optional):**

```bash
# Install Node.js 20.x
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

# Install dependencies
cd /opt/tau-daemon/frontend
sudo -u tau npm ci --production

# Build frontend
PI_IP=$(hostname -I | awk '{print $1}')
sudo -u tau bash -c "NEXT_PUBLIC_API_URL=http://$PI_IP:8000 NEXT_PUBLIC_WS_URL=ws://$PI_IP:8000 npm run build"

# Install service
sudo cp /opt/tau-daemon/daemon/deployment/tau-frontend.service /etc/systemd/system/
sudo sed -i "s|http://localhost:8000|http://$PI_IP:8000|g" /etc/systemd/system/tau-frontend.service
sudo sed -i "s|ws://localhost:8000|ws://$PI_IP:8000|g" /etc/systemd/system/tau-frontend.service

# Enable service
sudo systemctl daemon-reload
sudo systemctl enable tau-frontend
```

### 12. Start Services

```bash
# Start backend
sudo systemctl start tau-daemon
sudo systemctl status tau-daemon

# Start frontend (if installed)
sudo systemctl start tau-frontend
sudo systemctl status tau-frontend

# View logs
sudo journalctl -u tau-daemon -f
sudo journalctl -u tau-frontend -f
```

## Verification

### Check Services

```bash
# Tau daemon (backend)
systemctl status tau-daemon

# Tau frontend (web UI)
systemctl status tau-frontend

# PostgreSQL
systemctl status postgresql

# OLA daemon
systemctl status olad
```

### Test Web Interface

```bash
# Get Pi's IP
PI_IP=$(hostname -I | awk '{print $1}')
echo "Web UI: http://$PI_IP:3000"

# Open in browser from any device on network:
# http://<pi-ip>:3000
```

### Test API

```bash
# Health check
curl http://localhost:8000/health

# System status
curl http://localhost:8000/status

# API documentation (interactive)
# Open in browser: http://<pi-ip>:8000/docs
```

### Test Hardware

```bash
# LabJack detection
lsusb | grep LabJack
# Should show: ID 0cd5:0009 LabJack Corporation U3-HV

# Test OLA
ola_dev_info
# Should list DMX devices

# Test DMX output (red on channel 1-3)
ola_streaming_client --dmx 255,0,0
```

## Network Access

By default, the daemon listens on `0.0.0.0:8000`, making it accessible from your local network.

### Find Pi's IP Address

```bash
hostname -I
# First IP is typically your network address
```

### Access Points

From any device on your network:

- **API**: `http://<pi-ip>:8000`
- **API Docs**: `http://<pi-ip>:8000/docs`
- **OLA Web UI**: `http://<pi-ip>:9090`

### Firewall (Optional)

```bash
# Install UFW
sudo apt-get install -y ufw

# Allow SSH (important!)
sudo ufw allow 22/tcp

# Allow Tau daemon
sudo ufw allow 8000/tcp

# Allow OLA web UI
sudo ufw allow 9090/tcp

# Enable firewall
sudo ufw enable
```

## Performance Tuning

### Raspberry Pi 4 (Recommended)

Default settings work well:

```bash
CONTROL_LOOP_HZ=30  # 30Hz event loop
LOG_LEVEL=INFO
```

### Raspberry Pi 3

Reduce event loop frequency:

```bash
CONTROL_LOOP_HZ=20  # 20Hz instead of 30Hz
LOG_LEVEL=WARNING   # Reduce log verbosity
```

### Monitor Performance

```bash
# Watch CPU usage
htop

# Monitor daemon
sudo journalctl -u tau-daemon -f

# Check event loop performance in API
curl http://localhost:8000/status | jq '.event_loop'
```

## Configuration

### Switch Configuration

Configure physical switches connected to LabJack:

```bash
# Edit via API or database
curl http://localhost:8000/docs
# Navigate to /api/switches endpoints
```

See `examples/example_config.yaml` for reference configuration.

### DMX Fixtures

Configure DMX fixtures via OLA web interface:

```bash
# Open OLA web UI
http://<pi-ip>:9090

# Configure:
# 1. Add your USB DMX adapter under "Add Universe"
# 2. Set up fixtures and channels
# 3. Test DMX output
```

## Troubleshooting

### Daemon Won't Start

```bash
# Check logs
sudo journalctl -u tau-daemon -n 50

# Common issues:
# 1. Database connection error → Check DATABASE_URL in .env
# 2. LabJack not detected → Check USB permissions (lsusb, udev rules)
# 3. Port already in use → Change DAEMON_PORT in .env
```

### LabJack Not Detected

```bash
# Check USB connection
lsusb | grep "0cd5:0009"

# Check udev rules
cat /etc/udev/rules.d/99-labjack.rules

# Reload udev
sudo udevadm control --reload-rules
sudo udevadm trigger

# Reconnect LabJack USB
```

### OLA Not Working

```bash
# Check OLA daemon
systemctl status olad

# Restart OLA
sudo systemctl restart olad

# Check devices
ola_dev_info

# Check OLA web UI
http://<pi-ip>:9090
```

### Database Issues

```bash
# Check PostgreSQL is running
systemctl status postgresql

# Test connection
psql -U tau_daemon -d tau_lighting -h localhost
# Enter password when prompted

# Reset database (WARNING: deletes all data)
sudo -u postgres dropdb tau_lighting
sudo -u postgres createdb tau_lighting -O tau_daemon
cd /opt/tau-daemon/daemon
sudo -u tau bash -c "source .env && .venv/bin/alembic upgrade head"
```

### Slow Performance

```bash
# Check CPU usage
htop

# Reduce event loop frequency (in .env)
CONTROL_LOOP_HZ=20

# Restart daemon
sudo systemctl restart tau-daemon

# Monitor performance
curl http://localhost:8000/status | jq '.event_loop.avg_iteration_ms'
# Should be < 10ms
```

## Updating

### Update System

```bash
# Update OS packages
sudo apt-get update
sudo apt-get upgrade -y

# Reboot if kernel updated
sudo reboot
```

### Update Tau

```bash
# Pull latest code
cd /opt/tau-daemon
sudo -u tau git pull

# Update Python dependencies
cd daemon
sudo -u tau .venv/bin/pip install -r requirements.txt --upgrade

# Run database migrations
sudo -u tau bash -c "source .env && .venv/bin/alembic upgrade head"

# Restart daemon
sudo systemctl restart tau-daemon
```

## Backup

### Database Backup

```bash
# Create backup directory
sudo mkdir -p /backup/tau
sudo chown tau:tau /backup/tau

# Manual backup
sudo -u tau pg_dump -U tau_daemon tau_lighting > /backup/tau/backup_$(date +%Y%m%d).sql

# Automated daily backup (crontab)
sudo crontab -e -u tau
# Add line:
0 2 * * * pg_dump -U tau_daemon tau_lighting > /backup/tau/backup_$(date +\%Y\%m\%d).sql
```

### Restore Database

```bash
# Stop daemon
sudo systemctl stop tau-daemon

# Restore from backup
sudo -u postgres psql -U tau_daemon tau_lighting < /backup/tau/backup_20260103.sql

# Start daemon
sudo systemctl start tau-daemon
```

## Security

### Change Default Password

```bash
# Change database password
sudo -u postgres psql -c "ALTER USER tau_daemon WITH PASSWORD 'new_secure_password';"

# Update .env
sudo nano /opt/tau-daemon/daemon/.env
# Update DATABASE_URL with new password

# Update systemd service
sudo nano /etc/systemd/system/tau-daemon.service
# Update DATABASE_URL with new password

# Restart
sudo systemctl daemon-reload
sudo systemctl restart tau-daemon
```

### Restrict Network Access

```bash
# Edit .env to restrict CORS
CORS_ALLOW_ALL=false
CORS_ORIGINS=["http://192.168.1.100:3000"]

# Or use firewall to restrict by IP
sudo ufw allow from 192.168.1.0/24 to any port 8000
```

## Support

- **Documentation**: `/opt/tau-daemon/daemon/README.md`
- **API Docs**: `http://<pi-ip>:8000/docs`
- **Logs**: `sudo journalctl -u tau-daemon -f`
- **Issues**: https://github.com/mattsoldo/tau/issues
