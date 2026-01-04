# Tau Smart Lighting Control System

A professional-grade smart lighting control system that provides intelligent, circadian-aware lighting control for residential and commercial environments. Runs on a Linux-based NUC and interfaces with physical hardware (LabJack U3-HV for inputs, USB-to-DMX for outputs) while providing a modern web interface for control and configuration.

## Project Status

**Phase 1: Foundation & Infrastructure** ✅ COMPLETED

- [x] Project structure and Docker environment
- [x] PostgreSQL database schema with migrations
- [x] Python daemon foundation with FastAPI
- [x] Next.js frontend setup with TypeScript
- [x] Logging and configuration management

**Next Steps: Phase 2 - Control Daemon Core**

## Features

### Hardware Integration
- Physical switch/dimmer control via LabJack U3-HV
- DMX512 lighting output via OLA (Open Lighting Architecture)
- Support for various fixture types (dimmable, dim-to-warm, tunable white)
- Real-time input processing with sophisticated state machines

### Intelligent Control
- Circadian lighting programs that adjust throughout the day
- Scene management for preset configurations
- Group control with multi-level nesting (up to 4 levels)
- State persistence across system restarts
- DMX channel collision detection

### User Interface
- Modern responsive web UI (mobile/tablet/desktop)
- Real-time updates via WebSocket
- Circadian schedule visualization
- Scene activation and management

## Architecture

```
tau/
├── daemon/               # Python control daemon
│   ├── src/tau/         # Application source code
│   │   ├── main.py      # Entry point
│   │   ├── config.py    # Configuration management
│   │   ├── database.py  # Database ORM layer
│   │   ├── api/         # FastAPI REST API
│   │   ├── hardware/    # LabJack & OLA interfaces (Phase 3)
│   │   ├── control/     # Control loop (Phase 2)
│   │   ├── lighting/    # Lighting algorithms (Phase 4)
│   │   └── models/      # SQLAlchemy models (Phase 2)
│   ├── tests/           # Test suite
│   ├── alembic/         # Database migrations
│   └── config/          # Systemd service files
│
├── frontend/            # Next.js web application
│   ├── src/
│   │   ├── app/         # Next.js App Router pages
│   │   ├── components/  # React components
│   │   ├── lib/         # API client & utilities
│   │   ├── hooks/       # Custom React hooks
│   │   ├── stores/      # Zustand state management
│   │   └── types/       # TypeScript definitions
│   └── public/          # Static assets
│
├── database/            # Database schema & migrations
│   ├── init.sql         # Initial schema with indexes
│   ├── migrations/      # Alembic migrations
│   └── seeds/           # Seed data
│
├── specs/               # Project specifications
├── docs/                # Documentation
├── scripts/             # Utility scripts
└── docker-compose.yml   # Development environment
```

## Technology Stack

### Backend
- **Language**: Python 3.11+
- **Framework**: FastAPI (async REST API)
- **Database**: PostgreSQL 15+ with asyncpg
- **ORM**: SQLAlchemy 2.0 (async)
- **Migrations**: Alembic
- **Hardware**: LabJackPython, OLA Python bindings
- **Logging**: structlog with JSON output

