# Tau Lighting Control System - Development Plan

**Last Updated**: December 12, 2024
**Current Phase**: Phase 1 Complete ✅ | Ready for Phase 2

---

## Project Overview

Tau is a professional-grade smart lighting control system that provides intelligent, circadian-aware lighting control for residential and commercial environments. It runs on a Linux-based NUC and interfaces with physical hardware while providing a modern web interface.

### Core Features
- Physical switch/dimmer control via LabJack U3-HV
- DMX512 lighting output via OLA
- Circadian lighting programs
- Scene management
- Group control with multi-level nesting
- Real-time web interface
- State persistence across reboots

### Technology Stack
- **Backend**: Python 3.11+, FastAPI, SQLAlchemy, PostgreSQL
- **Frontend**: Next.js 14+, TypeScript, Tailwind CSS
- **Infrastructure**: Docker, systemd

---

## Development Phases

### ✅ Phase 1: Foundation & Infrastructure (COMPLETED)

**Duration**: Weeks 1-2
**Status**: ✅ Complete

#### Objectives
Set up core infrastructure and database foundation.

#### Completed Deliverables
- [x] Project directory structure
- [x] Docker Compose configuration (database, daemon, frontend)
- [x] PostgreSQL database schema (12 tables, 1 view)
- [x] Alembic migration system
- [x] Python daemon foundation with FastAPI
- [x] SQLAlchemy async database connection
- [x] Structured logging with JSON output
- [x] Environment configuration management
- [x] Next.js 14+ frontend with TypeScript
- [x] Tailwind CSS styling
- [x] TypeScript type definitions
- [x] systemd service files
- [x] Health check endpoints

