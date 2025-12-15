# Tau Lighting Control Daemon

A high-performance Python daemon for controlling smart lighting systems with circadian rhythm support, scene management, and physical switch integration. Designed for home automation and professional lighting installations.

## 🚀 Current Status: **FULLY OPERATIONAL**

All components are running and verified:
- ✅ Backend daemon (FastAPI) on port 8000
- ✅ Frontend server on port 3000
- ✅ PostgreSQL database with example data
- ✅ WebSocket real-time updates
- ✅ Mock hardware interfaces (LabJack & OLA)
- ✅ **Native macOS support** (Intel & Apple Silicon)

### 📋 Quick Access Links

| Interface | URL | Description |
|-----------|-----|-------------|
| **Main Dashboard** | http://localhost:3000/ | System overview and navigation |
| **Lighting Control** | http://localhost:3000/test_frontend.html | Full fixture/group/scene control |
| **OLA Mock Interface** | http://localhost:3000/ola_mock_interface.html | DMX channel visualization |
| **API Documentation** | http://localhost:8000/docs | Interactive Swagger UI |
| **API (ReDoc)** | http://localhost:8000/redoc | Alternative API docs |
| **System Status** | http://localhost:8000/status | Real-time system metrics |

### 🔍 Verify System Health

```bash
python verify_system.py  # Check all components
python demo_control.py   # Run lighting demo
```

### 🍎 macOS Quick Start

The system runs natively on macOS (Intel & Apple Silicon):

```bash
# Option 1: Double-click to start
open TauLighting.command

# Option 2: Automated setup
./setup_mac.sh

# Option 3: Test Mac compatibility
python test_mac_compatibility.py
```

See [MAC_DEPLOYMENT.md](MAC_DEPLOYMENT.md) for detailed macOS instructions.

## Features

- ⏰ **Circadian Rhythm Engine** - Automatic daylight simulation with customizable profiles
- 🎬 **Scene Management** - Capture and recall lighting presets
- 🎛️ **Physical Switch Integration** - Support for buttons, dimmers, and rotary encoders via LabJack
- 🌈 **Tunable White Control** - Brightness and color temperature (CCT) management
- 🔌 **DMX/OLA Output** - Professional lighting control via Open Lighting Architecture
- 🚀 **Real-Time Control** - 30 Hz event loop for responsive operation
- 🌐 **REST API** - Complete HTTP API for remote control
- ⚡ **WebSocket Streaming** - Real-time state updates to connected clients
- 📊 **Group Management** - Logical grouping of fixtures with independent control
- 🐳 **Docker Ready** - Production-ready containerization
- 🔧 **Mock Hardware** - Full functionality without physical hardware for testing

## Quick Start

### Docker (Recommended)

```bash
# Clone repository
git clone https://github.com/yourusername/tau-daemon.git
cd tau-daemon

# Configure environment
echo "POSTGRES_PASSWORD=your_secure_password" > .env

# Start services
docker-compose up -d

# Load example configuration
docker-compose exec tau-daemon python scripts/load_example_config.py

# Open API documentation
open http://localhost:8000/docs
```

The daemon will be available at:
- **REST API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **WebSocket**: ws://localhost:8000/ws

### Manual Installation

See [DEPLOYMENT.md](deployment/DEPLOYMENT.md) for detailed installation instructions.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      REST API / WebSocket                    │
│                       (FastAPI, Port 8000)                   │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────────┐
│                   Lighting Controller                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Circadian  │  │    Scene     │  │    Switch    │      │
│  │    Engine    │  │   Engine     │  │   Handler    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────────┐
│                    State Manager                             │
│         (In-memory state, periodic persistence)              │
└────────────────────────┬────────────────────────────────────┘
                         │
       ┌─────────────────┼─────────────────┐
       │                 │                 │
