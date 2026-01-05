#!/bin/bash
# Tau Lighting Control - Safe Deployment Script with Automatic Backup & Rollback
#
# This script provides safety features for deploying updates:
# - Automatic pre-deployment backups (code + database)
# - Health checks at each step
# - Automatic rollback on failure
# - Manual rollback command
#
# Usage:
#   sudo ./deploy-safe.sh                    # Safe deployment with backups
#   sudo ./deploy-safe.sh --force            # Force rebuild even if up to date
#   sudo ./deploy-safe.sh --rollback         # Rollback to last backup
#   sudo ./deploy-safe.sh --list-backups     # List available backups
#   sudo ./deploy-safe.sh --rollback-to ID   # Rollback to specific backup

set -e  # Exit on error

# Configuration
BACKUP_DIR="/opt/tau-backups"
TAU_DIR="/opt/tau-daemon"
MAX_BACKUPS=5  # Keep last 5 backups
BACKUP_ID=$(date +%Y%m%d-%H%M%S)
BACKUP_METADATA="$BACKUP_DIR/backup-$BACKUP_ID.meta"
LATEST_BACKUP_LINK="$BACKUP_DIR/latest-backup.meta"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Parse command line arguments
MODE="deploy"
FORCE_REBUILD=false
ROLLBACK_TARGET=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --rollback)
            MODE="rollback"
            shift
            ;;
        --rollback-to)
            MODE="rollback"
            ROLLBACK_TARGET="$2"
            shift 2
            ;;
        --list-backups)
            MODE="list"
            shift
            ;;
        --force)
            FORCE_REBUILD=true
            shift
            ;;
        --help|-h)
            echo "Tau Safe Deployment Script"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --force              Force rebuild even if up to date"
            echo "  --rollback           Rollback to most recent backup"
            echo "  --rollback-to ID     Rollback to specific backup ID"
            echo "  --list-backups       List available backups"
            echo "  --help               Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Error: This script must be run with sudo${NC}"
    echo "Usage: sudo ./deploy-safe.sh"
    exit 1
fi

# Get actual user (not root when using sudo)
ACTUAL_USER="${SUDO_USER:-tau}"

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "${RED}❌${NC} $1"
}

log_step() {
    echo -e "${CYAN}▶${NC} $1"
}

