#!/bin/bash
# Start Tau Lighting Control in Development Mode
# This script starts both the backend daemon and frontend dev server

set -e

echo "========================================="
echo "Tau Lighting Control - Development Mode"
echo "========================================="
echo

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -d "daemon" ] || [ ! -d "frontend" ]; then
    echo "❌ Error: Must run from project root directory"
    echo "   Current directory: $(pwd)"
    exit 1
fi

# Function to cleanup background processes on exit
cleanup() {
    echo
    echo "🛑 Shutting down development servers..."
    if [ ! -z "$DAEMON_PID" ]; then
        kill $DAEMON_PID 2>/dev/null || true
    fi
    if [ ! -z "$FRONTEND_PID" ]; then
        kill $FRONTEND_PID 2>/dev/null || true
    fi
    exit
}

trap cleanup SIGINT SIGTERM

# Set up environment for daemon
cd daemon
export PYTHONPATH=$(pwd)/src
export DATABASE_URL="${DATABASE_URL:-postgresql://tau_daemon:tau_password@localhost:5432/tau_lighting}"
export LABJACK_MOCK="${LABJACK_MOCK:-true}"
export OLA_MOCK="${OLA_MOCK:-true}"
export LOG_LEVEL="${LOG_LEVEL:-INFO}"

echo -e "${BLUE}📦 Starting backend daemon...${NC}"
echo "   Database: $DATABASE_URL"
echo "   LabJack: ${LABJACK_MOCK} (mock)"
echo "   OLA: ${OLA_MOCK} (mock)"
echo "   Log level: $LOG_LEVEL"
echo

# Start daemon in background
.venv/bin/python -m tau.main &
DAEMON_PID=$!
echo -e "${GREEN}✓ Daemon started (PID: $DAEMON_PID)${NC}"
echo "   API: http://localhost:8000"
echo "   Docs: http://localhost:8000/docs"
echo

# Wait for daemon to be ready
echo "⏳ Waiting for daemon to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ Daemon is ready${NC}"
        break
    fi
    sleep 1
    if [ $i -eq 30 ]; then
        echo "❌ Daemon failed to start within 30 seconds"
        cleanup
    fi
done
echo

# Start frontend dev server
cd ../frontend
echo -e "${BLUE}📦 Starting frontend dev server...${NC}"
echo "   Mode: development (hot reload enabled)"
echo "   API proxy: http://localhost:8000"
echo

npm run dev &
FRONTEND_PID=$!
echo -e "${GREEN}✓ Frontend dev server started (PID: $FRONTEND_PID)${NC}"
echo "   UI: http://localhost:3000"
echo

echo "========================================="
echo -e "${GREEN}✅ Development environment ready!${NC}"
echo "========================================="
echo
echo "Frontend: http://localhost:3000"
echo "Backend:  http://localhost:8000"
echo "API Docs: http://localhost:8000/docs"
echo
echo "Press Ctrl+C to stop all servers"
echo

# Wait for background processes
wait
