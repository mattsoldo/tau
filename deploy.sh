#!/bin/bash
# Tau Lighting Control - Robust Deployment Script
# This script safely updates and restarts the Tau system on Raspberry Pi
#
# Usage:
#   sudo ./deploy.sh          # Interactive mode - ask before rebuilding if up to date
#   sudo ./deploy.sh --force  # Force rebuild even if up to date

set -e  # Exit on error

# Parse command line arguments
FORCE_REBUILD=false
if [[ "$1" == "--force" ]]; then
    FORCE_REBUILD=true
fi

echo "========================================="
echo "Tau Deployment Script"
echo "========================================="
echo

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running on Raspberry Pi
if [ ! -d "/opt/tau-daemon" ]; then
    echo -e "${RED}❌ Error: /opt/tau-daemon not found${NC}"
    echo "This script should be run on the Raspberry Pi"
    exit 1
fi

# Check if running as root (needed for systemctl and process killing)
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}❌ Error: This script must be run with sudo${NC}"
    echo "Usage: sudo ./deploy.sh"
    exit 1
fi

# Get the actual user (not root when using sudo)
ACTUAL_USER="${SUDO_USER:-tau}"

echo -e "${YELLOW}🛑 Step 1: Stopping existing processes...${NC}"

# Stop tau-frontend service if running
if systemctl is-active --quiet tau-frontend; then
    echo "  Stopping tau-frontend service..."
    systemctl stop tau-frontend || true
fi

# Kill any Node.js/Next.js processes (dev servers, orphaned processes)
echo "  Killing any Node.js/Next.js processes..."
pkill -f "next dev" || true
pkill -f "next start" || true
pkill -f "npm.*start" || true
pkill -f "npm.*dev" || true
sleep 2  # Give processes time to terminate

# Double check and force kill if needed
if pgrep -f "next" > /dev/null; then
    echo "  Force killing remaining Next.js processes..."
    pkill -9 -f "next" || true
    sleep 1
fi

# Verify port 3000 is free
if lsof -i :3000 > /dev/null 2>&1; then
    echo -e "${YELLOW}  Warning: Port 3000 still in use, force clearing...${NC}"
    lsof -t -i :3000 | xargs kill -9 || true
    sleep 1
fi

echo -e "${GREEN}✓ All processes stopped${NC}"
echo

echo -e "${YELLOW}🔄 Step 2: Checking for updates...${NC}"
cd /opt/tau-daemon

# Fix ownership to prevent git permission issues
echo "  Ensuring correct file ownership..."
chown -R $ACTUAL_USER:$ACTUAL_USER /opt/tau-daemon

# Ensure git doesn't complain about ownership
if ! sudo -u $ACTUAL_USER git config --get safe.directory | grep -q "/opt/tau-daemon"; then
    sudo -u $ACTUAL_USER git config --global --add safe.directory /opt/tau-daemon
fi

# Fetch latest changes
sudo -u $ACTUAL_USER git fetch origin
BEHIND=$(sudo -u $ACTUAL_USER git rev-list HEAD..origin/main --count)

if [ "$BEHIND" -eq 0 ]; then
    echo -e "${GREEN}✓ Already up to date${NC}"
    echo
    # Ask if user wants to rebuild anyway (unless --force flag is used)
    if [ "$FORCE_REBUILD" = false ]; then
        read -p "Rebuild and restart anyway? (y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Deployment cancelled"
            exit 0
        fi
    else
        echo "  Force rebuild requested via --force flag"
    fi
else
    echo "  $BEHIND commit(s) behind origin/main"
    echo
    echo "Recent changes:"
    sudo -u $ACTUAL_USER git log --oneline HEAD..origin/main | head -5
    echo
fi

echo -e "${YELLOW}📥 Step 3: Applying updates...${NC}"

# Pull latest code
echo "  Pulling latest code..."
sudo -u $ACTUAL_USER git pull origin main
CURRENT_COMMIT=$(sudo -u $ACTUAL_USER git rev-parse --short HEAD)
echo -e "${GREEN}✓ Updated to commit $CURRENT_COMMIT${NC}"
echo

echo -e "${YELLOW}🔧 Step 4: Updating backend...${NC}"

# Update Python dependencies
cd /opt/tau-daemon/daemon
echo "  Installing Python dependencies..."
sudo -u $ACTUAL_USER .venv/bin/pip install -r requirements.txt --upgrade -q
echo -e "${GREEN}✓ Python dependencies updated${NC}"

