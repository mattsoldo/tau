# Tau Lighting Control on Raspberry Pi

This guide explains how to set up and run the Tau Lighting Control System on a Raspberry Pi.

## Quick Start

Run this single command on your Raspberry Pi to install and start Tau:

```bash
curl -fsSL https://raw.githubusercontent.com/YOUR_ORG/tau/main/scripts/pi-setup.sh | bash
```

Or download and run manually:

```bash
wget https://raw.githubusercontent.com/YOUR_ORG/tau/main/scripts/pi-setup.sh
chmod +x pi-setup.sh
./pi-setup.sh
```

## Requirements

### Hardware
- Raspberry Pi 3, 4, or 5 (any model with GPIO)
- 2GB+ RAM recommended
- MicroSD card (16GB+ recommended)
- Network connection (Ethernet or WiFi)

### Software
- Raspberry Pi OS (64-bit recommended)
- Python 3.11+
- PostgreSQL 15+
- Node.js 20+ (for web frontend)

## Installation Options

### Using GPIO for Switch Inputs (Default)

The default configuration uses Raspberry Pi GPIO pins for switch inputs:

```bash
./pi-setup.sh --gpio
```

### Using LabJack U3

If you have a LabJack U3 connected via USB:

```bash
./pi-setup.sh --labjack
```

### Without Frontend

To install only the backend daemon:

```bash
./pi-setup.sh --no-frontend
```

## GPIO Pin Configuration

### Default Pin Assignments

| Channel | GPIO Pin | Physical Pin | Function |
|---------|----------|--------------|----------|
| 0       | GPIO 17  | Pin 11       | Switch Input |
| 1       | GPIO 27  | Pin 13       | Switch Input |
| 2       | GPIO 22  | Pin 15       | Switch Input |
| 3       | GPIO 23  | Pin 16       | Switch Input |
| 4       | GPIO 24  | Pin 18       | Switch Input |
| 5       | GPIO 25  | Pin 22       | Switch Input |
| 6       | GPIO 5   | Pin 29       | Switch Input |
| 7       | GPIO 6   | Pin 31       | Switch Input |

### PWM Output Pins (Hardware PWM)

| Channel | GPIO Pin | Physical Pin | Function |
|---------|----------|--------------|----------|
| 0       | GPIO 12  | Pin 32       | PWM Output (LED Driver) |
| 1       | GPIO 13  | Pin 33       | PWM Output (LED Driver) |

### Custom Pin Mapping

Edit the `.env` file to customize pin assignments:

```bash
# Custom input pin mapping (format: channel:gpio_pin)
GPIO_INPUT_PINS=0:17,1:27,2:22,3:23

# Custom PWM pin mapping
GPIO_PWM_PINS=0:12,1:13
```

## Wiring Diagrams

### Switch Input Wiring

Connect switches between GPIO pins and ground. The internal pull-up resistors are enabled by default.

```
GPIO Pin ─────┬───── Switch ───── GND
              │
         Internal
         Pull-up
```

When the switch is open, the GPIO reads HIGH (3.3V).
When the switch is closed, the GPIO reads LOW (0V).

### PWM Output Wiring

Connect LED drivers to the PWM output pins:

```
GPIO 12 ─────── LED Driver Signal Input
GND ─────────── LED Driver GND
```

For high-power LED drivers, use a transistor or MOSFET:

```
GPIO 12 ─────── 1kΩ ─────┬───── MOSFET Gate
                         │
                    10kΩ to GND

MOSFET Drain ───── LED Driver -
MOSFET Source ───── GND
```

## Network Access

The web interface is accessible from any device on your network.

### Finding Your Pi's IP Address

```bash
hostname -I
```

### Accessing the Web Interface

Open a browser on any device and navigate to:

- **Web Interface**: `http://<PI_IP>:3000`
- **API Documentation**: `http://<PI_IP>:8000/docs`
- **API Health Check**: `http://<PI_IP>:8000/health`

### Enabling CORS for Network Access

If you have issues accessing the API from other devices, enable CORS in `.env`:

```bash
CORS_ALLOW_ALL=true
```

## Service Management

Tau runs as a systemd service that starts automatically on boot.

### Check Service Status

```bash
sudo systemctl status tau-daemon
sudo systemctl status tau-frontend
```

### View Logs

```bash
# Live log stream
sudo journalctl -u tau-daemon -f

# Recent logs
sudo journalctl -u tau-daemon -n 100
```

### Restart Services

