# Tau Lighting Control - Deployment Guide

This guide covers deployment options for the Tau lighting control daemon in production environments.

## Table of Contents

1. [Docker Deployment](#docker-deployment)
2. [Systemd Service](#systemd-service)
3. [Nginx Reverse Proxy (Recommended)](#nginx-reverse-proxy-recommended)
4. [Database Setup](#database-setup)
5. [Configuration](#configuration)
6. [Hardware Setup](#hardware-setup)
7. [Security](#security)
8. [Monitoring](#monitoring)
9. [Troubleshooting](#troubleshooting)

---

## Docker Deployment

### Quick Start

The easiest way to run Tau is using Docker Compose:

```bash
# Clone repository
git clone https://github.com/yourusername/tau-daemon.git
cd tau-daemon

# Set environment variables
cp .env.example .env
# Edit .env with your configuration

# Start services
docker-compose up -d

# Check logs
docker-compose logs -f tau-daemon

# Stop services
docker-compose down
```

### Docker Compose Services

The `docker-compose.yml` includes:

1. **postgres** - PostgreSQL 15 database
   - Port: 5432
   - Volume: `postgres_data` for persistence
   - Health checks enabled

2. **tau-daemon** - Main lighting control service
   - Port: 8000 (HTTP/WebSocket)
   - Depends on healthy postgres
   - Auto-restart on failure

3. **pgadmin** (optional) - Database management UI
   - Port: 5050
   - Profile: `tools` (start with `--profile tools`)

### Environment Variables

Create a `.env` file:

```bash
# Database password
POSTGRES_PASSWORD=your_secure_password_here

# PgAdmin password (if using tools profile)
PGADMIN_PASSWORD=admin_password_here
```

### Docker Commands

```bash
# Build and start
docker-compose up -d

# View logs
docker-compose logs -f tau-daemon
docker-compose logs -f postgres

# Restart service
docker-compose restart tau-daemon

# Stop all services
docker-compose down

# Stop and remove volumes (WARNING: deletes database)
docker-compose down -v

# Start with pgAdmin
docker-compose --profile tools up -d
```

### Health Checks

Both services have health checks configured:

- **PostgreSQL**: `pg_isready` every 10s
- **Tau Daemon**: HTTP GET `/health` every 30s

Check health status:

```bash
docker-compose ps
```

### Updating

```bash
# Pull latest code
git pull

# Rebuild and restart
docker-compose up -d --build

# Run database migrations
docker-compose exec tau-daemon alembic upgrade head
```

---

## Systemd Service

For bare-metal deployments on Linux, use systemd.

### Prerequisites

```bash
# Install Python 3.11+
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3-pip

# Install PostgreSQL
sudo apt-get install -y postgresql postgresql-contrib

# Install system dependencies
sudo apt-get install -y gcc libusb-1.0-0-dev
```

### Installation

```bash
# Create tau user
sudo useradd -r -s /bin/false tau

# Create installation directory
sudo mkdir -p /opt/tau-daemon
sudo chown tau:tau /opt/tau-daemon

# Clone repository
cd /opt/tau-daemon
sudo -u tau git clone https://github.com/yourusername/tau-daemon.git .

# Create virtual environment
sudo -u tau python3.11 -m venv .venv
sudo -u tau .venv/bin/pip install --upgrade pip
sudo -u tau .venv/bin/pip install -r requirements.txt

# Create log directory
sudo mkdir -p /var/log/tau
sudo chown tau:tau /var/log/tau
```

### Database Setup

```bash
# Create database user
sudo -u postgres createuser tau_daemon

# Create database
sudo -u postgres createdb tau_lighting -O tau_daemon

# Set password
sudo -u postgres psql -c "ALTER USER tau_daemon WITH PASSWORD 'your_password';"

# Run migrations
cd /opt/tau-daemon
sudo -u tau .venv/bin/alembic upgrade head
```

### Service Configuration

Copy the service file:

```bash
sudo cp deployment/tau-daemon.service /etc/systemd/system/
sudo systemctl daemon-reload
```

Edit `/etc/systemd/system/tau-daemon.service` to adjust:
- Database credentials
- Port number
- Log level
- Control loop frequency

### Service Management

```bash
# Enable and start
sudo systemctl enable tau-daemon
sudo systemctl start tau-daemon

# Check status
sudo systemctl status tau-daemon

# View logs
sudo journalctl -u tau-daemon -f

# Restart
sudo systemctl restart tau-daemon

# Stop
sudo systemctl stop tau-daemon

# Disable
sudo systemctl disable tau-daemon
```

### Updating with Systemd

```bash
# Stop service
sudo systemctl stop tau-daemon

# Update code
cd /opt/tau-daemon
sudo -u tau git pull

# Install dependencies
sudo -u tau .venv/bin/pip install -r requirements.txt

# Run migrations
sudo -u tau .venv/bin/alembic upgrade head

# Start service
sudo systemctl start tau-daemon
```

---

## Nginx Reverse Proxy (Recommended)

For production deployments, use nginx as a reverse proxy to serve both the frontend and backend on port 80.

### Benefits

- **Single port**: Both frontend and backend accessible on port 80
- **Simplified URLs**: No port numbers needed (`http://192.168.1.100` instead of `http://192.168.1.100:3000`)
- **Better performance**: nginx serves static files efficiently
- **Production-ready**: Standard web server architecture

### Quick Setup

Run the automated setup script:

```bash
cd /opt/tau-daemon
sudo ./daemon/deployment/setup_nginx.sh
```

This script will:
1. Install nginx if not already installed
2. Build the frontend static files
3. Stop and disable the old tau-frontend service
4. Install nginx configuration
5. Enable and start nginx

### Manual Setup

If you prefer manual configuration:

```bash
# Install nginx
sudo apt-get update
sudo apt-get install -y nginx

# Build frontend
cd /opt/tau-daemon/frontend
sudo -u tau npm run build

# Install nginx configuration
sudo cp /opt/tau-daemon/daemon/deployment/tau-nginx.conf /etc/nginx/sites-available/tau

# Remove default site
sudo rm /etc/nginx/sites-enabled/default

# Enable Tau site
sudo ln -s /etc/nginx/sites-available/tau /etc/nginx/sites-enabled/tau

# Test configuration
sudo nginx -t

# Restart nginx
sudo systemctl restart nginx
sudo systemctl enable nginx

# Disable old frontend service
sudo systemctl stop tau-frontend
sudo systemctl disable tau-frontend
```

### Architecture

With nginx reverse proxy:

- **Frontend**: Static files served by nginx from `/opt/tau-daemon/frontend/out`
- **Backend API**: Proxied to `localhost:8000` for `/api/*` routes
- **WebSocket**: Proxied to `localhost:8000/ws` for `/api/ws`
- **Health/Status**: Proxied to `localhost:8000` for `/health` and `/status`

### URL Structure

Before (without nginx):
- Frontend: `http://192.168.1.100:3000`
- Backend: `http://192.168.1.100:8000/api/fixtures/`

After (with nginx):
- Frontend: `http://192.168.1.100/`
- Backend: `http://192.168.1.100/api/fixtures/`

### Updating Frontend

After making frontend changes:

```bash
# Rebuild static files
cd /opt/tau-daemon/frontend
sudo -u tau npm run build

# Nginx will automatically serve the new files (no restart needed)
```

### Troubleshooting Nginx

**Check nginx status**:
```bash
sudo systemctl status nginx
```

**View nginx logs**:
```bash
# Access log
sudo tail -f /var/log/nginx/tau-access.log

# Error log
sudo tail -f /var/log/nginx/tau-error.log
```

**Test configuration**:
```bash
sudo nginx -t
```

**Reload configuration** (without dropping connections):
```bash
sudo systemctl reload nginx
```

**Check which process is using port 80**:
```bash
sudo lsof -i :80
```

---

## Database Setup

### Initial Schema

Run Alembic migrations to create tables:

```bash
# Docker
docker-compose exec tau-daemon alembic upgrade head

# Systemd
cd /opt/tau-daemon
sudo -u tau .venv/bin/alembic upgrade head
```

### Load Example Configuration

Populate the database with example fixtures, groups, and scenes:

```bash
# Docker
docker-compose exec tau-daemon python scripts/load_example_config.py

# Systemd
cd /opt/tau-daemon
sudo -u tau .venv/bin/python scripts/load_example_config.py
```

### Custom Configuration

1. Copy example config:
   ```bash
   cp examples/example_config.yaml my_config.yaml
   ```

2. Edit `my_config.yaml` with your fixtures, groups, etc.

3. Load:
   ```bash
   # Docker
   docker-compose exec tau-daemon python scripts/load_example_config.py my_config.yaml

   # Systemd
   sudo -u tau .venv/bin/python scripts/load_example_config.py my_config.yaml
   ```

### Backup and Restore

```bash
# Backup
pg_dump -U tau_daemon tau_lighting > tau_backup.sql

# Restore
psql -U tau_daemon tau_lighting < tau_backup.sql
```

---

## Configuration

### Environment Variables

The daemon is configured via environment variables:

#### Database
- `DATABASE_URL` - PostgreSQL connection string
  - Format: `postgresql://user:password@host:port/database`
  - Default: `postgresql://tau_daemon:tau_password@localhost/tau_lighting`

#### API
- `DAEMON_PORT` - HTTP/WebSocket port (default: 8000)
- `API_TITLE` - API documentation title (default: "Tau Lighting Control")
- `API_VERSION` - API version (default: "0.1.0")
- `API_DOCS_ENABLED` - Enable /docs endpoint (default: true)

#### Logging
- `LOG_LEVEL` - DEBUG, INFO, WARNING, ERROR (default: INFO)

#### Control Loop
- `CONTROL_LOOP_HZ` - Event loop frequency in Hz (default: 30)
  - Higher = more responsive, higher CPU usage
  - Lower = less responsive, lower CPU usage

#### Hardware
- `LABJACK_MOCK` - Use mock LabJack driver (default: false)
- `OLA_MOCK` - Use mock OLA/DMX driver (default: false)

### Docker Environment

Set in `docker-compose.yml` or `.env`:

```yaml
environment:
  DATABASE_URL: postgresql://tau_daemon:password@postgres:5432/tau_lighting
  DAEMON_PORT: 8000
  LOG_LEVEL: INFO
  CONTROL_LOOP_HZ: 30
  LABJACK_MOCK: "false"
  OLA_MOCK: "false"
```

### Systemd Environment

Set in `/etc/systemd/system/tau-daemon.service`:

```ini
[Service]
Environment="DATABASE_URL=postgresql://tau_daemon:password@localhost/tau_lighting"
Environment="DAEMON_PORT=8000"
Environment="LOG_LEVEL=INFO"
Environment="CONTROL_LOOP_HZ=30"
```

---

## Hardware Setup

### LabJack (Analog/Digital IO)

1. **Install LabJack drivers**:
   - Download from https://labjack.com/support/software/installers
   - Follow platform-specific instructions

2. **Connect LabJack**:
   - USB connection to host
   - Verify with `lsusb` (Linux) or LabJack LJM utility

3. **Configure switches**:
   - Digital pins: 0-15 (buttons, retractive switches)
   - Analog pins: 0-15 (potentiometers, 0-2.4V)

4. **Disable mock mode**:
   ```bash
   LABJACK_MOCK=false
   ```

### OLA/DMX (Lighting Output)

1. **Install OLA**:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install ola

   # macOS
   brew install ola
   ```

2. **Configure OLA**:
   - Start OLA daemon: `olad`
   - Web UI: http://localhost:9090
   - Configure DMX interface (USB DMX adapter)

3. **Verify OLA**:
   ```bash
   ola_dev_info
   ola_streaming_client --dmx 255,0,0  # Test red
   ```

4. **Disable mock mode**:
   ```bash
   OLA_MOCK=false
   ```

### Mock Mode (Testing)

For testing without physical hardware:

```bash
LABJACK_MOCK=true
OLA_MOCK=true
```

Mock drivers simulate hardware responses but don't control actual devices.

---

## Security

### Network Security

1. **Firewall**:
   ```bash
   # Allow daemon port
   sudo ufw allow 8000/tcp

   # Restrict to local network
   sudo ufw allow from 192.168.1.0/24 to any port 8000
   ```

2. **Reverse Proxy** (optional):
   - Use nginx/Apache for HTTPS
   - Add authentication
   - Rate limiting

### Database Security

1. **Strong passwords**:
   - Use unique password for `tau_daemon` user
   - Store in `.env`, not in version control

2. **Network restrictions**:
   ```bash
   # Edit /etc/postgresql/15/main/pg_hba.conf
   # Restrict to localhost
   local   tau_lighting    tau_daemon    md5
   host    tau_lighting    tau_daemon    127.0.0.1/32    md5
   ```

3. **Regular backups**:
   ```bash
   # Daily backup cron
   0 2 * * * pg_dump -U tau_daemon tau_lighting > /backup/tau_$(date +\%Y\%m\%d).sql
   ```

### Systemd Security

The service file includes security hardening:

- `NoNewPrivileges=true` - Prevents privilege escalation
- `PrivateTmp=true` - Isolated /tmp
- `ProtectSystem=strict` - Read-only system directories
- `ProtectHome=true` - No access to /home
- `ReadWritePaths=/var/log/tau /opt/tau-daemon` - Limited write access

### Application Security

1. **API rate limiting** - Implement in reverse proxy
2. **Input validation** - Pydantic schemas validate all inputs
3. **SQL injection** - SQLAlchemy ORM prevents injection
4. **WebSocket authentication** - Add auth to /ws endpoint

---

## Monitoring

### Health Check

```bash
# HTTP health check
curl http://localhost:8000/health

# Expected response:
{"status":"healthy","timestamp":"2025-01-15T10:30:00"}
```

### Status Endpoint

```bash
curl http://localhost:8000/status

# Returns:
{
  "event_loop": {"running": true, "hz": 30, "avg_iteration_ms": 0.4},
  "hardware": {"labjack": "connected", "ola": "connected"},
  "lighting": {"fixtures_on": 5, "circadian_groups": 3}
}
```

### Logs

```bash
# Docker
docker-compose logs -f tau-daemon

# Systemd
sudo journalctl -u tau-daemon -f

# File logs (if configured)
tail -f /var/log/tau/daemon.log
```

### Metrics

Key metrics to monitor:

- **Event loop Hz** - Should stay near 30 Hz
- **Iteration time** - Should be < 33ms (1/30th second)
- **Hardware status** - "connected" vs "disconnected"
- **Database connections** - Check for leaks
- **Memory usage** - Should be stable (< 200MB)

### Alerting

Set up alerts for:

1. **Service down**:
   ```bash
   # Check if service is running
   systemctl is-active tau-daemon
   ```

2. **Health check fails**:
   ```bash
   # Returns non-zero on failure
   curl -f http://localhost:8000/health
   ```

3. **Event loop slow**:
   - Check status endpoint
   - Alert if `avg_iteration_ms > 30`

---

## Troubleshooting

### Service Won't Start

**Check logs**:
```bash
# Systemd
sudo journalctl -u tau-daemon -n 50

# Docker
docker-compose logs tau-daemon
```

**Common issues**:

1. **Database connection error**:
   - Verify PostgreSQL is running
   - Check DATABASE_URL
   - Test connection: `psql $DATABASE_URL`

2. **Port already in use**:
   - Check: `sudo lsof -i :8000`
   - Change port: `DAEMON_PORT=8001`

3. **Permission denied**:
   - Check file ownership: `ls -l /opt/tau-daemon`
   - Fix: `sudo chown -R tau:tau /opt/tau-daemon`

### Event Loop Running Slow

**Symptoms**: Status shows event loop < 30 Hz or high iteration times

**Solutions**:

1. **Reduce control loop frequency**:
   ```bash
   CONTROL_LOOP_HZ=10  # Lower frequency
   ```

2. **Check CPU usage**:
   ```bash
   top -p $(pgrep -f tau.main)
   ```

3. **Optimize database queries**:
   - Check for missing indexes
   - Reduce state persistence frequency

### Hardware Not Responding

**LabJack**:
```bash
# Check USB connection
lsusb | grep LabJack

# Test with LJM utility
# Follow LabJack troubleshooting guide
```

**OLA/DMX**:
```bash
# Check OLA daemon
systemctl status olad

# List devices
ola_dev_info

# Test output
ola_streaming_client --dmx 255,255,255
```

### WebSocket Disconnects

**Symptoms**: Clients frequently disconnect

**Solutions**:

1. **Check network stability**:
   - Ping daemon: `ping <daemon-ip>`
   - Check for packet loss

2. **Increase timeout**:
   - Configure WebSocket keepalive
   - Client should send periodic pings

3. **Check logs** for errors:
   ```bash
   sudo journalctl -u tau-daemon | grep -i websocket
   ```

### Database Performance

**Slow queries**:
```sql
-- Enable slow query logging
ALTER DATABASE tau_lighting SET log_min_duration_statement = 100;

-- View slow queries
SELECT * FROM pg_stat_statements ORDER BY total_time DESC LIMIT 10;
```

**Connection pool exhausted**:
- Increase pool size in SQLAlchemy configuration
- Check for connection leaks

### API Errors

**429 Too Many Requests**:
- Implement rate limiting in reverse proxy
- Reduce client request frequency

**500 Internal Server Error**:
- Check daemon logs for exceptions
- Verify database connectivity
- Check state manager integrity

---

## Production Checklist

Before deploying to production:

- [ ] Change default database password
- [ ] Set `LOG_LEVEL=WARNING` or `ERROR`
- [ ] Enable firewall rules
- [ ] Configure automated backups
- [ ] Set up monitoring/alerting
- [ ] Test hardware connections
- [ ] Load production configuration
- [ ] Test all API endpoints
- [ ] Test WebSocket connections
- [ ] Document any customizations
- [ ] Set up reverse proxy with HTTPS (optional)
- [ ] Configure service to start on boot
- [ ] Test failure recovery (restart service)
- [ ] Verify log rotation configured

---

## Support

For issues or questions:

- GitHub Issues: https://github.com/yourusername/tau-daemon/issues
- Documentation: See README.md and examples/README.md
- API Docs: http://localhost:8000/docs (when daemon running)
