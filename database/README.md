# Tau Database

PostgreSQL database schema and migrations for the Tau lighting control system.

## Directory Structure

```
database/
├── init.sql          # Initial schema with indexes and views
├── migrations/       # Migration files (managed by Alembic)
├── seeds/            # Seed data for development
└── README.md         # This file
```

## Schema Overview

The database consists of several key components:

### Device Configuration
- `fixture_models` - Manufacturer specs for light fixtures
- `fixtures` - Physical fixtures with DMX addressing
- `switch_models` - Manufacturer specs for switches/dimmers
- `switches` - Physical input devices

### Logical Organization
- `groups` - Collections of fixtures (supports nesting up to 4 levels)
- `group_fixtures` - Many-to-many relationship between groups and fixtures
- `group_hierarchy` - Parent-child relationships for nested groups

### Lighting Programs
- `circadian_profiles` - Time-based lighting curves (brightness + CCT)
- `scenes` - Static lighting presets

### Runtime State
- `fixture_state` - Current state of each fixture (persisted across reboots)
- `group_state` - Group-level state (e.g., circadian suspension)

## Database Migrations

Migrations are managed using Alembic. See `/daemon/alembic/` for migration files.

### Running Migrations

From the daemon directory:

```bash
# Upgrade to latest
alembic upgrade head

# Upgrade one revision
alembic upgrade +1

# Downgrade one revision
alembic downgrade -1

# View migration history
alembic history

# View current revision
alembic current
```

### Creating New Migrations

```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "Add new feature"

# Create empty migration
alembic revision -m "Manual migration"
```

## Initial Setup

### Using Docker Compose

The database is automatically initialized when running:

```bash
docker-compose up database
```

The `init.sql` file is executed on first startup.

### Manual Setup

```bash
# Create database
createdb tau_lighting

# Run initialization script
psql tau_lighting < init.sql

# Run migrations
cd daemon
alembic upgrade head
```

## Views

### v_fixture_status
Combines fixture, model, and state information for easy querying.

```sql
SELECT * FROM v_fixture_status WHERE is_on = true;
```

### v_group_membership
Recursive view showing all fixtures in a group (including nested groups).

```sql
SELECT * FROM v_group_membership WHERE group_id = 1;
```

## Seed Data

Development seed data can be placed in `database/seeds/` directory.

Example seed files:
- `02-fixture-models.sql` - Common fixture manufacturers and models
- `03-switch-models.sql` - Common switch manufacturers and models
- `04-test-fixtures.sql` - Sample fixtures for testing

Seed files are automatically loaded by Docker Compose on first startup (in alphabetical order).

## Backup and Restore

### Backup

```bash
pg_dump tau_lighting > backup.sql

# Or with compression
pg_dump tau_lighting | gzip > backup.sql.gz
```

### Restore

```bash
psql tau_lighting < backup.sql

# Or from compressed
gunzip -c backup.sql.gz | psql tau_lighting
```

## Performance Considerations

### Indexes

The schema includes indexes on:
- Foreign keys for join performance
- DMX channels for collision detection
- State flags for filtered queries (partial indexes)
- Timestamps for chronological queries

### Connection Pooling

The daemon uses SQLAlchemy's async engine with connection pooling:
- Pool size: 20 connections
- Max overflow: 10 connections
- Pre-ping enabled for connection health checks

## Security

### User Permissions

For production, create a dedicated database user:

```sql
CREATE USER tau_daemon WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE tau_lighting TO tau_daemon;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO tau_daemon;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO tau_daemon;
```

### Network Access

Configure `pg_hba.conf` to restrict access:

```
# Local connections only
host    tau_lighting    tau_daemon    127.0.0.1/32    scram-sha-256
```

## Troubleshooting

### Check database connection

```bash
psql -U tau_daemon -d tau_lighting -c "SELECT version();"
```

### View active connections

```sql
SELECT * FROM pg_stat_activity WHERE datname = 'tau_lighting';
```

### Check table sizes

```sql
SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

### Reset database (development only)

```bash
docker-compose down -v
docker-compose up database
```