┌──────┴──────┐   ┌──────┴──────┐   ┌──────┴──────┐
│   LabJack   │   │   OLA/DMX   │   │  PostgreSQL │
│  (Inputs)   │   │  (Outputs)  │   │ (Persistence)│
└─────────────┘   └─────────────┘   └─────────────┘
```

### Core Components

#### Event Loop (src/tau/control/event_loop.py)
- Runs at 30 Hz (configurable)
- Coordinates all control subsystems
- Async/await architecture for efficiency

#### State Manager (src/tau/control/state_manager.py)
- In-memory fixture and group state
- Brightness (0.0-1.0) and CCT (Kelvin)
- Thread-safe access for control loop and API

#### Lighting Controller (src/tau/logic/controller.py)
- Orchestrates circadian, scenes, and switches
- Processes inputs → calculates targets → updates hardware
- Handles transitions and overrides

#### Hardware Manager (src/tau/hardware/manager.py)
- Abstraction layer for LabJack and OLA
- Mock drivers for testing
- Real driver stubs for production

#### REST API (src/tau/api/)
- FastAPI framework
- OpenAPI/Swagger documentation
- Pydantic validation
- Database access via SQLAlchemy

#### WebSocket (src/tau/api/websocket.py)
- Connection manager with subscriptions
- Real-time event broadcasting
- Event types: fixture_state_changed, scene_recalled, etc.

## Project Structure

```
daemon/
├── src/tau/                    # Main application code
│   ├── main.py                 # Entry point and daemon lifecycle
│   ├── config.py               # Settings (Pydantic)
│   ├── database.py             # SQLAlchemy async engine and sessions
│   │
│   ├── api/                    # FastAPI REST API
│   │   ├── __init__.py         # App creation, routers, WebSocket
│   │   ├── schemas.py          # Pydantic request/response models
│   │   ├── websocket.py        # WebSocket connection manager
│   │   └── routes/             # API endpoints
│   │       ├── fixtures.py     # Fixtures CRUD
│   │       ├── groups.py       # Groups CRUD and membership
│   │       ├── scenes.py       # Scenes CRUD, capture, recall
│   │       ├── control.py      # Direct control, panic mode
│   │       └── circadian.py    # Circadian profiles CRUD
│   │
│   ├── control/                # Control loop and state
│   │   ├── event_loop.py       # 30 Hz async event loop
│   │   └── state_manager.py    # In-memory state management
│   │
│   ├── hardware/               # Hardware abstraction
│   │   ├── manager.py          # Hardware manager
│   │   ├── labjack.py          # LabJack driver (real + mock)
│   │   └── ola.py              # OLA/DMX driver (real + mock)
│   │
│   ├── logic/                  # Lighting logic
│   │   ├── circadian.py        # Circadian rhythm engine
│   │   ├── scenes.py           # Scene engine
│   │   ├── switches.py         # Switch handler
│   │   ├── controller.py       # Lighting controller
│   │   └── utils.py            # Color mixing, interpolation
│   │
│   └── models/                 # SQLAlchemy ORM models
│       ├── base.py             # Base model class
│       ├── fixtures.py         # Fixture and FixtureModel
│       ├── groups.py           # Group and GroupFixture
│       ├── scenes.py           # Scene and SceneValue
│       ├── circadian.py        # CircadianProfile
│       ├── switches.py         # Switch and SwitchModel
│       └── state.py            # FixtureState and GroupState
│
├── alembic/                    # Database migrations
│   ├── versions/               # Migration scripts
│   └── env.py                  # Alembic configuration
│
├── deployment/                 # Production deployment
│   ├── tau-daemon.service      # systemd service file
│   └── DEPLOYMENT.md           # Deployment guide
│
├── examples/                   # Example configurations
│   ├── example_config.yaml     # Sample configuration
│   └── README.md               # Configuration documentation
│
├── scripts/                    # Utility scripts
│   └── load_example_config.py  # Load YAML into database
│
├── tests/                      # Test suite
│   ├── test_phase3_hardware.py # Hardware integration tests
│   ├── test_phase4_lighting.py # Lighting logic tests
│   ├── test_phase5_api.py      # API tests
│   ├── test_phase6_websocket.py# WebSocket tests
│   ├── test_unit_logic.py      # Unit tests (33 tests)
│   └── test_summary.md         # Test coverage report
│
├── docker-compose.yml          # Docker orchestration
├── Dockerfile                  # Container image
├── requirements.txt            # Python dependencies
├── alembic.ini                 # Alembic configuration
└── README.md                   # This file
```

## Installation

### Option 1: Docker (Recommended)

Docker is the easiest way to get started:

1. **Install Docker and Docker Compose**
   - Docker: https://docs.docker.com/get-docker/
   - Docker Compose: https://docs.docker.com/compose/install/

2. **Clone and configure**:
   ```bash
   git clone https://github.com/yourusername/tau-daemon.git
   cd tau-daemon
   echo "POSTGRES_PASSWORD=secure_password" > .env
   ```

3. **Start services**:
   ```bash
   docker-compose up -d
   ```

4. **Initialize database**:
   ```bash
   docker-compose exec tau-daemon alembic upgrade head
   docker-compose exec tau-daemon python scripts/load_example_config.py
   ```

### Option 2: Systemd (Linux)

For bare-metal installations:

1. **Install prerequisites**:
   ```bash
   sudo apt-get update
   sudo apt-get install -y python3.11 python3.11-venv postgresql
   ```

2. **Follow detailed instructions** in [deployment/DEPLOYMENT.md](deployment/DEPLOYMENT.md)

### Option 3: Local Development

For development without deployment:

1. **Create virtual environment**:
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```