```bash
sudo systemctl restart tau-daemon
sudo systemctl restart tau-frontend
```

### Stop/Start Services

```bash
sudo systemctl stop tau-daemon
sudo systemctl start tau-daemon
```

## Configuration

The main configuration file is located at `~/tau/.env`.

### Key Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `USE_GPIO` | `true` | Use Raspberry Pi GPIO instead of LabJack |
| `GPIO_USE_PIGPIO` | `true` | Use pigpio for hardware PWM |
| `GPIO_PULL_UP` | `true` | Enable internal pull-up resistors |
| `DAEMON_PORT` | `8000` | API server port |
| `DAEMON_HOST` | `0.0.0.0` | Bind to all network interfaces |
| `FRONTEND_PORT` | `3000` | Web frontend port |
| `CORS_ALLOW_ALL` | `false` | Allow CORS from any origin |

### Example Configuration for Raspberry Pi

```bash
# Database
DATABASE_URL=postgresql://tau_daemon:tau_dev_password@localhost:5432/tau_lighting

# Daemon
DAEMON_PORT=8000
DAEMON_HOST=0.0.0.0
LOG_LEVEL=INFO

# Hardware
USE_GPIO=true
GPIO_USE_PIGPIO=true
GPIO_PULL_UP=true
LABJACK_MOCK=false
OLA_MOCK=true

# CORS for network access
CORS_ALLOW_ALL=true

# Frontend
NODE_ENV=production
FRONTEND_PORT=3000
NEXT_PUBLIC_API_URL=http://192.168.1.100:8000
NEXT_PUBLIC_WS_URL=ws://192.168.1.100:8000
```

## Using with LabJack U3

The Raspberry Pi can also work with a LabJack U3 connected via USB.

### Installation

1. Install LabJack Exodriver:
   ```bash
   git clone https://github.com/labjack/exodriver.git
   cd exodriver
   sudo ./install.sh
   ```

2. Configure `.env`:
   ```bash
   USE_GPIO=false
   LABJACK_MOCK=false
   ```

3. Restart the daemon:
   ```bash
   sudo systemctl restart tau-daemon
   ```

### USB Permissions

Add your user to the dialout group for USB access:

```bash
sudo usermod -a -G dialout $USER
```

Log out and back in for changes to take effect.

## Troubleshooting

### GPIO Permission Errors

If you see permission errors for GPIO:

```bash
sudo usermod -a -G gpio $USER
```

Log out and back in.

### pigpiod Not Running

The pigpio daemon is required for hardware PWM:

```bash
sudo systemctl enable pigpiod
sudo systemctl start pigpiod
```

### Database Connection Errors

Check PostgreSQL is running:

```bash
sudo systemctl status postgresql
```

Verify the database exists:

```bash
sudo -u postgres psql -l
```

### Service Won't Start

Check the logs for errors:

```bash
sudo journalctl -u tau-daemon -n 50 --no-pager
```

### Web Interface Not Accessible

1. Check the daemon is running:
   ```bash
   curl http://localhost:8000/health
   ```

2. Check firewall settings:
   ```bash
   sudo ufw status
   sudo ufw allow 8000
   sudo ufw allow 3000
   ```

3. Verify CORS is configured:
   ```bash
   grep CORS ~/tau/.env
   ```

## Performance Optimization

### Reduce Memory Usage

For low-memory Pi models, disable development features:

```bash
NODE_ENV=production
API_DOCS_ENABLED=false
LOG_LEVEL=WARNING
```

### Improve PWM Quality

For smoother PWM output, ensure pigpio is running:

```bash
sudo systemctl status pigpiod
```

pigpio provides hardware-timed PWM at up to 1MHz resolution.

## Updating

To update to the latest version:

```bash
cd ~/tau
git pull origin main
cd daemon
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
cd ../frontend
npm install
npm run build
sudo systemctl restart tau-daemon
sudo systemctl restart tau-frontend
```

## Uninstalling

To completely remove Tau:

```bash
# Stop and disable services
sudo systemctl stop tau-daemon tau-frontend
sudo systemctl disable tau-daemon tau-frontend

# Remove service files
sudo rm /etc/systemd/system/tau-daemon.service
sudo rm /etc/systemd/system/tau-frontend.service
sudo systemctl daemon-reload

# Remove database
sudo -u postgres psql -c "DROP DATABASE tau_lighting;"
sudo -u postgres psql -c "DROP USER tau_daemon;"

# Remove installation directory
rm -rf ~/tau
```