#### Files Created
```
├── database/
│   ├── init.sql (189 lines)
│   ├── README.md
│   └── migrations/
├── daemon/
│   ├── src/tau/
│   │   ├── main.py (118 lines)
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── logging_config.py
│   │   └── api/__init__.py
│   ├── alembic/
│   │   └── versions/20250101_0000_initial_schema.py (400+ lines)
│   ├── requirements.txt
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx
│   │   │   └── globals.css
│   │   └── types/tau.ts (200+ lines)
│   ├── package.json
│   ├── tsconfig.json
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

#### Test Results
- ✅ All 12 database tables created successfully
- ✅ Default circadian profiles inserted
- ✅ Daemon connecting to database
- ✅ FastAPI health endpoint responding
- ✅ Frontend serving pages on port 3000
- ✅ API documentation available at /docs

---

### 🔄 Phase 2: Control Daemon Core

**Duration**: Weeks 3-4
**Status**: 🔜 Ready to Start

#### Objectives
Build the core daemon functionality with ORM models and state management.

#### Tasks

##### 1. SQLAlchemy ORM Models
Create ORM models for all database tables:

**Files to Create**:
- `daemon/src/tau/models/__init__.py`
- `daemon/src/tau/models/fixtures.py` - FixtureModel, Fixture
- `daemon/src/tau/models/switches.py` - SwitchModel, Switch
- `daemon/src/tau/models/groups.py` - Group, GroupFixture, GroupHierarchy
- `daemon/src/tau/models/circadian.py` - CircadianProfile
- `daemon/src/tau/models/scenes.py` - Scene, SceneValue
- `daemon/src/tau/models/state.py` - FixtureState, GroupState

**Key Features**:
- Async-compatible models
- Proper relationships (ForeignKey, ManyToMany)
- Type hints for all fields
- Validation using SQLAlchemy CheckConstraint
- JSON field handling for circadian curve_points

##### 2. Event Loop Architecture
Build the main control loop:

**Files to Create**:
- `daemon/src/tau/control/__init__.py`
- `daemon/src/tau/control/event_loop.py` - Main control loop
- `daemon/src/tau/control/scheduler.py` - Task scheduling

**Key Features**:
- Async event loop running at 30 Hz
- Separate task queues for different priorities
- Graceful shutdown handling
- Error recovery and retry logic

##### 3. State Management System
Implement state tracking and persistence:

**Files to Create**:
- `daemon/src/tau/control/state_manager.py` - State management
- `daemon/src/tau/control/persistence.py` - Database persistence

**Key Features**:
- In-memory state cache for performance
- Periodic persistence to database (every 5 seconds)
- State recovery on daemon startup
- Atomic state updates
- Conflict resolution

##### 4. Configuration Loader
Load and validate configuration:

**Files to Create**:
- `daemon/src/tau/config_loader.py` - Configuration loading
- `daemon/config/default_config.yaml` - Default configuration

**Key Features**:
- Load fixture configurations from database
- Validate DMX channel assignments
- Detect channel collisions
- Load switch assignments
- Group membership resolution

#### Deliverables
- [ ] Complete ORM models with tests
- [ ] Working event loop with 30 Hz timing
- [ ] State management with persistence
- [ ] Configuration loader with validation
- [ ] Unit tests for all components (>80% coverage)

#### Success Criteria
- All ORM models query database successfully
- Event loop maintains consistent timing
- State persists and recovers correctly
- Configuration loads without errors
- No DMX channel collisions detected

---

### Phase 3: Hardware Integration

**Duration**: Weeks 5-6
**Status**: 📋 Planned

#### Objectives
Integrate with LabJack U3-HV for input and OLA for DMX output.

#### Tasks

##### 1. LabJack U3-HV Integration
**Files to Create**:
- `daemon/src/tau/hardware/__init__.py`
- `daemon/src/tau/hardware/labjack.py` - LabJack interface
- `daemon/src/tau/hardware/labjack_mock.py` - Mock for testing

**Key Features**:
- Async digital/analog pin reading
- Debouncing logic
- Pin state change detection
- Error handling and reconnection
- Mock implementation for development

##### 2. Input State Machines
**Files to Create**:
- `daemon/src/tau/hardware/input_handler.py` - Input processing
- `daemon/src/tau/hardware/state_machines.py` - Button state machines

**Key Features**:
- Tap detection
- Hold detection (>500ms)
- Double-tap detection
- Rotary encoder support
- Input event queue

##### 3. OLA Client Integration
**Files to Create**:
- `daemon/src/tau/hardware/ola_client.py` - OLA interface
- `daemon/src/tau/hardware/ola_mock.py` - Mock for testing

**Key Features**:
- DMX universe output at 44 Hz
- 512-channel support
- DMX packet construction
- Connection management
- Mock implementation

##### 4. Hardware Health Monitoring
**Files to Create**:
- `daemon/src/tau/hardware/health_monitor.py`

**Key Features**:
- Device connectivity checks
- Automatic reconnection
- Health status reporting
- Alerting on failures

#### Deliverables
- [ ] LabJack input reading
- [ ] Input state machines working
- [ ] OLA DMX output streaming
- [ ] Hardware health monitoring
- [ ] Mock implementations for testing

#### Success Criteria
- Physical switches trigger events
- DMX output updates at 44 Hz
- System recovers from hardware disconnects
- Mock mode works without hardware

---

### Phase 4: Lighting Control Logic

**Duration**: Weeks 7-8
**Status**: 📋 Planned

#### Objectives
Implement core lighting algorithms and circadian engine.

#### Tasks

##### 1. Color Temperature Mixing
**Files to Create**:
- `daemon/src/tau/lighting/__init__.py`
- `daemon/src/tau/lighting/color_mixing.py`
- `daemon/src/tau/lighting/curves.py`

**Key Features**:
- Linear color mixing
- Perceptual color mixing
- Logarithmic dimming curves
- CCT to warm/cool channel conversion
- Gamma correction

##### 2. Circadian Rhythm Engine
**Files to Create**:
- `daemon/src/tau/lighting/circadian.py`
- `daemon/src/tau/lighting/interpolation.py`

**Key Features**:
- Time-based curve interpolation
- Linear interpolation
- Cosine interpolation
- Step interpolation
- Automatic brightness/CCT calculation

##### 3. Scene Management
**Files to Create**:
- `daemon/src/tau/lighting/scene_manager.py`

**Key Features**:
- Scene activation with transitions
- Scene recall
- Scene saving
- Fade duration control

##### 4. Group Resolution
**Files to Create**:
- `daemon/src/tau/lighting/group_resolver.py`

**Key Features**:
- Recursive group membership
- 4-level nesting support
- Fixture aggregation
- Group state calculation

#### Deliverables
- [ ] Color mixing algorithms
- [ ] Circadian engine working
- [ ] Scene activation and recall
- [ ] Group hierarchy resolution
- [ ] Comprehensive lighting tests

#### Success Criteria
- CCT values produce correct channel outputs
- Circadian curves follow time-based profiles
- Scenes activate with smooth transitions
- Nested groups resolve correctly

---

### Phase 5: HTTP API Layer

**Duration**: Weeks 9-10
**Status**: 📋 Planned

#### Objectives
Build complete REST API for all CRUD operations and control.

#### Tasks

##### 1. CRUD Endpoints
**Files to Create**:
- `daemon/src/tau/api/routes/__init__.py`
- `daemon/src/tau/api/routes/fixtures.py`
- `daemon/src/tau/api/routes/groups.py`
- `daemon/src/tau/api/routes/scenes.py`
- `daemon/src/tau/api/routes/switches.py`
- `daemon/src/tau/api/routes/circadian.py`

**Endpoints**:
```
GET    /api/fixtures           - List all fixtures
GET    /api/fixtures/{id}      - Get fixture details
POST   /api/fixtures           - Create fixture
PUT    /api/fixtures/{id}      - Update fixture
DELETE /api/fixtures/{id}      - Delete fixture

