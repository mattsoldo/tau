#!/bin/bash
# Tau Lighting Control - Software Update Script
# This script is executed by the daemon to perform software updates

set -e  # Exit on any error

# Setup logging
LOG_DIR="/var/log/tau"
LOG_FILE="$LOG_DIR/update_$(date +%Y%m%d_%H%M%S).log"

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR" 2>/dev/null || true

# Logging function
log() {
    local timestamp=$(date +'%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] $1" | tee -a "$LOG_FILE"
}

log "========================================="
log "Tau Software Update Started"
log "========================================="

# Change to repository root
REPO_ROOT="/opt/tau-daemon"
if [ ! -d "$REPO_ROOT" ]; then
    log "ERROR: Repository directory not found: $REPO_ROOT"
    exit 1
fi

cd "$REPO_ROOT" || exit 1
log "Working directory: $(pwd)"

# Step 1: Git pull latest code
log ""
log "Step 1/6: Pulling latest code from git..."
if ! git pull origin main 2>&1 | tee -a "$LOG_FILE"; then
    log "ERROR: Git pull failed"
    exit 1
fi
NEW_VERSION=$(git rev-parse --short HEAD)
log "Updated to version: $NEW_VERSION"

# Step 2: Update backend Python dependencies
log ""
log "Step 2/6: Updating Python dependencies..."
cd "$REPO_ROOT/daemon" || exit 1

if [ ! -f ".venv/bin/pip" ]; then
    log "ERROR: Python virtual environment not found at .venv"
    exit 1
fi

if ! .venv/bin/pip install -r requirements.txt --upgrade 2>&1 | tee -a "$LOG_FILE"; then
    log "ERROR: Failed to install Python dependencies"
    exit 1
fi
log "Python dependencies updated successfully"

# Step 3: Run database migrations
log ""
log "Step 3/6: Running database migrations..."

# Source environment variables
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
    log "Loaded environment from .env"
else
    log "WARNING: .env file not found, using system environment"
fi

if ! .venv/bin/alembic upgrade head 2>&1 | tee -a "$LOG_FILE"; then
    log "ERROR: Database migration failed"
    exit 1
fi
log "Database migrations completed successfully"

# Step 4: Update frontend dependencies (if frontend exists)
log ""
log "Step 4/6: Updating frontend dependencies..."
cd "$REPO_ROOT/frontend" || {
    log "Frontend directory not found, skipping frontend update"
    cd "$REPO_ROOT"
}

if [ -f "package.json" ]; then
    log "Installing frontend dependencies..."
    if ! npm ci --production 2>&1 | tee -a "$LOG_FILE"; then
        log "ERROR: Failed to install frontend dependencies"
        exit 1
    fi
    log "Frontend dependencies installed successfully"

    # Step 5: Build frontend
    log ""
    log "Step 5/6: Building frontend..."
    if ! npm run build 2>&1 | tee -a "$LOG_FILE"; then
        log "ERROR: Frontend build failed"
        exit 1
    fi
    log "Frontend build completed successfully"
else
    log "Frontend package.json not found, skipping frontend build"
fi

# Step 6: Restart services
log ""
log "Step 6/6: Restarting services..."

# Restart backend daemon
log "Restarting tau-daemon service..."
if sudo systemctl restart tau-daemon 2>&1 | tee -a "$LOG_FILE"; then
    log "Backend daemon restarted successfully"
else
    log "WARNING: Failed to restart backend daemon"
fi

# Restart frontend (if it exists and is enabled)
if systemctl is-enabled tau-frontend &>/dev/null; then
    log "Restarting tau-frontend service..."
    if sudo systemctl restart tau-frontend 2>&1 | tee -a "$LOG_FILE"; then
        log "Frontend service restarted successfully"
    else
        log "WARNING: Failed to restart frontend service"
    fi
else
    log "Frontend service not enabled, skipping frontend restart"
fi

log ""
log "========================================="
log "Tau Software Update Completed Successfully"
log "Version: $NEW_VERSION"
log "Log file: $LOG_FILE"
log "========================================="

exit 0