# Run database migrations
echo "  Running database migrations..."
if [ -f .env ]; then
    # Export environment variables from .env file
    set -a
    source .env
    set +a
    if sudo -u $ACTUAL_USER bash -c "cd /opt/tau-daemon/daemon && source .env && .venv/bin/alembic upgrade head" 2>&1; then
        echo -e "${GREEN}✓ Database migrations complete${NC}"
    else
        echo -e "${YELLOW}⚠ Warning: Database migrations failed (continuing anyway)${NC}"
        echo "  This may be okay if database is already up to date or not configured"
    fi
else
    echo -e "${YELLOW}⚠ Warning: .env file not found, skipping migrations${NC}"
fi
echo

echo -e "${YELLOW}🎨 Step 5: Building frontend...${NC}"

cd /opt/tau-daemon/frontend

# Clean build artifacts
echo "  Cleaning build cache..."
sudo -u $ACTUAL_USER rm -rf .next out node_modules/.cache
echo -e "${GREEN}✓ Cache cleared${NC}"

# Install/update frontend dependencies
echo "  Installing frontend dependencies..."
sudo -u $ACTUAL_USER npm ci --production -q
echo -e "${GREEN}✓ Frontend dependencies installed${NC}"

# Build frontend (static export)
echo "  Building frontend (this may take a minute)..."
sudo -u $ACTUAL_USER NODE_ENV=production npm run build
echo -e "${GREEN}✓ Frontend built successfully${NC}"

# Verify build output exists
if [ ! -d "out" ]; then
    echo -e "${RED}❌ Error: Frontend build failed - 'out' directory not found${NC}"
    exit 1
fi
echo

echo -e "${YELLOW}🔄 Step 6: Restarting services...${NC}"

# Restart backend daemon
echo "  Restarting tau-daemon..."
systemctl restart tau-daemon
sleep 2

# Check if daemon started successfully
if ! systemctl is-active --quiet tau-daemon; then
    echo -e "${RED}❌ Error: tau-daemon failed to start${NC}"
    echo "Check logs with: sudo journalctl -u tau-daemon -n 50"
    exit 1
fi
echo -e "${GREEN}✓ Backend daemon restarted${NC}"

# Ensure frontend service is disabled (we serve static files via nginx)
if systemctl is-enabled --quiet tau-frontend 2>/dev/null; then
    echo "  Disabling tau-frontend service (not needed for static export)..."
    systemctl disable tau-frontend || true
fi

# Reload nginx
echo "  Reloading nginx..."
nginx -t || {
    echo -e "${RED}❌ Error: nginx configuration test failed${NC}"
    exit 1
}
systemctl reload nginx
echo -e "${GREEN}✓ Nginx reloaded${NC}"
echo

echo -e "${YELLOW}🔍 Step 7: Verifying deployment...${NC}"

# Wait for backend to be ready
echo "  Waiting for backend to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Backend is responding${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}❌ Error: Backend failed to respond within 30 seconds${NC}"
        echo "Check logs with: sudo journalctl -u tau-daemon -n 50"
        exit 1
    fi
    sleep 1
done

# Test frontend
echo "  Testing frontend..."
if curl -s http://localhost/ | grep -q "Tau Lighting Control"; then
    echo -e "${GREEN}✓ Frontend is serving correctly${NC}"
else
    echo -e "${RED}❌ Error: Frontend not responding correctly${NC}"
    exit 1
fi

# Test API proxy
echo "  Testing API proxy..."
if curl -s http://localhost/api/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ API proxy working${NC}"
else
    echo -e "${YELLOW}⚠ Warning: API proxy test failed${NC}"
fi

# Show service status
echo
echo -e "${YELLOW}📊 Service Status:${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
systemctl status tau-daemon --no-pager -l | head -4 | tail -1
systemctl status postgresql --no-pager -l | head -4 | tail -1
systemctl status olad --no-pager -l | head -4 | tail -1
systemctl status nginx --no-pager -l | head -4 | tail -1
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo

# Get Pi's IP address
PI_IP=$(hostname -I | awk '{print $1}')

echo "========================================="
echo -e "${GREEN}✅ Deployment Complete!${NC}"
echo "========================================="
echo
echo "Deployed commit: $CURRENT_COMMIT"
echo
echo "Access Points:"
echo "  Web UI:       http://$PI_IP/"
echo "  API:          http://$PI_IP/api/"
echo "  API Docs:     http://$PI_IP:8000/docs"
echo "  OLA Web UI:   http://$PI_IP/ola/"
echo
echo "Useful Commands:"
echo "  View logs:    sudo journalctl -u tau-daemon -f"
echo "  Restart:      sudo systemctl restart tau-daemon"
echo "  Status:       sudo systemctl status tau-daemon"
echo