GET    /api/groups             - List all groups
GET    /api/groups/{id}        - Get group details
POST   /api/groups             - Create group
PUT    /api/groups/{id}        - Update group
DELETE /api/groups/{id}        - Delete group

GET    /api/scenes             - List all scenes
GET    /api/scenes/{id}        - Get scene details
POST   /api/scenes             - Create scene
PUT    /api/scenes/{id}        - Update scene
DELETE /api/scenes/{id}        - Delete scene
POST   /api/scenes/{id}/activate - Activate scene

GET    /api/circadian          - List profiles
GET    /api/circadian/{id}     - Get profile
POST   /api/circadian          - Create profile
PUT    /api/circadian/{id}     - Update profile
DELETE /api/circadian/{id}     - Delete profile
```

##### 2. Control Endpoints
**Files to Create**:
- `daemon/src/tau/api/routes/control.py`

**Endpoints**:
```
POST   /api/control/fixture/{id}  - Control fixture
POST   /api/control/group/{id}    - Control group
POST   /api/control/scene/{id}    - Activate scene
```

##### 3. Real-time Events (WebSocket/SSE)
**Files to Create**:
- `daemon/src/tau/api/websocket.py`
- `daemon/src/tau/api/events.py`

**Events**:
- `fixture_state_changed` - Fixture state update
- `group_state_changed` - Group state update
- `scene_activated` - Scene activation
- `hardware_status` - Hardware status change
- `error` - Error occurred

##### 4. API Validation and Documentation
**Features**:
- Pydantic models for request/response
- OpenAPI/Swagger documentation
- Request validation
- Error handling
- Rate limiting

#### Deliverables
- [ ] All CRUD endpoints implemented
- [ ] Control endpoints working
- [ ] WebSocket/SSE event streaming
- [ ] Complete API documentation
- [ ] API integration tests

#### Success Criteria
- All endpoints return correct responses
- Real-time updates work via WebSocket
- API documentation is complete
- Input validation prevents errors

---

### Phase 6: Frontend Backend Integration

**Duration**: Weeks 11-12
**Status**: 📋 Planned

#### Objectives
Connect frontend to backend API and implement state management.

#### Tasks

##### 1. API Client Services
**Files to Create**:
- `frontend/src/lib/api.ts` - Base API client
- `frontend/src/lib/fixtures.ts` - Fixture API
- `frontend/src/lib/groups.ts` - Group API
- `frontend/src/lib/scenes.ts` - Scene API
- `frontend/src/lib/circadian.ts` - Circadian API

**Features**:
- Axios-based HTTP client
- Error handling
- Request/response interceptors
- Type-safe API calls

##### 2. State Management
**Files to Create**:
- `frontend/src/stores/useFixtureStore.ts`
- `frontend/src/stores/useGroupStore.ts`
- `frontend/src/stores/useSceneStore.ts`
- `frontend/src/stores/useUIStore.ts`

**Features**:
- Zustand stores for global state
- Optimistic updates
- State synchronization
- Persistence to localStorage

##### 3. Real-time Updates
**Files to Create**:
- `frontend/src/lib/websocket.ts`
- `frontend/src/hooks/useWebSocket.ts`

**Features**:
- WebSocket connection management
- Automatic reconnection
- Event subscription
- Type-safe event handlers

##### 4. Data Fetching
**Files to Create**:
- `frontend/src/hooks/useFixtures.ts`
- `frontend/src/hooks/useGroups.ts`
- `frontend/src/hooks/useScenes.ts`

**Features**:
- React Query integration
- Caching and invalidation
- Loading and error states
- Pagination support

#### Deliverables
- [ ] API client services
- [ ] State management with Zustand
- [ ] WebSocket integration
- [ ] React hooks for data fetching
- [ ] Integration tests

#### Success Criteria
- API calls work from frontend
- State updates in real-time
- WebSocket reconnects automatically
- Optimistic UI updates work

---

### Phase 7: User Interface

**Duration**: Weeks 13-14
**Status**: 📋 Planned

#### Objectives
Build complete user interface with all control features.

#### Tasks

##### 1. Room/Group Control
**Files to Create**:
- `frontend/src/components/rooms/RoomList.tsx`
- `frontend/src/components/rooms/RoomCard.tsx`
- `frontend/src/components/groups/GroupControl.tsx`
- `frontend/src/app/rooms/page.tsx`

**Features**:
- Room grid view
- Group hierarchy display
- Brightness sliders
- CCT sliders
- On/off toggles

##### 2. Fixture Control
**Files to Create**:
- `frontend/src/components/fixtures/FixtureList.tsx`
- `frontend/src/components/fixtures/FixtureControl.tsx`
- `frontend/src/components/fixtures/FixtureSettings.tsx`

**Features**:
- Fixture list with search
- Individual fixture control
- Fixture configuration
- DMX channel display

##### 3. Scene Management
**Files to Create**:
- `frontend/src/components/scenes/SceneList.tsx`
- `frontend/src/components/scenes/SceneEditor.tsx`
- `frontend/src/app/scenes/page.tsx`

**Features**:
- Scene library grid
- Scene activation buttons
- Scene creation wizard
- Scene editing interface

##### 4. Circadian Schedule
**Files to Create**:
- `frontend/src/components/circadian/ProfileChart.tsx`
- `frontend/src/components/circadian/ProfileEditor.tsx`
- `frontend/src/app/schedule/page.tsx`

**Features**:
- Curve visualization with Recharts
- Time-point editor
- Profile assignment
- Preview current values

##### 5. Settings
**Files to Create**:
- `frontend/src/components/settings/FixtureConfig.tsx`
- `frontend/src/components/settings/SwitchConfig.tsx`
- `frontend/src/app/settings/page.tsx`

**Features**:
- Fixture configuration
- Switch mapping
- System settings
- Hardware status

#### Deliverables
- [ ] Room control interface
- [ ] Scene management UI
- [ ] Circadian schedule editor
- [ ] Settings pages
- [ ] Responsive mobile design

#### Success Criteria
- All controls are responsive
- Real-time updates reflect immediately
- UI works on mobile/tablet/desktop
- Smooth animations and transitions

---

### Phase 8: Testing & Deployment

**Duration**: Weeks 15-16
**Status**: 📋 Planned

#### Objectives
Complete testing, optimization, and production deployment.

#### Tasks

##### 1. Unit Tests
**Files to Create**:
- `daemon/tests/test_models.py`
- `daemon/tests/test_lighting.py`
- `daemon/tests/test_hardware.py`
- `daemon/tests/test_api.py`

**Coverage Goals**:
- Models: >90%
- Lighting algorithms: >95%
- API endpoints: >85%
- Overall: >80%

##### 2. Integration Tests
**Files to Create**:
- `daemon/tests/integration/test_full_flow.py`
- `daemon/tests/integration/test_api_integration.py`

**Tests**:
- End-to-end fixture control
- Scene activation flows
- Circadian automation
- State persistence

##### 3. Frontend Tests
**Files to Create**:
- `frontend/src/__tests__/components/*.test.tsx`
- `frontend/src/__tests__/hooks/*.test.ts`

**Tests**:
- Component rendering
- User interactions
- API integration
- State management

##### 4. Performance Optimization
**Tasks**:
- [ ] Optimize database queries
- [ ] Add indexes where needed
- [ ] Optimize API response times
- [ ] Frontend bundle optimization
- [ ] Lazy loading components

##### 5. Production Deployment
**Files to Create**:
- `scripts/deploy.sh` - Deployment script
- `scripts/backup.sh` - Backup script
- `docs/DEPLOYMENT.md` - Deployment guide

**Tasks**:
- [ ] Production Docker images
- [ ] Systemd service setup
- [ ] Nginx configuration
- [ ] SSL certificates
- [ ] Monitoring setup

#### Deliverables
- [ ] Complete test suite
- [ ] Performance optimizations
- [ ] Deployment scripts
- [ ] Production documentation
- [ ] Backup procedures

#### Success Criteria
- >80% test coverage
- <100ms API response times
- <2s frontend load time
- Successful production deployment
- Automated backups working

---

## Quick Reference

### Current Status: Phase 1 Complete ✅

**What's Working**:
- ✅ Database with 12 tables
- ✅ Python daemon with FastAPI
- ✅ Next.js frontend
- ✅ Docker Compose orchestration
- ✅ Health check endpoints

**Next Steps**: Begin Phase 2
1. Create SQLAlchemy ORM models
2. Build event loop architecture
3. Implement state management
4. Add configuration loading

### Development Commands

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f [daemon|frontend|database]

# Restart after code changes
docker-compose restart daemon

# Run tests
docker exec tau-daemon pytest

# Database migrations
docker exec tau-daemon alembic upgrade head

# Frontend development
cd frontend && npm run dev
```

### Useful URLs
- Frontend: http://localhost:3000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Database: localhost:5432

---

## Notes

### Architecture Decisions
- **Async throughout**: Python daemon uses asyncio, SQLAlchemy async, FastAPI async
- **Mock hardware**: Development mode with mock LabJack/OLA interfaces
- **Type safety**: TypeScript frontend, Python type hints, Pydantic models
- **Structured logging**: JSON logs for production parsing
- **State persistence**: 5-second interval for balance of performance and reliability

### Performance Targets
- Control loop: 30 Hz
- DMX output: 44 Hz
- API response: <100ms
- Frontend load: <2s
- State persistence: Every 5 seconds

### Security Considerations
- Database user permissions
- API rate limiting (Phase 5)
- Input validation throughout
- No authentication in v1.0 (local network only)

---

**Document Version**: 1.0
**Last Updated**: December 12, 2024
**Maintained By**: Development Team