# List available backups
list_backups() {
    echo "========================================="
    echo "Available Backups"
    echo "========================================="
    echo ""

    if [ ! -d "$BACKUP_DIR" ] || [ -z "$(ls -A $BACKUP_DIR/*.meta 2>/dev/null)" ]; then
        log_warning "No backups found"
        exit 0
    fi

    echo -e "${CYAN}ID                  COMMIT    DATE/TIME           STATUS${NC}"
    echo "─────────────────────────────────────────────────────────────────"

    for meta in $(ls -t $BACKUP_DIR/*.meta 2>/dev/null | grep -v latest-backup); do
        if [ -f "$meta" ]; then
            source "$meta"

            # Check if backup files still exist
            BACKUP_STATUS="${GREEN}✓ Valid${NC}"
            if [ ! -f "$BACKUP_CODE_FILE" ] || [ ! -f "$BACKUP_DB_FILE" ]; then
                BACKUP_STATUS="${RED}✗ Missing${NC}"
            fi

            # Format output
            printf "%-19s %-9s %-19s %b\n" \
                "$BACKUP_ID" \
                "$GIT_COMMIT_SHORT" \
                "$(date -d "@$BACKUP_TIMESTAMP" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -r "$BACKUP_TIMESTAMP" '+%Y-%m-%d %H:%M:%S')" \
                "$BACKUP_STATUS"
        fi
    done

    echo ""

    if [ -L "$LATEST_BACKUP_LINK" ]; then
        LATEST_ID=$(basename "$(readlink "$LATEST_BACKUP_LINK")" .meta | sed 's/backup-//')
        echo -e "${CYAN}Latest backup: ${NC}$LATEST_ID"
    fi
}

# Create backup
create_backup() {
    log_step "Creating pre-deployment backup..."

    # Create backup directory
    mkdir -p "$BACKUP_DIR"

    # Get current git commit
    cd "$TAU_DIR"
    GIT_COMMIT=$(git rev-parse HEAD)
    GIT_COMMIT_SHORT=$(git rev-parse --short HEAD)
    GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

    # Define backup file paths
    BACKUP_CODE_FILE="$BACKUP_DIR/code-$BACKUP_ID.tar.gz"
    BACKUP_DB_FILE="$BACKUP_DIR/db-$BACKUP_ID.sql"

    # Backup code (exclude build artifacts and dependencies)
    log_info "  Backing up code..."
    tar -czf "$BACKUP_CODE_FILE" \
        --exclude='.venv' \
        --exclude='node_modules' \
        --exclude='.next' \
        --exclude='out' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        -C /opt tau-daemon 2>/dev/null

    CODE_SIZE=$(du -h "$BACKUP_CODE_FILE" | cut -f1)
    log_success "  Code backed up ($CODE_SIZE)"

    # Backup database
    log_info "  Backing up database..."
    if sudo -u postgres pg_dump tau_lighting > "$BACKUP_DB_FILE" 2>/dev/null; then
        DB_SIZE=$(du -h "$BACKUP_DB_FILE" | cut -f1)
        log_success "  Database backed up ($DB_SIZE)"
    else
        log_warning "  Database backup failed (may not be configured)"
        echo "-- No database backup" > "$BACKUP_DB_FILE"
    fi

    # Save metadata
    cat > "$BACKUP_METADATA" << EOF
BACKUP_ID="$BACKUP_ID"
BACKUP_TIMESTAMP=$(date +%s)
BACKUP_DATE="$(date '+%Y-%m-%d %H:%M:%S')"
GIT_COMMIT="$GIT_COMMIT"
GIT_COMMIT_SHORT="$GIT_COMMIT_SHORT"
GIT_BRANCH="$GIT_BRANCH"
BACKUP_CODE_FILE="$BACKUP_CODE_FILE"
BACKUP_DB_FILE="$BACKUP_DB_FILE"
EOF

    # Update latest backup link
    ln -sf "$BACKUP_METADATA" "$LATEST_BACKUP_LINK"

    # Clean old backups
    BACKUP_COUNT=$(ls -1 "$BACKUP_DIR"/*.meta 2>/dev/null | grep -v latest-backup | wc -l)
    if [ "$BACKUP_COUNT" -gt "$MAX_BACKUPS" ]; then
        log_info "  Cleaning old backups (keeping last $MAX_BACKUPS)..."
        ls -t "$BACKUP_DIR"/*.meta | grep -v latest-backup | tail -n +$((MAX_BACKUPS + 1)) | while read meta; do
            BACKUP_TO_DELETE=$(basename "$meta" .meta | sed 's/backup-//')
            rm -f "$BACKUP_DIR/code-$BACKUP_TO_DELETE.tar.gz"
            rm -f "$BACKUP_DIR/db-$BACKUP_TO_DELETE.sql"
            rm -f "$meta"
            log_info "    Removed backup: $BACKUP_TO_DELETE"
        done
    fi

    log_success "Backup created: $BACKUP_ID"
    echo ""
}

# Rollback to backup
perform_rollback() {
    local target_backup="$1"

    # Determine which backup to use
    if [ -z "$target_backup" ]; then
        # Use latest backup
        if [ ! -L "$LATEST_BACKUP_LINK" ]; then
            log_error "No backups found to rollback to"
            exit 1
        fi
        ROLLBACK_META="$(readlink "$LATEST_BACKUP_LINK")"
        target_backup=$(basename "$ROLLBACK_META" .meta | sed 's/backup-//')
    else
        ROLLBACK_META="$BACKUP_DIR/backup-$target_backup.meta"
        if [ ! -f "$ROLLBACK_META" ]; then
            log_error "Backup not found: $target_backup"
            echo "Run: sudo ./deploy-safe.sh --list-backups"
            exit 1
        fi
    fi

    # Load backup metadata
    source "$ROLLBACK_META"

    # Verify backup files exist
    if [ ! -f "$BACKUP_CODE_FILE" ]; then
        log_error "Backup code file not found: $BACKUP_CODE_FILE"
        exit 1
    fi
    if [ ! -f "$BACKUP_DB_FILE" ]; then
        log_error "Backup database file not found: $BACKUP_DB_FILE"
        exit 1
    fi

    echo "========================================="
    echo "ROLLBACK INITIATED"
    echo "========================================="
    echo ""
    log_warning "Rolling back to backup: $BACKUP_ID"
    log_info "  Date: $BACKUP_DATE"
    log_info "  Commit: $GIT_COMMIT_SHORT ($GIT_BRANCH)"
    echo ""

    read -p "$(echo -e ${YELLOW}Are you sure you want to rollback? This will stop services. [y/N]: ${NC})" -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Rollback cancelled"
        exit 0
    fi
    echo ""

    # Stop services
    log_step "Stopping services..."
    systemctl stop tau-daemon || true
    sleep 2
    log_success "Services stopped"
    echo ""

    # Restore code
    log_step "Restoring code from backup..."
    cd /opt

    # Move current installation to temp location (in case we need it)
    if [ -d "$TAU_DIR" ]; then
        TEMP_DIR="/tmp/tau-daemon-before-rollback-$(date +%s)"
        mv "$TAU_DIR" "$TEMP_DIR"
        log_info "  Current installation moved to: $TEMP_DIR"
    fi

    # Extract backup
    tar -xzf "$BACKUP_CODE_FILE" -C /opt
    chown -R $ACTUAL_USER:$ACTUAL_USER "$TAU_DIR"
    log_success "Code restored"
    echo ""

    # Restore database
    log_step "Restoring database..."
    if grep -q "No database backup" "$BACKUP_DB_FILE"; then
        log_warning "No database backup available, skipping database restore"
    else
        sudo -u postgres dropdb tau_lighting 2>/dev/null || true
        sudo -u postgres createdb tau_lighting
        sudo -u postgres psql tau_lighting < "$BACKUP_DB_FILE" > /dev/null 2>&1
        log_success "Database restored"
    fi
    echo ""

    # Reinstall Python dependencies (in case requirements changed)
    log_step "Reinstalling Python dependencies..."
    cd "$TAU_DIR/daemon"
    sudo -u $ACTUAL_USER .venv/bin/pip install -r requirements.txt --upgrade -q 2>/dev/null || {
        log_warning "Failed to update dependencies, trying with existing..."
    }
    log_success "Python dependencies ready"
    echo ""

    # Rebuild frontend
    log_step "Rebuilding frontend..."
    cd "$TAU_DIR/frontend"
    sudo -u $ACTUAL_USER rm -rf .next out node_modules/.cache 2>/dev/null || true
    sudo -u $ACTUAL_USER npm ci -q 2>/dev/null || {
        log_warning "npm ci failed, trying npm install..."
        sudo -u $ACTUAL_USER npm install -q 2>/dev/null || true
    }
    sudo -u $ACTUAL_USER NODE_ENV=production npm run build 2>&1 | tail -5
    log_success "Frontend rebuilt"
    echo ""

    # Restart services
    log_step "Restarting services..."
    systemctl start tau-daemon
    sleep 3

    if systemctl is-active --quiet tau-daemon; then
        log_success "Backend daemon started"
    else
        log_error "Backend daemon failed to start"
        echo "Check logs: sudo journalctl -u tau-daemon -n 50"
        exit 1
    fi

    # Reload nginx
    nginx -t && systemctl reload nginx
    log_success "Nginx reloaded"
    echo ""

    # Verify deployment
    log_step "Verifying rollback..."
    sleep 2

    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        log_success "Backend is responding"
    else
        log_error "Backend health check failed"
        exit 1
    fi

    if curl -s http://localhost/ | grep -q "Tau"; then
        log_success "Frontend is serving"
    else
        log_warning "Frontend may not be serving correctly"
    fi

    echo ""
    echo "========================================="
    log_success "ROLLBACK COMPLETE"
    echo "========================================="
    echo ""
    echo "Restored to:"
    echo "  Backup ID: $BACKUP_ID"
    echo "  Commit: $GIT_COMMIT_SHORT"
    echo "  Date: $BACKUP_DATE"
    echo ""
}

# Perform safe deployment
perform_deployment() {
    echo "========================================="
    echo "Tau Safe Deployment"
    echo "========================================="
    echo ""

    # Check if tau-daemon directory exists
    if [ ! -d "$TAU_DIR" ]; then
        log_error "/opt/tau-daemon not found"
        echo "This script should be run on the Raspberry Pi with Tau installed"
        exit 1
    fi

    # Create backup
    create_backup

    # Store backup ID for potential rollback
    DEPLOYMENT_BACKUP_ID="$BACKUP_ID"

    # Show what we're about to do
    cd "$TAU_DIR"
    sudo -u $ACTUAL_USER git fetch origin 2>/dev/null
    BEHIND=$(sudo -u $ACTUAL_USER git rev-list HEAD..origin/main --count)

    if [ "$BEHIND" -eq 0 ]; then
        log_info "Already up to date with origin/main"
        if [ "$FORCE_REBUILD" = false ]; then
            read -p "$(echo -e ${YELLOW}Rebuild and restart anyway? [y/N]: ${NC})" -n 1 -r
            echo ""
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                log_info "Deployment cancelled"
                exit 0
            fi
        fi
    else
        log_info "$BEHIND commit(s) behind origin/main"
        echo ""
        log_info "Recent changes:"
        sudo -u $ACTUAL_USER git log --oneline HEAD..origin/main | head -5
        echo ""
    fi

    # Run deployment with error handling
    log_step "Running deployment script..."
    echo ""

    set +e  # Don't exit on error, we want to handle it

    if [ "$FORCE_REBUILD" = true ]; then
        ./deploy.sh --force
    else
        ./deploy.sh
    fi

    DEPLOY_EXIT_CODE=$?
    set -e

    echo ""

    # Check if deployment succeeded
    if [ $DEPLOY_EXIT_CODE -eq 0 ]; then
        # Verify services are actually running
        sleep 3

        if ! systemctl is-active --quiet tau-daemon; then
            log_error "Deployment script succeeded but daemon is not running"
            DEPLOY_EXIT_CODE=1
        elif ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
            log_error "Deployment script succeeded but health check failed"
            DEPLOY_EXIT_CODE=1
        fi
    fi

    if [ $DEPLOY_EXIT_CODE -eq 0 ]; then
        echo "========================================="
        log_success "DEPLOYMENT SUCCESSFUL"
        echo "========================================="
        echo ""
        NEW_COMMIT=$(cd "$TAU_DIR" && git rev-parse --short HEAD)
        echo "Deployed commit: $NEW_COMMIT"
        echo "Backup ID: $DEPLOYMENT_BACKUP_ID"
        echo ""
        log_info "If issues arise, rollback with:"
        echo "  sudo ./deploy-safe.sh --rollback"
        echo ""
    else
        echo "========================================="
        log_error "DEPLOYMENT FAILED"
        echo "========================================="
        echo ""
        log_warning "Initiating automatic rollback..."
        echo ""
        sleep 2

        # Perform automatic rollback
        perform_rollback "$DEPLOYMENT_BACKUP_ID"

        echo ""
        log_error "Deployment failed and was rolled back"
        echo "Check deployment logs above for errors"
        exit 1
    fi
}

# Main script logic
case $MODE in
    list)
        list_backups
        ;;
    rollback)
        perform_rollback "$ROLLBACK_TARGET"
        ;;
    deploy)
        perform_deployment
        ;;
    *)
        log_error "Unknown mode: $MODE"
        exit 1
        ;;
esac