3. **Set up PostgreSQL**:
   ```bash
   createdb tau_lighting
   alembic upgrade head
   ```

4. **Configure environment**:
   ```bash
   export DATABASE_URL="postgresql://user:pass@localhost/tau_lighting"
   export LABJACK_MOCK=true
   export OLA_MOCK=true
   export LOG_LEVEL=DEBUG
   ```

5. **Run daemon**:
   ```bash
   python -m tau.main
   ```

## Configuration

### Environment Variables

Configure the daemon via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://tau_daemon:tau_password@localhost/tau_lighting` |
| `DAEMON_PORT` | HTTP/WebSocket port | `8000` |
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `CONTROL_LOOP_HZ` | Event loop frequency (Hz) | `30` |
| `LABJACK_MOCK` | Use mock LabJack driver | `false` |
| `OLA_MOCK` | Use mock OLA/DMX driver | `false` |
| `API_DOCS_ENABLED` | Enable /docs endpoint | `true` |

### YAML Configuration

Define fixtures, groups, and scenes in YAML:

```yaml
# examples/my_config.yaml

fixture_models:
  - manufacturer: "Phillips"
    model: "Hue White Ambiance"
    type: "tunable_white"
    dmx_footprint: 2
    cct_min_kelvin: 2200
    cct_max_kelvin: 6500

fixtures:
  - name: "Living Room Ceiling"
    model: "Phillips Hue White Ambiance"
    dmx_channel_start: 1

groups:
  - name: "Living Room"
    circadian_enabled: true
    circadian_profile: "Standard Home"
    fixtures:
      - "Living Room Ceiling"

circadian_profiles:
  - name: "Standard Home"
    keyframes:
      - time: "06:00:00"
        brightness: 0.2
        cct: 2200
      - time: "12:00:00"
        brightness: 1.0
        cct: 5500
      - time: "22:00:00"
        brightness: 0.2
        cct: 2200

scenes:
  - name: "Movie Time"
    scope_group: "Living Room"
    values:
      - fixture: "Living Room Ceiling"
        brightness: 100  # 10%
        cct: 2200
```

Load configuration:

```bash
python scripts/load_example_config.py examples/my_config.yaml
```

See [examples/README.md](examples/README.md) for complete documentation.

## Usage

### REST API

The daemon provides a comprehensive REST API:

#### Control Fixtures

```bash
# Set fixture brightness and CCT
curl -X POST http://localhost:8000/api/control/fixtures/1 \
  -H "Content-Type: application/json" \
  -d '{"brightness": 0.8, "color_temp": 3000}'

# Turn fixture on/off
curl -X POST http://localhost:8000/api/control/fixtures/1/on
curl -X POST http://localhost:8000/api/control/fixtures/1/off
```

#### Control Groups

```bash
# Set group brightness
curl -X POST http://localhost:8000/api/control/groups/1 \
  -H "Content-Type: application/json" \
  -d '{"brightness": 0.5}'

# Suspend/resume circadian
curl -X POST http://localhost:8000/api/control/groups/1/circadian/suspend
curl -X POST http://localhost:8000/api/control/groups/1/circadian/resume
```

#### Scenes

```bash
# Recall a scene
curl -X POST http://localhost:8000/api/scenes/1/recall

# Capture current state as new scene
curl -X POST http://localhost:8000/api/scenes/capture \
  -H "Content-Type: application/json" \
  -d '{"name": "Reading Mode", "fixture_ids": [1, 2, 3]}'
```

#### Emergency Controls

```bash
# Turn all lights off
curl -X POST http://localhost:8000/api/control/all-off

# Panic mode (all lights 100%)
curl -X POST http://localhost:8000/api/control/panic
```

#### Status and Health

```bash
# Health check
curl http://localhost:8000/health

# System status
curl http://localhost:8000/status
```

### WebSocket

Real-time updates via WebSocket:

```javascript
// Connect
const ws = new WebSocket('ws://localhost:8000/ws');

// Subscribe to events
ws.send(JSON.stringify({
  action: 'subscribe',
  event_types: ['fixture_state_changed', 'scene_recalled']
}));

// Receive updates
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Event:', data.event_type, data);
  // Example: {event_type: "fixture_state_changed", fixture_id: 1, brightness: 0.8, ...}
};

// Keepalive
setInterval(() => {
  ws.send(JSON.stringify({action: 'ping'}));
}, 30000);
```

