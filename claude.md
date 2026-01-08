# Tau Lighting Control System - Claude Development Guide

This document provides guidance for working effectively on the Tau lighting control system. It captures best practices, conventions, and patterns observed in the codebase.

---

## Project Overview

Tau is a professional-grade smart lighting control system that runs on a **Raspberry Pi** (accessible at `soldo@tau` via SSH). It provides intelligent, circadian-aware lighting control through:

- **Hardware**: LabJack U3-HV for physical switch inputs, USB-to-DMX for lighting output
- **Backend**: Python FastAPI daemon managing state, hardware, and control logic
- **Frontend**: Next.js/TypeScript web interface
- **Database**: PostgreSQL for persistent configuration and state

The system operates in two modes:
- **Development**: Daemon runs directly with environment variables for rapid iteration
- **Production**: Systemd service with proper deployment and process management

---

## Development Environment

### Raspberry Pi Access

The production hardware runs on a Raspberry Pi accessible via:
```bash
ssh soldo@tau
```

**Important**: Always use `soldo@tau` for SSH access, not `tau@tau`.

### Development vs Production Mode

**Development Mode** (preferred for rapid iteration):
```bash
# On the Raspberry Pi
ssh soldo@tau
cd ~/code/tau

# Stop production service
sudo systemctl stop tau-daemon

# Run daemon in dev mode
cd daemon
export DATABASE_URL="postgresql://tau_daemon:tau_password@localhost:5432/tau_lighting"
export LABJACK_MOCK=true  # Or false for real hardware
export OLA_MOCK=true      # Or false for real DMX
export LOG_LEVEL=INFO
python -m tau.main

# Run frontend locally (on your machine)
cd frontend
npm run dev  # Runs on localhost:3001 (or 3000)
```

**Production Mode**:
```bash
# On the Raspberry Pi
sudo systemctl start tau-daemon
sudo systemctl status tau-daemon

# Frontend served by nginx at http://tau.local
```

### Why Deploy to Pi

> "I have all the live equipment (switches and lights) connected to the pi, so localhost has limited value for testing."

Always deploy backend and frontend changes to the Pi for testing with real hardware.

---

## Architecture Overview

```
tau/
├── daemon/                      # Python control daemon
│   ├── src/tau/
│   │   ├── main.py             # Application entry point
│   │   ├── api/routes/         # FastAPI REST endpoints
│   │   ├── control/            # State management, event loop
│   │   ├── hardware/           # LabJack, OLA drivers
│   │   ├── logic/              # Lighting algorithms, switches
│   │   ├── models/             # SQLAlchemy ORM models
│   │   └── services/           # Business logic services
│   ├── alembic/                # Database migrations
│   └── tests/                  # Pytest test suite
│
├── frontend/                    # Next.js application
│   ├── src/
│   │   ├── app/                # Next.js App Router pages
│   │   ├── components/         # React components
│   │   └── types/              # TypeScript definitions
│   └── public/                 # Static assets
│
├── specs/                       # Living documentation
│   ├── prd.md                  # Product requirements
│   ├── daemon_spec.md          # Daemon specification
│   ├── logic.md                # Control logic spec
│   └── schema.sql              # Database schema documentation
│
└── database/                    # Database setup
    └── README.md
```

---

## Backend Best Practices (Python/FastAPI)

### 1. Async Session Management Pattern

**Critical Pattern**: Always use async generators properly without manual session closing.

```python
# ✅ CORRECT: Async generator pattern
async def get_system_setting_typed(
    key: str,
    value_type: str = "str",
    default_value = None,
    session: Optional[AsyncSession] = None
):
    if session is None:
        # Create our own session via async generator
        async for sess in get_session():
            try:
                result = await sess.execute(
                    select(SystemSetting).where(SystemSetting.key == key)
                )
                setting = result.scalar_one_or_none()
                if setting is None:
                    return default_value
                return setting.get_typed_value()
            except Exception as e:
                logger.error("error", key=key, error=str(e))
                return default_value
        # Session automatically closed by generator
    else:
        # Use provided session (caller manages lifecycle)
        result = await session.execute(...)
        return result

# ❌ WRONG: Manual session closing causes IllegalStateChangeError
async for sess in get_session():
    session = sess
    break
# ... later ...
await session.close()  # DON'T DO THIS!
```

