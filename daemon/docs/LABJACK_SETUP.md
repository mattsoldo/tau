# LabJack Hardware Setup Guide

## Overview

The Tau Lighting Control system supports LabJack U3-LV and U3-HV USB data acquisition devices for analog/digital I/O and PWM control.

`★ Insight ─────────────────────────────────────`
Docker containers need special permissions to access USB devices. The three main approaches are:
1. **Privileged mode**: Easiest but grants full host access
2. **Device mapping**: More secure, maps specific USB devices
3. **Device cgroups**: Most secure, grants specific device permissions
`─────────────────────────────────────────────────`

## Hardware Support Status

| Feature | Mock Mode | Real Hardware |
|---------|-----------|---------------|
| Analog Inputs (16 channels) | ✅ Working | ✅ Implemented |
| PWM Outputs (2 channels) | ✅ Working | ✅ Implemented |
| Digital I/O | ⚠️ Partial | ⚠️ Partial |
| Model Detection | ✅ Working | ✅ Implemented |
| Web Interface | ✅ Working | ✅ Working |

## Prerequisites

### 1. Hardware Requirements
- LabJack U3-LV (0-2.4V range) or U3-HV (±10V range)
- USB 2.0 port
- USB cable (included with LabJack)

### 2. Software Requirements
```bash
# Install LabJack driver and Python library
pip install LabJackPython

# Linux: Install USB libraries (already in Docker image)
sudo apt-get install libusb-1.0-0 libusb-1.0-0-dev
```

## Running with Real Hardware

### Option 1: Native (No Docker)

```bash
# Set environment to use real hardware
export LABJACK_MOCK=false
export OLA_MOCK=true  # Keep OLA in mock unless you have it
export DATABASE_URL="postgresql://tau_daemon:password@localhost/tau_lighting"

# Run the daemon
python -m tau.main
```

### Option 2: Docker with USB Access

#### Step 1: Find Your LabJack Device

```bash
# List USB devices to find LabJack
lsusb | grep -i labjack
# Example output: Bus 001 Device 004: ID 0cd5:0003 LabJack Corporation U3

# Note the bus and device numbers
```

#### Step 2: Configure Docker Compose

Edit `docker-compose.production.yml`:

```yaml
tau-daemon:
  # Choose ONE of these USB access methods:

  # Method 1: Privileged (easiest for testing)
  privileged: true

  # Method 2: Device mapping (recommended)
  devices:
    - /dev/bus/usb/001/004:/dev/bus/usb/001/004  # Use your actual device path

  # Method 3: Device cgroups (most secure)
  device_cgroup_rules:
    - 'c 189:* rwm'  # USB device access
```

#### Step 3: Run with Production Configuration

```bash
# Create .env file with production settings
cat > .env << EOF
POSTGRES_PASSWORD=your_secure_password
LOG_LEVEL=INFO
EOF

# Start with real hardware support
docker-compose -f docker-compose.production.yml up -d

# Check logs
docker-compose -f docker-compose.production.yml logs -f tau-daemon
```

## USB Device Permissions (Linux)

If you get permission errors, create a udev rule:

```bash
# Create udev rule for LabJack devices
sudo tee /etc/udev/rules.d/50-labjack.rules << EOF
# LabJack U3
SUBSYSTEM=="usb", ATTR{idVendor}=="0cd5", MODE="0666"
EOF

# Reload udev rules
sudo udevadm control --reload-rules
sudo udevadm trigger
```

## Testing the Connection

### 1. Check API Status

```bash
# Check if LabJack is connected
curl http://localhost:8000/api/labjack/status | jq

# Expected response with real hardware:
{
  "connected": true,
  "model": "U3-LV",  # or "U3-HV"
  "serial_number": "320012345",
  "mock_mode": false,
  ...
}
```

### 2. Test Analog Input Reading

```bash
# Read channels 0-3
curl -X POST http://localhost:8000/api/labjack/read \
  -H "Content-Type: application/json" \
  -d '{"channels": [0, 1, 2, 3]}' | jq
```

### 3. Test PWM Output

```bash
# Set PWM channel 0 to 50% duty cycle
curl -X POST http://localhost:8000/api/labjack/pwm \
  -H "Content-Type: application/json" \
  -d '{"outputs": {"0": 0.5}}' | jq
```

### 4. Access Web Interface

Open http://localhost:3000/labjack_monitor.html to see the real-time monitoring interface.

## Troubleshooting

### Issue: "LabJackPython library not installed"

```bash
# Install the library
pip install LabJackPython

# For Docker, rebuild the image
docker-compose -f docker-compose.production.yml build
```

### Issue: "Permission denied" accessing USB device

```bash
# Add user to dialout group (Linux)
sudo usermod -a -G dialout $USER

# Logout and login again for changes to take effect
```

### Issue: "No LabJack Found"

1. Check USB connection
2. Verify device appears in `lsusb`
3. Try unplugging and reconnecting
4. Check Docker device mapping if using containers

### Issue: Docker can't access USB device

```bash
# Option 1: Run with privileged mode (for testing)
docker run --privileged ...

# Option 2: Map the entire USB bus
docker run -v /dev/bus/usb:/dev/bus/usb ...

# Option 3: Use docker-compose.production.yml with correct device path
```

## Pin Configuration

### LabJack U3 Pin Mapping

| Channel | Pin Name | Location | Default Mode |
|---------|----------|----------|--------------|
| 0-7 | FIO0-7 | DB15 connector | Analog Input |
| 8-15 | EIO0-7 | DB15 connector | Analog Input |
| PWM 0 | FIO4 | DB15 pin 5 | Timer0/PWM |
| PWM 1 | FIO5 | DB15 pin 6 | Timer1/PWM |

### Voltage Ranges

- **U3-LV**: 0 to 2.4V (Low Voltage)
- **U3-HV**: ±10V (High Voltage)

## Performance Considerations

- **Sampling Rate**: Default 1 Hz per channel
- **PWM Frequency**: ~732 Hz with 16-bit resolution
- **USB Latency**: Typically < 1ms
- **Docker Overhead**: Minimal with direct device mapping

## Security Notes

When running in production:

1. **Never use privileged mode** in production - use specific device mapping
2. **Set proper file permissions** for device access
3. **Use environment variables** for sensitive configuration
4. **Monitor error logs** for hardware failures
5. **Implement proper error handling** for device disconnections

## Next Steps

1. Connect your LabJack U3 device
2. Configure Docker or run natively
3. Test with the web interface
4. Integrate with your lighting control logic
5. Set up monitoring and alerts for hardware issues