Event types:
- `fixture_state_changed` - Fixture brightness/CCT changed
- `group_state_changed` - Group state changed
- `scene_recalled` - Scene was recalled
- `scene_captured` - New scene captured
- `circadian_changed` - Circadian profile modified
- `hardware_status` - Hardware connection status
- `system_status` - System health status

### API Documentation

Interactive API documentation is available when the daemon is running:

- **Swagger UI**: http://localhost:8000/docs - Interactive API explorer
- **ReDoc**: http://localhost:8000/redoc - Alternative documentation UI
- **OpenAPI JSON**: http://localhost:8000/openapi.json - Machine-readable schema
- **API Reference**: [API_REFERENCE.md](API_REFERENCE.md) - Complete offline reference with examples

## Development

### Setup

```bash
# Clone repository
git clone https://github.com/yourusername/tau-daemon.git
cd tau-daemon

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies (including dev dependencies)
pip install -r requirements.txt
pip install -e .

# Install development tools
pip install pytest pytest-cov black isort flake8 mypy
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=tau --cov-report=html

# Run specific test file
pytest tests/test_phase4_lighting.py

# Run specific test
pytest tests/test_unit_logic.py::test_circadian_midnight_wraparound
```

### Code Quality

The project uses several tools to maintain code quality:

```bash
# Format code
black src/ tests/

# Sort imports
isort src/ tests/

# Lint
flake8 src/ tests/

# Type checking
mypy src/
```

Configuration:
- **Black**: Line length 100, Python 3.11+
- **isort**: Black-compatible profile
- **flake8**: Max line length 100
- **mypy**: Strict mode with async support

### Mock Hardware

For development without physical hardware:

```bash
export LABJACK_MOCK=true
export OLA_MOCK=true
python -m tau.main
```

Mock drivers:
- **LabJack**: Simulates digital/analog inputs, returns dummy values
- **OLA**: Accepts DMX data but doesn't output to hardware

### Database Migrations

Using Alembic for schema migrations:

```bash
# Create a new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View migration history
alembic history
```

### Adding Features

1. **Create branch**:
   ```bash
   git checkout -b feature/my-new-feature
   ```

2. **Implement feature**:
   - Add code to appropriate module
   - Add tests to `tests/`
   - Update documentation

3. **Test**:
   ```bash
   pytest
   black src/ tests/
   flake8 src/ tests/
   ```

4. **Commit**:
   ```bash
   git add .
   git commit -m "Add my new feature"
   ```

5. **Push and create PR**:
   ```bash
   git push origin feature/my-new-feature
   ```

## Testing

The project has comprehensive test coverage (~92%):

### Test Suite

- **test_phase3_hardware.py** - Hardware integration tests (LabJack, OLA, event loop)
- **test_phase4_lighting.py** - Lighting logic integration tests
- **test_phase5_api.py** - REST API endpoint tests
- **test_phase6_websocket.py** - WebSocket functionality tests
- **test_unit_logic.py** - 33 unit tests covering edge cases

### Test Coverage

See [tests/test_summary.md](tests/test_summary.md) for detailed coverage report.

Key tested components:
- ✅ Event loop (30 Hz, ~0.4ms iterations)
- ✅ State manager (fixtures, groups, thread safety)
- ✅ Hardware drivers (mock and real stubs)
- ✅ Circadian engine (interpolation, midnight wraparound)
- ✅ Scene engine (capture, recall)
- ✅ Switch handler (debouncing, multiple input types)
- ✅ Lighting controller (coordination)
- ✅ REST API (23 endpoints)
- ✅ WebSocket (connections, subscriptions, broadcasting)

### Running Tests

```bash
# All tests
pytest

# With verbose output
pytest -v

# Specific test file
pytest tests/test_unit_logic.py

# With coverage
pytest --cov=tau --cov-report=html
open htmlcov/index.html
```

## Deployment

For production deployment:

1. **Read deployment guide**: [deployment/DEPLOYMENT.md](deployment/DEPLOYMENT.md)

2. **Choose deployment method**:
   - Docker Compose (recommended for most users)
   - systemd (for bare-metal Linux installations)

3. **Security checklist**:
   - [ ] Change default database password
   - [ ] Configure firewall rules
   - [ ] Set up HTTPS reverse proxy (optional)
   - [ ] Enable automated backups
   - [ ] Configure monitoring/alerting