### 2. Database Context Managers

Use context managers for session management in API endpoints:

```python
from tau.database import get_db_session

@router.get("/settings")
async def get_all_system_settings():
    """Get all system settings"""
    async with get_db_session() as session:
        try:
            result = await session.execute(select(SystemSetting))
            settings = result.scalars().all()
            return [SystemSettingResponse.model_validate(s) for s in settings]
        except Exception as e:
            logger.error("get_system_settings_error", error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed: {str(e)}")
```

### 3. Structured Logging

Use structlog with structured context:

```python
import structlog

logger = structlog.get_logger(__name__)

# Always use key-value pairs
logger.info(
    "system_setting_updated",
    key=key,
    old_value=old_val,
    new_value=new_val
)

logger.error(
    "hardware_connection_failed",
    hardware="labjack",
    error=str(e),
    retry_count=retries
)
```

### 4. Type Safety with Pydantic

Define request/response models with Pydantic:

```python
from pydantic import BaseModel, Field

class SystemSettingResponse(BaseModel):
    """System setting response"""
    id: int = Field(..., description="Setting ID")
    key: str = Field(..., description="Setting key")
    value: str = Field(..., description="Setting value (as string)")
    description: Optional[str] = Field(None, description="Human-readable description")
    value_type: str = Field(..., description="Value type (int, float, bool, str)")

    class Config:
        from_attributes = True  # For SQLAlchemy model validation
```

### 5. SQLAlchemy Models

Use SQLAlchemy 2.0 style with Mapped annotations:

```python
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String, Text

class SystemSetting(Base):
    """System configuration storage"""
    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    value_type: Mapped[str] = mapped_column(String(20), nullable=False, server_default="str")

    def get_typed_value(self):
        """Convert stored string value to proper type"""
        if self.value_type == "int":
            return int(self.value)
        elif self.value_type == "float":
            return float(self.value)
        elif self.value_type == "bool":
            return self.value.lower() in ("true", "1", "yes")
        return self.value
```

### 6. Hardware Abstraction

Mock hardware for development:

```python
# Environment-based hardware selection
LABJACK_MOCK = os.getenv("LABJACK_MOCK", "false").lower() == "true"
OLA_MOCK = os.getenv("OLA_MOCK", "false").lower() == "true"

# Graceful fallback if hardware unavailable
if LABJACK_MOCK or not labjack_available:
    from tau.hardware.labjack_mock import MockLabJack
    self.labjack = MockLabJack()
else:
    from tau.hardware.labjack_driver import LabJackDriver
    self.labjack = LabJackDriver()
```

---

## Frontend Best Practices (Next.js/TypeScript)

### 1. API-First Design

Always define clear API contracts and fetch data consistently:

```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL || '';

// Centralized API calls
async function fetchSettings(): Promise<SystemSetting[]> {
  const res = await fetch(`${API_URL}/api/config/settings`);
  if (!res.ok) throw new Error('Failed to fetch settings');
  return res.json();
}

// Update with error handling
async function updateSetting(key: string, value: string) {
  const res = await fetch(`${API_URL}/api/config/settings/${key}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value }),
  });
  if (!res.ok) {
    const errorData = await res.json();
    throw new Error(errorData.detail || 'Failed to update setting');
  }
  return res.json();
}
```

### 2. Inline Editing Pattern

For settings and configuration UI, use inline editing:

```typescript
const [editingKey, setEditingKey] = useState<string | null>(null);
const [editValue, setEditValue] = useState<string>('');

// Start editing
const handleEdit = (key: string, currentValue: string) => {
  setEditingKey(key);
  setEditValue(currentValue);
};

// Save changes
const handleSave = async (key: string) => {
  await updateSetting(key, editValue);
  await fetchData();  // Refresh
  setEditingKey(null);
};

// Cancel editing
const handleCancel = () => {
  setEditingKey(null);
  setEditValue('');
};

