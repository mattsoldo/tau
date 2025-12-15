# macOS Deployment Guide for Tau Lighting System

This guide covers running Tau on macOS for both development (MacBook) and production (Mac mini).

## ✅ Compatibility

**Fully compatible with macOS**:
- macOS Ventura (13.0+)
- macOS Sonoma (14.0+)
- macOS Sequoia (15.0+)
- Apple Silicon (M1/M2/M3) and Intel processors

## 🚀 Quick Start (Development)

```bash
# 1. Run automated setup
chmod +x setup_mac.sh
./setup_mac.sh

# 2. Start the system
./start_tau.sh

# 3. Open browser
open http://localhost:3000
```

## 📦 Prerequisites

### Required Software

| Software | Installation | Purpose |
|----------|-------------|---------|
| Homebrew | `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"` | Package manager |
| Python 3.12 | `brew install python@3.12` | Runtime |
| PostgreSQL | `brew install postgresql@15` | Database |
| Git | `xcode-select --install` | Version control |

### Optional Hardware Support

| Hardware | Installation | Notes |
|----------|-------------|-------|
| OLA (DMX) | `brew install ola` | For real DMX output |
| LabJack | Download from [labjack.com](https://labjack.com/support/software/installers/ljm) | For physical switches |

## 🔧 Manual Installation

### 1. Install Dependencies

```bash
# Install Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install PostgreSQL
brew install postgresql@15
brew services start postgresql@15

# Install Python dependencies
python3.12 -m pip install -r requirements.txt
```

### 2. Database Setup

```bash
# Create database and user
createuser -s tau_daemon
createdb tau_lighting
psql -d tau_lighting -c "ALTER USER tau_daemon WITH PASSWORD 'tau_password';"

# Run migrations
export DATABASE_URL="postgresql://tau_daemon:tau_password@localhost/tau_lighting"
alembic upgrade head

# Load example data
python scripts/load_example_config.py
```

### 3. Environment Configuration

Create `.env` file:

```bash
# Database
DATABASE_URL=postgresql://tau_daemon:tau_password@localhost/tau_lighting

# Python
PYTHONPATH=/Users/soldo/code/tau/daemon/src

# Hardware (set to false for real hardware)
LABJACK_MOCK=true
OLA_MOCK=true

# API
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO
```

## 🖥️ Mac mini Production Deployment

### Option 1: User Application

Best for single-user setups or testing:

```bash
# Copy files to Applications folder
cp -r tau-daemon /Applications/

# Create alias for easy access
echo "alias tau='cd /Applications/tau-daemon && ./start_tau.sh'" >> ~/.zshrc

# Start on login (optional)
cp start_tau.sh ~/Library/LaunchAgents/
```

### Option 2: System Service (Recommended)

Best for dedicated Mac mini running 24/7:

```bash
# 1. Copy application to shared location
sudo cp -r tau-daemon /Users/Shared/

# 2. Create logs directory
sudo mkdir -p /Users/Shared/tau-daemon/logs

# 3. Install launchd service
sudo cp com.tau.daemon.plist /Library/LaunchDaemons/
sudo launchctl load /Library/LaunchDaemons/com.tau.daemon.plist

# 4. Start service
sudo launchctl start com.tau.daemon

# 5. Check status
sudo launchctl list | grep tau
```

### Managing the Service

```bash
# Start service
sudo launchctl start com.tau.daemon

# Stop service
sudo launchctl stop com.tau.daemon

# Restart service
sudo launchctl stop com.tau.daemon && sudo launchctl start com.tau.daemon

# View logs
tail -f /Users/Shared/tau-daemon/logs/tau-daemon.log

# Uninstall service
sudo launchctl unload /Library/LaunchDaemons/com.tau.daemon.plist
sudo rm /Library/LaunchDaemons/com.tau.daemon.plist
```

## 🔌 Hardware Configuration

### LabJack on macOS

1. Install drivers from [LabJack Downloads](https://labjack.com/support/software/installers/ljm)
2. Connect LabJack via USB
3. Test connection:
   ```bash
   # Install Python library
   pip install labjack-ljm

   # Test
   python -c "from labjack import ljm; ljm.openS('ANY', 'ANY', 'ANY')"
   ```
4. Set `LABJACK_MOCK=false` in `.env`

### OLA on macOS

1. Install OLA:
   ```bash
   brew install ola
   ```

2. Configure OLA:
   ```bash
   # Create config directory
   mkdir -p ~/.olad

   # Start OLA daemon
   olad -c ~/.olad

   # Open web interface
   open http://localhost:9090
   ```

3. Configure DMX output device in OLA web interface
4. Set `OLA_MOCK=false` in `.env`

## 🔒 Security Considerations

### Network Security

For Mac mini in production:

```bash
# 1. Enable firewall
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate on

# 2. Allow only local connections (modify .env)
API_HOST=127.0.0.1

# 3. For remote access, use SSH tunnel
ssh -L 8000:localhost:8000 user@mac-mini.local
```

### User Permissions

```bash
# Create dedicated user for daemon
sudo dscl . -create /Users/tau-daemon
sudo dscl . -create /Users/tau-daemon UserShell /usr/bin/false
sudo dscl . -create /Users/tau-daemon RealName "Tau Daemon"
sudo dscl . -create /Users/tau-daemon UniqueID 510
sudo dscl . -create /Users/tau-daemon PrimaryGroupID 20
```

## 🐛 Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| Port 8000 in use | `lsof -ti:8000 \| xargs kill -9` |
| PostgreSQL not starting | `brew services restart postgresql@15` |
| Python not found | `brew install python@3.12 && brew link python@3.12` |
| Permission denied | Check file ownership: `ls -la` |
| Service not starting | Check logs: `tail -f /Users/Shared/tau-daemon/logs/tau-daemon-error.log` |

### Debug Mode

```bash
# Run with debug logging
export LOG_LEVEL=DEBUG
python -m tau.main

# Check database connection
psql -U tau_daemon -d tau_lighting -c "SELECT COUNT(*) FROM fixtures;"

# Test API
curl http://localhost:8000/health
```

### Reset Everything

```bash
# Stop all services
./stop_tau.sh
brew services stop postgresql@15

# Drop database
dropdb tau_lighting
dropuser tau_daemon

# Remove files
rm -rf venv/
rm .env
rm *.log

# Start fresh
./setup_mac.sh
```

## 📊 Performance Tuning

### For Mac mini Production

```bash
# 1. Disable sleep
sudo pmset -a sleep 0
sudo pmset -a disablesleep 1

# 2. Set performance mode
sudo nvram boot-args="serverperfmode=1"

# 3. Increase file limits
sudo launchctl limit maxfiles 65536 200000

# 4. PostgreSQL tuning (edit /opt/homebrew/var/postgresql@15/postgresql.conf)
shared_buffers = 256MB
work_mem = 4MB
maintenance_work_mem = 64MB
effective_cache_size = 1GB
```

## 🔄 Auto-Start Configuration

### Login Items (GUI Method)
1. Open System Settings → General → Login Items
2. Click + and select `/Applications/tau-daemon/start_tau.sh`

### Command Line Method
```bash
osascript -e 'tell application "System Events" to make login item at end with properties {path:"/Applications/tau-daemon/start_tau.sh", hidden:false}'
```

## 📱 Remote Access

### From iPhone/iPad (on same network)

1. Find Mac's IP:
   ```bash
   ipconfig getifaddr en0  # For WiFi
   ipconfig getifaddr en1  # For Ethernet
   ```

2. Access from mobile browser:
   ```
   http://192.168.1.100:3000  # Replace with your Mac's IP
   ```

### Over Internet (using ngrok)

1. Install ngrok:
   ```bash
   brew install ngrok
   ```

2. Expose locally:
   ```bash
   ngrok http 3000
   ```

3. Access via provided URL

## ✅ Verification

Run the verification script to ensure everything is working:

```bash
python verify_system.py
```

Expected output:
```
✓ Health Check: v0.1.0
✓ Fixtures API: 5 fixtures
✓ Groups API: 4 groups
✓ Scenes API: 4 scenes
✓ WebSocket: Connected
✓ System fully operational!
```

## 📚 Additional Resources

- [LabJack macOS Guide](https://labjack.com/support/software/examples/ud/mac)
- [OLA macOS Documentation](https://www.openlighting.org/ola/tutorials/ola-on-mac/)
- [PostgreSQL on macOS](https://www.postgresql.org/download/macosx/)
- [launchd Documentation](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)

---

*Tau Lighting System - Optimized for macOS*