4. **Hardware setup**:
   - Connect LabJack U3-HV for switches
   - Connect USB-to-DMX adapter
   - Configure OLA for DMX output
   - Set `LABJACK_MOCK=false` and `OLA_MOCK=false`

5. **Load configuration**:
   ```bash
   python scripts/load_example_config.py your_config.yaml
   ```

6. **Test**:
   - Verify health check: `curl http://localhost:8000/health`
   - Check status: `curl http://localhost:8000/status`
   - Test API endpoints
   - Verify hardware output

## Hardware Requirements

### Production

- **Computer**: Linux NUC, Raspberry Pi 4, or similar
  - 2+ CPU cores
  - 2GB+ RAM
  - USB ports for peripherals

- **Input**: LabJack U3-HV or compatible
  - 16 digital I/O pins (buttons, switches)
  - 16 analog inputs (potentiometers, 0-2.4V)
  - USB connection

- **Output**: USB-to-DMX adapter
  - OLA compatible (Enttec, DMXKing, etc.)
  - 512 DMX channels per universe

### Development

No hardware required:
- Set `LABJACK_MOCK=true` and `OLA_MOCK=true`
- Full functionality with simulated I/O
- Perfect for testing and development

## Performance

Typical performance on Raspberry Pi 4:

- **Event loop**: 30 Hz (33ms period)
- **Iteration time**: 0.3-0.5 ms average
- **Memory usage**: 150-200 MB
- **CPU usage**: 5-10% (one core)
- **API latency**: < 50ms (local network)
- **WebSocket latency**: < 10ms

## Troubleshooting

### Service Won't Start

Check logs:
```bash
# Docker
docker-compose logs tau-daemon

# Systemd
sudo journalctl -u tau-daemon -f
```

Common issues:
- Database connection error → Check `DATABASE_URL`
- Port already in use → Change `DAEMON_PORT`
- Permission denied → Check file ownership

### Hardware Not Responding

```bash
# Check LabJack
lsusb | grep LabJack

# Check OLA
systemctl status olad
ola_dev_info

# Test DMX output
ola_streaming_client --dmx 255,255,255
```

### API Errors

```bash
# Check daemon status
curl http://localhost:8000/health
curl http://localhost:8000/status

# Check logs for exceptions
docker-compose logs tau-daemon | grep -i error
```

See [deployment/DEPLOYMENT.md](deployment/DEPLOYMENT.md) for comprehensive troubleshooting.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Follow code style guidelines (Black, isort, flake8)
6. Submit a pull request

### Development Process

1. **Issue**: Create or find an issue to work on
2. **Branch**: Create feature branch from `main`
3. **Code**: Implement feature with tests
4. **Test**: Run `pytest`, `black`, `flake8`, `mypy`
5. **Commit**: Clear commit messages
6. **PR**: Submit pull request with description

### Code Style

- **Formatting**: Black with 100 character lines
- **Imports**: isort with Black profile
- **Linting**: flake8 configured for Black
- **Types**: mypy strict mode
- **Docstrings**: Google style

## License

[Your License Here - e.g., MIT, Apache 2.0, GPL]

## Acknowledgments

- **FastAPI** - Modern async web framework
- **SQLAlchemy** - Python SQL toolkit and ORM
- **Open Lighting Architecture** - DMX/lighting control
- **LabJack** - Industrial I/O devices
- **PostgreSQL** - Robust open-source database

## Support

- **Documentation**:
  - [README.md](README.md) - Project overview and quick start
  - [API_REFERENCE.md](API_REFERENCE.md) - Complete API documentation with examples
  - [deployment/DEPLOYMENT.md](deployment/DEPLOYMENT.md) - Production deployment guide
  - [examples/README.md](examples/README.md) - Configuration documentation
  - [tests/test_summary.md](tests/test_summary.md) - Test coverage report
- **API Docs**: http://localhost:8000/docs - Interactive Swagger UI
- **Issues**: https://github.com/yourusername/tau-daemon/issues
- **Discussions**: https://github.com/yourusername/tau-daemon/discussions

## Roadmap

Future enhancements:
- [ ] Authentication and authorization
- [ ] Multi-universe DMX support
- [ ] Advanced scene transitions (fade, crossfade)
- [ ] Scheduler (time-based scene activation)
- [ ] Integration with home automation (Home Assistant, etc.)
- [ ] Mobile app for iOS/Android
- [ ] Zigbee/Z-Wave fixture support
- [ ] Alexa/Google Home integration
- [ ] Energy monitoring and reporting
