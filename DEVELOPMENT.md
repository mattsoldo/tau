# Tau Lighting Control - Development Guide

This guide covers running Tau in development mode for debugging and adding features.

## Table of Contents

1. [Development vs Production](#development-vs-production)
2. [Quick Start](#quick-start)
3. [Running Components Separately](#running-components-separately)
4. [Development on Mac/Linux](#development-on-maclinux)
5. [Development on Raspberry Pi](#development-on-raspberry-pi)
6. [Hot Reload](#hot-reload)
7. [Debugging](#debugging)
8. [Common Tasks](#common-tasks)

---

## Development vs Production

### Development Mode
- **Frontend**: Next.js dev server on port 3000 with hot reload
- **Backend**: Python daemon on port 8000 with auto-reload
- **Features**: Hot reload, detailed logging, mock hardware support
- **Best for**: Adding features, debugging, testing

### Production Mode
- **Frontend**: Static files served by nginx on port 80
- **Backend**: Python daemon on port 8000
- **Features**: Optimized performance, real hardware support
- **Best for**: Actual lighting control, deployment

---

## Quick Start

### Option 1: Automated Script (Mac/Linux)

```bash
# From project root
./start_dev.sh
```

This starts:
- Backend daemon at `http://localhost:8000`
- Frontend at `http://localhost:3000`
- API docs at `http://localhost:8000/docs`

Press `Ctrl+C` to stop all servers.

### Option 2: Manual Start

See [Running Components Separately](#running-components-separately) below.

---

## Running Components Separately

### Backend Daemon

```bash
cd daemon

# Set up environment
export PYTHONPATH=$(pwd)/src
export DATABASE_URL="postgresql://tau_daemon:tau_password@localhost:5432/tau_lighting"
export LABJACK_MOCK=true  # Use mock hardware
export OLA_MOCK=true
export LOG_LEVEL=INFO

# Start daemon
.venv/bin/python -m tau.main
```

The daemon will start on `http://localhost:8000`.

**Environment Variables:**
- `DATABASE_URL` - PostgreSQL connection string
- `LABJACK_MOCK` - Use mock LabJack (true) or real hardware (false)
- `OLA_MOCK` - Use mock OLA/DMX (true) or real hardware (false)
- `LOG_LEVEL` - DEBUG, INFO, WARNING, ERROR
- `DAEMON_PORT` - Port for API server (default: 8000)
- `CONTROL_LOOP_HZ` - Control loop frequency (default: 30)

### Frontend Dev Server

```bash
cd frontend

# Start dev server
npm run dev
```

The frontend will start on `http://localhost:3000` with hot reload enabled.

**What happens:**
- Changes to React components reload instantly
- API requests are proxied to `http://localhost:8000`
- No need to rebuild after code changes

---

## Development on Mac/Linux

### Prerequisites

```bash
# Install Python 3.11+
brew install python@3.11  # macOS
# or
sudo apt-get install python3.11  # Linux

# Install Node.js 18+
brew install node  # macOS
# or
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs  # Linux

# Install PostgreSQL
brew install postgresql@15  # macOS
# or
sudo apt-get install postgresql-15  # Linux
```

### Setup

```bash
# Clone repository
git clone https://github.com/mattsoldo/tau.git
cd tau

# Backend setup
cd daemon
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd ..

# Frontend setup
cd frontend
npm install
cd ..

# Database setup
createdb tau_lighting
cd daemon
.venv/bin/alembic upgrade head
cd ..
```

### Start Development

```bash
./start_dev.sh
```

---

## Development on Raspberry Pi

### Using Real Hardware

On the Pi, you can develop with actual LabJack and DMX hardware:

```bash
cd /opt/tau-daemon

# Stop production services
sudo systemctl stop tau-daemon
sudo systemctl stop nginx

# Set up environment for real hardware
cd daemon
export PYTHONPATH=$(pwd)/src
export DATABASE_URL="postgresql://tau_daemon:tau_password@localhost:5432/tau_lighting"
export LABJACK_MOCK=false  # Use real LabJack
export OLA_MOCK=false      # Use real OLA/DMX
export LOG_LEVEL=DEBUG     # Verbose logging

# Start daemon
.venv/bin/python -m tau.main
```

In another terminal:

```bash
cd /opt/tau-daemon/frontend
npm run dev
```

Access at `http://192.168.1.199:3000`

### Switching Back to Production

```bash
# Rebuild frontend
cd /opt/tau-daemon/frontend
npm run build

# Restart services
sudo systemctl start tau-daemon
sudo systemctl start nginx
```

---

## Hot Reload

### Frontend Hot Reload

The Next.js dev server automatically reloads when you save files:

- **React components** (`*.tsx`) - Instant reload
- **Styles** (`*.css`) - Instant update
- **API client** (`utils/api.ts`) - Requires page refresh
- **Next.js config** - Requires restart

### Backend Auto-Reload

For backend changes, you can use `watchdog` for auto-reload:

```bash
cd daemon

# Install watchdog
.venv/bin/pip install watchdog

# Run with auto-reload
.venv/bin/watchmedo auto-restart --directory=./src --pattern=*.py --recursive -- python -m tau.main
```

Or manually restart the daemon after making changes.

---

## Debugging

### Backend Debugging

**VS Code Launch Config** (`.vscode/launch.json`):

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Python: Tau Daemon",
      "type": "python",
      "request": "launch",
      "module": "tau.main",
      "cwd": "${workspaceFolder}/daemon",
      "env": {
        "PYTHONPATH": "${workspaceFolder}/daemon/src",
        "DATABASE_URL": "postgresql://tau_daemon:tau_password@localhost:5432/tau_lighting",
        "LABJACK_MOCK": "true",
        "OLA_MOCK": "true",
        "LOG_LEVEL": "DEBUG"
      }
    }
  ]
}
```

**Breakpoints:**
- Set breakpoints in `.py` files
- Use VS Code debugger or `import pdb; pdb.set_trace()`

### Frontend Debugging

**Browser DevTools:**
1. Open Chrome DevTools (`Cmd+Option+I`)
2. Sources tab for breakpoints
3. Console tab for logs
4. Network tab for API requests

**React DevTools:**
```bash
# Install React DevTools extension in Chrome
```

### Logging

**Backend:**
```python
import structlog
logger = structlog.get_logger(__name__)

logger.debug("debug message", key="value")
logger.info("info message", count=42)
logger.warning("warning message")
logger.error("error message", error=str(e))
```

**Frontend:**
```typescript
console.log("Frontend log", { data });
console.error("Error:", error);
```

---

## Common Tasks

### Create Database Migration

```bash
cd daemon
.venv/bin/alembic revision --autogenerate -m "Description of changes"
.venv/bin/alembic upgrade head
```

### Run Tests

```bash
# Backend tests
cd daemon
.venv/bin/pytest

# Frontend tests (if configured)
cd frontend
npm test
```

### Lint Code

```bash
# Backend
cd daemon
.venv/bin/ruff check src/

# Frontend
cd frontend
npm run lint
```

### Format Code

```bash
# Backend
cd daemon
.venv/bin/ruff format src/

# Frontend
cd frontend
npm run format  # if configured
```

### View Logs

**Development:**
```bash
# Backend logs are in terminal where daemon is running
# Frontend logs are in browser console
```

**Production:**
```bash
# Backend daemon logs
sudo journalctl -u tau-daemon -f

# Nginx logs
sudo tail -f /var/log/nginx/tau-error.log
sudo tail -f /var/log/nginx/tau-access.log
```

### Reset Database

```bash
cd daemon

# Drop all tables
.venv/bin/alembic downgrade base

# Recreate tables
.venv/bin/alembic upgrade head

# Load example config (optional)
.venv/bin/python scripts/load_example_config.py
```

### Update Dependencies

```bash
# Backend
cd daemon
.venv/bin/pip install --upgrade -r requirements.txt

# Frontend
cd frontend
npm update
```

---

## Tips & Tricks

### Speed Up Frontend Builds

```bash
# Use turbo for faster rebuilds
npm install -g turbo
turbo dev
```

### Monitor Control Loop Performance

```bash
# Check event loop stats
curl http://localhost:8000/status | jq '.event_loop'
```

### Test API Endpoints

```bash
# Using curl
curl http://localhost:8000/api/fixtures/ | jq

# Using httpie (more readable)
brew install httpie
http localhost:8000/api/fixtures/
```

### Quick Database Queries

```bash
# Connect to database
psql postgresql://tau_daemon:tau_password@localhost:5432/tau_lighting

# Useful queries
SELECT * FROM fixtures;
SELECT * FROM fixture_state;
SELECT * FROM groups;
```

---

## Troubleshooting

### Frontend Can't Reach Backend

**Symptom:** API errors in browser console

**Solution:**
1. Verify backend is running: `curl http://localhost:8000/health`
2. Check Next.js rewrites are working: view browser Network tab
3. Ensure `next.config.js` has rewrites for dev mode

### Database Connection Errors

**Symptom:** Backend fails to start with database errors

**Solution:**
1. Check PostgreSQL is running: `pg_isalive`
2. Verify credentials: `psql $DATABASE_URL`
3. Run migrations: `alembic upgrade head`

### Port Already in Use

**Symptom:** "Address already in use" error

**Solution:**
```bash
# Find process using port 8000
lsof -i :8000

# Kill the process
kill -9 <PID>

# Or use different port
export DAEMON_PORT=8001
```

### Hardware Not Detected

**Symptom:** LabJack or OLA errors

**Solution:**
```bash
# Use mock hardware for development
export LABJACK_MOCK=true
export OLA_MOCK=true

# Or install hardware drivers
# See deployment/DEPLOYMENT.md for hardware setup
```

---

## Next Steps

- Read [daemon/README.md](daemon/README.md) for backend architecture
- Read [frontend/README.md](frontend/README.md) for frontend structure
- See [specs/prd.md](specs/prd.md) for product requirements
- See [specs/daemon_spec.md](specs/daemon_spec.md) for technical spec

---

## Support

For questions or issues:
- GitHub Issues: https://github.com/mattsoldo/tau/issues
- Check logs first (see "View Logs" section above)
- Include error messages and environment info when reporting issues