// Render
{editingKey === setting.key ? (
  <>
    <input value={editValue} onChange={(e) => setEditValue(e.target.value)} />
    <button onClick={() => handleSave(setting.key)}>Save</button>
    <button onClick={handleCancel}>Cancel</button>
  </>
) : (
  <>
    <span>{formatValue(setting.value)}</span>
    <button onClick={() => handleEdit(setting.key, setting.value)}>Edit</button>
  </>
)}
```

### 3. Type Definitions

Define comprehensive TypeScript interfaces:

```typescript
// types/tau.ts
interface SystemSetting {
  id: number;
  key: string;
  value: string;
  description: string | null;
  value_type: 'int' | 'float' | 'bool' | 'str';
}

interface LabJackStatus {
  connected: boolean;
  model?: string;
  serial_number?: string;
  read_count: number;
  write_count: number;
  error_count: number;
  digital_inputs: Record<string, boolean>;
}
```

### 4. Real-Time Polling

Use useEffect for periodic data updates:

```typescript
useEffect(() => {
  const fetchData = async () => {
    try {
      const response = await fetch(`${API_URL}/status`);
      if (!response.ok) throw new Error('Status API error');
      setStatus(await response.json());
      setError(null);
    } catch {
      setError('Connection error');
    }
  };

  fetchData();
  const interval = setInterval(fetchData, 2000);
  return () => clearInterval(interval);
}, []);
```

### 5. Design System Consistency

Follow the established dark theme with amber accents:

```typescript
// Color palette
const colors = {
  background: {
    primary: '#0a0a0b',
    secondary: '#161619',
    tertiary: '#111113',
  },
  border: {
    default: '#2a2a2f',
    hover: '#3a3a3f',
  },
  text: {
    primary: 'white',
    secondary: '#8e8e93',
    tertiary: '#636366',
  },
  accent: {
    amber: '#f59e0b',
    green: '#22c55e',
    red: '#ef4444',
  }
};

// Consistent component styling
<div className="bg-[#161619] border border-[#2a2a2f] rounded-2xl p-6">
  <h3 className="text-lg font-semibold">Title</h3>
  <p className="text-sm text-[#636366]">Description</p>
</div>
```

### 6. Loading States & Error Handling

Always handle loading and error states:

```typescript
const [loading, setLoading] = useState(true);
const [error, setError] = useState<string | null>(null);

{error && (
  <div className="px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400">
    {error}
  </div>
)}

{loading ? (
  <div className="text-center text-[#636366]">Loading...</div>
) : (
  <Content data={data} />
)}
```

---

## Database Best Practices

### 1. Migrations with Alembic

Always create migrations for schema changes:

```bash
cd daemon

# Create migration
alembic revision --autogenerate -m "Add system_settings table"

# Review the generated migration file
# Edit alembic/versions/<timestamp>_add_system_settings_table.py

# Apply migration
alembic upgrade head

# Check status
alembic current
alembic history
```

### 2. Default Data in Migrations

Include default/seed data in migrations:

```python
def upgrade() -> None:
    op.create_table(
        'system_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key')
    )

    # Insert default settings
    op.execute("""
        INSERT INTO system_settings (key, value, description, value_type)
        VALUES (
            'dim_speed_ms',
            '2000',
            'Time in milliseconds for a full 0-100% brightness transition',
            'int'
        )
    """)
```

### 3. Schema Documentation

**Important**: Update `specs/schema.sql` after every schema change to maintain living documentation.

```sql
-- specs/schema.sql
CREATE TABLE system_settings (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) UNIQUE NOT NULL,
    value TEXT NOT NULL,
    description TEXT,
    value_type VARCHAR(20) NOT NULL DEFAULT 'str'
);

-- Default data
INSERT INTO system_settings (key, value, description, value_type) VALUES
    ('dim_speed_ms', '2000', 'Dimming transition time (ms) for 0-100% change', 'int');
```

---

## Deployment to Raspberry Pi

### Standard Deployment Workflow

**Backend Changes**:
```bash
# Copy Python files
scp daemon/src/tau/models/system_settings.py soldo@tau:~/code/tau/daemon/src/tau/models/
scp daemon/src/tau/api/routes/system_config.py soldo@tau:~/code/tau/daemon/src/tau/api/routes/