### Frontend
- **Framework**: Next.js 14+ (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **State**: Zustand
- **Data Fetching**: TanStack React Query
- **Real-time**: Socket.io / WebSocket
- **Charts**: Recharts

### Infrastructure
- **Container**: Docker & Docker Compose
- **Process Manager**: systemd
- **Reverse Proxy**: Nginx (optional)
- **Database**: PostgreSQL in Docker

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Node.js 20+ (for local frontend development)
- Python 3.11+ (for local daemon development)

### Development Setup

1. **Clone and setup environment**:
```bash
cd tau
cp .env.example .env
# Edit .env with your configuration
```

2. **Start all services with Docker**:
```bash
docker-compose up
```

Services will be available at:
- Frontend: http://localhost:3000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Database: localhost:5432

### Local Development (Without Docker)

**Database**:
```bash
# Start PostgreSQL with Docker
docker-compose up database

# Or use local PostgreSQL
createdb tau_lighting
psql tau_lighting < database/init.sql
```

**Daemon**:
```bash
cd daemon
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
python -m tau.main
```

**Frontend**:
```bash
cd frontend
npm install
npm run dev
```

## Database Management

### Migrations

```bash
cd daemon

# Upgrade to latest
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "Description"

# View history
alembic history
```

See [database/README.md](database/README.md) for more details.

## Configuration

Configuration is managed via environment variables. See `.env.example` for all available options.

### Key Settings

**Database**:
- `DATABASE_URL`: PostgreSQL connection string

**Daemon**:
- `DAEMON_PORT`: API port (default: 8000)
- `LOG_LEVEL`: Logging level (DEBUG/INFO/WARNING/ERROR)
- `LABJACK_MOCK`: Use mock hardware (true/false)
- `OLA_MOCK`: Use mock DMX (true/false)

**Frontend** (optional - auto-detected from browser hostname):
- `NEXT_PUBLIC_API_URL`: Backend API URL (default: auto-detected)
- `NEXT_PUBLIC_WS_URL`: WebSocket connection URL (default: auto-detected)

## Testing

**Python**:
```bash
cd daemon
pytest
pytest --cov=tau  # With coverage
```

**Frontend**:
```bash
cd frontend
npm test
npm run type-check
```

## Production Deployment

### On Linux NUC

1. **Install system dependencies**:
```bash
sudo apt-get update
sudo apt-get install postgresql python3.11 python3-pip nginx
```

2. **Setup database**:
```bash
sudo -u postgres createdb tau_lighting
sudo -u postgres createuser tau_daemon
psql -U postgres < database/init.sql
```

3. **Install daemon**:
```bash
cd /opt/tau/daemon
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .

# Install systemd service
sudo cp config/tau-daemon.service /etc/systemd/system/
sudo systemctl enable tau-daemon
sudo systemctl start tau-daemon
```

4. **Build and deploy frontend**:
```bash
cd /opt/tau/frontend
npm install
npm run build
npm start  # Or serve via Nginx
```

5. **Configure Nginx** (optional):
```nginx
server {
    listen 80;
    server_name tau.local;

    location / {
        proxy_pass http://localhost:3000;
    }

    location /api {
        proxy_pass http://localhost:8000;
    }
}
```

### Using Docker

```bash
# Production build
docker-compose -f docker-compose.yml up -d

# Or build custom images
docker build -t tau-daemon ./daemon
docker build -t tau-frontend ./frontend
```

## Hardware Setup

### LabJack U3-HV (Switch Inputs)
- Connect switches to digital/analog pins
- Configure pin mappings in database
- Install LabJack drivers and Python library

### OLA (DMX Output)
- Install OLA (Open Lighting Architecture)
- Configure USB-to-DMX adapter
- Test DMX output: `ola_dev_info`

### Mock Mode (Development)
Set `LABJACK_MOCK=true` and `OLA_MOCK=true` for development without hardware.

## Development Roadmap

### ✅ Phase 1: Foundation & Infrastructure (COMPLETED)
- [x] Database schema and migrations
- [x] Docker Compose setup
- [x] Python daemon foundation
- [x] Next.js frontend setup
- [x] Logging and configuration

### 🔄 Phase 2: Control Daemon Core (IN PROGRESS)
- [ ] SQLAlchemy ORM models
- [ ] Event loop architecture
- [ ] State management system
- [ ] Configuration loader

### Phase 3: Hardware Integration
- [ ] LabJack U3-HV integration
- [ ] Input state machines
- [ ] OLA client integration
- [ ] DMX output streaming

### Phase 4: Lighting Control Logic
- [ ] Tunable white mixing algorithms
- [ ] Circadian rhythm engine
- [ ] Scene management
- [ ] Group resolution

### Phase 5: HTTP API Layer
- [ ] CRUD endpoints
- [ ] Control endpoints
- [ ] WebSocket/SSE events
- [ ] API documentation

### Phase 6: Frontend Backend Integration
- [ ] API client services
- [ ] State management
- [ ] Real-time updates
- [ ] Data fetching

### Phase 7: User Interface
- [ ] Control components
- [ ] Scene management UI
- [ ] Circadian visualization
- [ ] Settings pages

### Phase 8: Testing & Deployment
- [ ] Unit tests
- [ ] Integration tests
- [ ] Performance optimization
- [ ] Deployment automation

## Documentation

- [Daemon README](daemon/README.md) - Python daemon documentation
- [Frontend README](frontend/README.md) - Frontend documentation
- [Database README](database/README.md) - Database schema and migrations
- [Specifications](specs/) - Original project specifications

## License

MIT License - See LICENSE file for details

## Contributing

This is a professional lighting control system. Contributions should maintain:
- Code quality and type safety
- Comprehensive testing
- Clear documentation
- Security best practices

## Support

For issues, questions, or contributions:
- Create an issue on GitHub
- Review the documentation in `/docs`
- Check the specifications in `/specs`

---

**Status**: Phase 1 Complete ✅ | Ready for Phase 2 Development