# SSH in and restart daemon
ssh soldo@tau
cd ~/code/tau/daemon

# If in dev mode, just restart the process
# If in production mode:
sudo systemctl restart tau-daemon
sudo systemctl status tau-daemon
```

**Frontend Changes**:
```bash
# Copy TypeScript files
scp frontend/src/app/config/settings/page.tsx soldo@tau:~/code/tau/frontend/src/app/config/settings/

# SSH in and rebuild
ssh soldo@tau
cd ~/code/tau/frontend
npm run build

# Reload nginx
sudo systemctl reload nginx

# Or if running Next.js standalone:
# npm start
```

**Database Changes**:
```bash
# Copy migration
scp daemon/alembic/versions/20260105_1200_add_system_settings_table.py \
    soldo@tau:~/code/tau/daemon/alembic/versions/

# SSH in and run migration
ssh soldo@tau
cd ~/code/tau/daemon
alembic upgrade head
```

### Quick Deploy Script Pattern

For convenience, create deployment scripts:

```bash
#!/bin/bash
# deploy.sh

# Backend
scp -r daemon/src/tau/* soldo@tau:~/code/tau/daemon/src/tau/

# Frontend
scp -r frontend/src/* soldo@tau:~/code/tau/frontend/src/

# SSH and rebuild
ssh soldo@tau << 'EOF'
    cd ~/code/tau/daemon
    sudo systemctl restart tau-daemon

    cd ~/code/tau/frontend
    npm run build
    sudo systemctl reload nginx
EOF

echo "Deployment complete!"
```

---

## Software Update System

This section defines practices for the OTA update system. All code changes must maintain compatibility with this system.

### Versioning

We use **semantic versioning** (semver) with GitHub Releases as the update source.

- **MAJOR** (v2.0.0): Breaking changes, database schema changes requiring migration, API incompatibilities
- **MINOR** (v1.2.0): New features, backward-compatible additions
- **PATCH** (v1.2.3): Bug fixes, performance improvements, no new features

Pre-release versions use suffixes: `v2.0.0-beta.1`, `v2.0.0-rc.1`

**Never** reference git commits or branch state for versioning in user-facing code. Always use release tags.

### Release Artifacts

**CRITICAL**: Every version release requires BOTH a git tag AND a GitHub Release with downloadable assets. The auto-update system uses the GitHub Releases API, which only sees actual Releases, not bare git tags.

Every release must include:

1. **Git tag**: `git tag -a v1.x.x -m "description"` and `git push origin v1.x.x`
2. **GitHub Release**: Created via `gh release create` with assets attached
3. **Tarball asset**: `tau-v{version}.tar.gz` (created with `git archive`)
4. **Release notes** in the GitHub release body (not a separate file)

**Creating a release**:
```bash
# 1. Tag the release
git tag -a v1.1.3 -m "v1.1.3 - Description of changes"
git push origin v1.1.3

# 2. Create tarball
git archive --format=tar.gz --prefix=tau/ -o /tmp/tau-v1.1.3.tar.gz v1.1.3

# 3. Create GitHub Release with asset
gh release create v1.1.3 /tmp/tau-v1.1.3.tar.gz \
  --repo mattsoldo/tau \
  --title "v1.1.3 - Title" \
  --notes "Release notes here"
```

When modifying build scripts or CI workflows, ensure these artifacts are generated and attached to releases.

### Release Notes Format

GitHub release bodies must follow this structure for the update UI to parse correctly:

```markdown
## What's New
- Feature description (user-facing benefit)

## Bug Fixes
- Fix description

## Breaking Changes
- Description of breaking change and migration path
- Or "None" if no breaking changes

## Upgrade Notes
- Any manual steps required (or omit section if none)
```

When adding features or fixing bugs, draft release note entries in commit messages or PR descriptions.

### Database Migrations for Updates

The update system runs migrations automatically after package installation.

**Migration file naming**:
```
migrations/
  001_initial_schema.sql
  002_add_scene_table.sql
  003_dali_dt8_support.sql
```

**Migration requirements**:

1. **Migrations must be idempotent** — Safe to run multiple times
2. **Always provide down migrations** — Required for rollback support
3. **Never modify existing migrations** — Create new ones instead
4. **Test rollback** — Verify `down` migration restores previous state

```sql
-- Example: migrations/004_add_preset_colors.sql

-- migrate:up
ALTER TABLE scenes ADD COLUMN preset_colors JSON;

-- migrate:down
ALTER TABLE scenes DROP COLUMN preset_colors;
```

**Schema version tracking**: The `schema_version` table tracks applied migrations. The update system checks this during rollback to determine if database restoration is needed.

When writing migration code:
- Increment `DATABASE_SCHEMA_VERSION` constant in `config.py`
- Update the version check in `verify_installation()`

### Service Management

The lighting system runs as systemd services. The update system stops services before installation and restarts them after.

**Service names** (do not change without updating update system):
- `lighting-control.service` — Main daemon
- `lighting-web.service` — Web UI server

**Health check endpoint**: The update system verifies installation by calling `GET /api/health`. This endpoint must:
- Return HTTP 200 when services are operational
- Return the current version in the response
- Be available within 30 seconds of service start

```python
@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "version": __version__,
        "database": check_database_connection(),
        "ola": check_ola_connection()
    }
```

Do not modify the health check response structure without updating `verify_installation()` in the update system.

### Backward Compatibility

**Configuration files**: When adding new configuration options:
- Always provide defaults in code
- Never require new config keys to be present
- Use `config.get('new_key', default_value)` pattern

```python
# Correct — works with old config files
check_interval = config.get('updates', {}).get('check_interval_hours', 24)

# Wrong — breaks if key missing
check_interval = config['updates']['check_interval_hours']
```

**API endpoints**:
- New endpoints: Add freely
- Modified endpoints: Maintain backward compatibility or version the API
- Removed endpoints: Deprecate for one minor version before removal

**Database schema**:
- Adding columns: Provide defaults, make nullable, or backfill
- Removing columns: Keep for one minor version, ignore in code
- Changing types: Create new column, migrate data, drop old

### Update System Code Locations

```
src/
  update/
    __init__.py
    daemon.py          # Scheduled check daemon
    github_client.py   # GitHub API interactions
    version.py         # Version comparison, semver parsing
    backup.py          # Backup creation and restoration
    installer.py       # Package installation logic
    state.py           # State machine, database operations
    cli.py             # CLI commands (lighting-ctl update ...)

tests/
  update/
    test_version.py
    test_backup.py
    test_state_machine.py
    fixtures/
      mock_releases.json
```

When modifying update system code:
- Maintain state machine transitions in `state.py`
- Test interrupted update recovery scenarios
- Verify rollback works after your changes

### Update Error Handling

Update operations must handle failures gracefully. Follow these patterns:

**Recoverable errors** (retry):
```python
@retry(max_attempts=3, backoff=exponential)
def download_asset(url: str) -> Path:
    ...
```

**Non-recoverable errors** (rollback):
```python
def install_package(path: Path) -> None:
    try:
        run_dpkg_install(path)
    except DpkgError as e:
        raise InstallationError(f"Package installation failed: {e}")
        # State machine catches this and triggers rollback
```

**Critical errors** (manual intervention):
```python
def restore_from_backup(backup_path: Path) -> None:
    try:
        ...
    except Exception as e:
        log_critical(f"ROLLBACK FAILED: {e}")
        log_critical("Manual intervention required")
        # Do not raise — system is in inconsistent state
        # Alert mechanisms should fire here
```

### Update Testing Requirements

Before merging changes that affect the update system:

1. **Unit tests pass**: `pytest tests/update/`
2. **State machine coverage**: All transitions have tests
3. **Rollback tested**: Verify rollback works for your changes
4. **Mock API tests**: GitHub API interactions use fixtures

**Testing update flows locally**:

```bash
# Simulate update check
lighting-ctl update check --dry-run

# Test backup/restore cycle
lighting-ctl update backup --test
lighting-ctl update restore --test --version v2.1.0

# Verify package installation
lighting-ctl update apply --dry-run v2.2.0
```

### CI/CD Integration

The GitHub Actions workflow (`.github/workflows/release.yml`) handles:
- Building the Debian package
- Generating checksums
- Creating draft releases

When modifying this workflow:
- Maintain the artifact naming convention
- Ensure checksums are generated with SHA256
- Keep releases as drafts until manually published

**Required secrets**:
- `GITHUB_TOKEN` — Provided automatically
- No other secrets required for public repo releases

### Prohibited Practices

1. **Never auto-install updates** — User must explicitly trigger installation
2. **Never skip checksum verification** — Even in development
3. **Never delete all backups** — Minimum 1 must remain during operations
4. **Never modify the installation singleton** — Only update system writes to `installation` table
5. **Never hardcode versions** — Use `__version__` from package metadata
6. **Never bypass the state machine** — All update operations go through state transitions

### Adding New Update Features

When extending the update system:

1. Update this documentation
2. Add database migrations if schema changes
3. Maintain CLI and Web UI parity
4. Update the state diagram if adding states
5. Add monitoring/logging for new failure modes
6. Test on actual Raspberry Pi hardware before release

---

## Documentation Standards

### Living Documentation

**Critical**: Keep specs/ directory up to date with every feature.

From user's global .claude/CLAUDE.md:
> "Each time we finish a new feature lets edit all the relevant docs in the specs (@specs/daemon_spec.md @specs/prd.md @specs/logic.md @specs/schema.sql) so that these are living documents and reflect the current state of the system. Do this alongside git commits of features."

**Affected Files** (update as needed):
- `specs/prd.md` - Product requirements and features
- `specs/daemon_spec.md` - Daemon functionality and API
- `specs/logic.md` - Control logic and algorithms
- `specs/schema.sql` - Complete database schema with comments

### Git Commit Messages

Use descriptive commit messages with context:

```bash
# Good examples
git commit -m "Add global settings management UI and API"
git commit -m "Fix session management in system settings helper"
git commit -m "Add system settings with dim_speed configuration"

# Include co-author for AI assistance
git commit -m "Add feature X

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

---

## Common Patterns & Conventions

### 1. Configuration Settings

Store runtime-configurable values in `system_settings` table:

```python
# Load on startup
dim_speed_ms = await get_system_setting_typed(
    key="dim_speed_ms",
    value_type="int",
    default_value=2000
)
logger.info("dim_speed_loaded", dim_speed_ms=dim_speed_ms)
```

### 2. Error Recovery & Graceful Degradation

System continues operating even when hardware unavailable:

```python
# Detection with fallback
labjack_available, labjack_details = _detect_labjack_hardware()

if not labjack_available:
    logger.warning("labjack_not_detected", using_mock=True)
    # Continue with mock hardware

# Automatic reconnection
async def health_check_loop():
    while True:
        if not self.hardware_connected:
            await self.attempt_reconnect()
        await asyncio.sleep(10)
```

### 3. Value Formatting & Display

Format values appropriately for user display:

```typescript
// Format numbers with units
const formatValue = (value: string, valueType: string) => {
  if (valueType === 'int') return parseInt(value).toLocaleString();
  if (valueType === 'float') return parseFloat(value).toFixed(2);
  if (valueType === 'bool') return value === 'true' ? 'Yes' : 'No';
  return value;
};

// Add units based on key naming
{formatValue(setting.value, setting.value_type)}
{setting.value_type === 'int' && setting.key.includes('ms') && ' ms'}
{setting.value_type === 'int' && setting.key.includes('percent') && '%'}
```

### 4. State Persistence

Always persist state changes immediately:

```python
# Update model
setting.value = new_value

# Commit immediately
await session.commit()

# Refresh to get updated values
await session.refresh(setting)

# Log the change
logger.info("setting_updated", key=setting.key, value=new_value)
```

---

## Testing Guidelines

### Backend Tests

Use pytest with async support:

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_get_system_settings(client: AsyncClient):
    """Test retrieving all system settings"""
    response = await client.get("/api/config/settings")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0

@pytest.mark.asyncio
async def test_update_system_setting(client: AsyncClient):
    """Test updating a system setting"""
    response = await client.put(
        "/api/config/settings/dim_speed_ms",
        json={"value": "3000"}
    )
    assert response.status_code == 200
    assert response.json()["value"] == "3000"
```

### Frontend Testing

Focus on component behavior and integration:

```typescript
// Component tests
describe('Settings Page', () => {
  it('should display all settings', async () => {
    render(<SettingsPage />);
    await waitFor(() => {
      expect(screen.getByText('Dim Speed')).toBeInTheDocument();
    });
  });
});
```

---

## Performance Considerations

### 1. Fast Polling for Hardware

Use appropriate polling rates:

```typescript
// Fast poll for digital inputs (100ms)
useEffect(() => {
  const interval = setInterval(pollDigitalInputs, 100);
  return () => clearInterval(interval);
}, []);

// Slower poll for status (2s)
useEffect(() => {
  const interval = setInterval(fetchStatus, 2000);
  return () => clearInterval(interval);
}, []);
```

### 2. Database Query Optimization

Minimize queries and use proper indexes:

```python
# Load related data efficiently
result = await session.execute(
    select(Fixture)
    .options(selectinload(Fixture.model))
    .where(Fixture.group_id == group_id)
)
```

---

## Security Considerations

### 1. Input Validation

Always validate and sanitize inputs:

```python
# Validate type conversions
try:
    if setting.value_type == "int":
        int(update.value)
    elif setting.value_type == "float":
        float(update.value)
except ValueError as e:
    raise HTTPException(
        status_code=400,
        detail=f"Invalid value for type {setting.value_type}: {str(e)}"
    )
```

### 2. No Authentication (v1)

System is designed for local network only:
- Daemon listens on `127.0.0.1` or local network
- No public exposure
- Authentication is out of scope for v1

---

## Troubleshooting Common Issues

### Session Management Errors

**Error**: `IllegalStateChangeError: Method 'close()' can't be called here`

**Cause**: Manually closing async generator sessions

**Fix**: Use the async generator pattern without manual closing (see Backend Best Practices #1)

### Port Already in Use

**Frontend port 3000 in use**:
```bash
# Use alternate port
npm run dev -- -p 3001
```

### Database Connection Issues

```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check connection
psql -U tau_daemon -d tau_lighting -h localhost

# Check credentials in .env or environment variables
echo $DATABASE_URL
```

### Hardware Not Detected

```bash
# Check LabJack connection
python -c "import u3; d = u3.U3(); print(d.configU3())"

# Check OLA
ola_dev_info

# Use mock mode for development
export LABJACK_MOCK=true
export OLA_MOCK=true
```

---

## Quick Reference

### Essential Commands

```bash
# SSH to Pi
ssh soldo@tau

# Start dev mode (on Pi)
export DATABASE_URL="postgresql://tau_daemon:tau_password@localhost:5432/tau_lighting"
export LABJACK_MOCK=false  # Use real hardware
export OLA_MOCK=false
python -m tau.main

# Production service
sudo systemctl status tau-daemon
sudo systemctl restart tau-daemon
sudo systemctl logs -f tau-daemon

# Database
alembic upgrade head
alembic current
psql -U tau_daemon -d tau_lighting

# Frontend
npm run build
sudo systemctl reload nginx
```

### File Locations on Pi

- Code: `~/code/tau/`
- Systemd service: `/etc/systemd/system/tau-daemon.service`
- Nginx config: `/etc/nginx/sites-available/tau`
- Database: PostgreSQL on localhost:5432
- Logs: `journalctl -u tau-daemon -f`

---

## Summary

This codebase follows modern best practices for a professional lighting control system:

- **Type-safe**: TypeScript frontend, Pydantic models, SQLAlchemy with Mapped types
- **Async-first**: Async/await throughout, proper session management
- **Hardware-aware**: Graceful degradation, automatic reconnection, mock support
- **Well-documented**: Living specs, comprehensive comments, structured logging
- **Maintainable**: Clear separation of concerns, consistent patterns, testable code
- **Production-ready**: Systemd service, migrations, persistent state, error handling

When making changes:
1. Follow established patterns
2. Update specs/ documentation
3. Test on the Raspberry Pi with real hardware
4. Commit with descriptive messages
5. Deploy to production when stable

---

*Last updated: January 2026*
