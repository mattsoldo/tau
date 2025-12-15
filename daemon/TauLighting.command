#!/bin/bash
# Tau Lighting System - Mac App Launcher
# Double-click this file to start the system

# Get the directory where this script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Set terminal title
echo -n -e "\033]0;Tau Lighting Control System\007"

# ASCII Art Logo
cat << "EOF"
╔══════════════════════════════════════════════════╗
║                                                  ║
║        🏠 TAU LIGHTING CONTROL SYSTEM 🏠        ║
║         Smart Home Lighting for macOS           ║
║                                                  ║
╚══════════════════════════════════════════════════╝
EOF

echo ""
echo "Starting Tau Lighting System..."
echo "================================"

# Check for virtual environment
if [ ! -d "venv" ]; then
    echo "⚠️  Virtual environment not found"
    echo "Running setup..."
    echo ""

    # Create virtual environment
    python3 -m venv venv
    source venv/bin/activate

    # Install dependencies
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt

    echo "✓ Setup complete"
else
    source venv/bin/activate
fi

# Check PostgreSQL
if ! command -v psql &> /dev/null; then
    echo "⚠️  PostgreSQL not found"
    echo "Please install PostgreSQL:"
    echo "  brew install postgresql@15"
    echo "  brew services start postgresql@15"
    echo ""
    echo "Press any key to exit..."
    read -n 1
    exit 1
fi

# Load environment
if [ -f ".env" ]; then
    source .env
else
    # Create default environment
    cat > .env << 'ENV_EOF'
DATABASE_URL=postgresql://tau_daemon:tau_password@localhost/tau_lighting
PYTHONPATH=./src
LOG_LEVEL=INFO
LABJACK_MOCK=true
OLA_MOCK=true
API_HOST=0.0.0.0
API_PORT=8000
ENV_EOF
    source .env
fi

# Ensure database exists
createdb tau_lighting 2>/dev/null || true
psql -d tau_lighting -c "CREATE USER tau_daemon WITH PASSWORD 'tau_password';" 2>/dev/null || true

# Kill any existing instances
echo "Cleaning up old processes..."
pkill -f "python -m http.server 3000" 2>/dev/null
pkill -f "python -m tau.main" 2>/dev/null
sleep 1

# Start frontend server
echo "Starting frontend server..."
python -m http.server 3000 > /dev/null 2>&1 &
FRONTEND_PID=$!

# Start backend daemon
echo "Starting backend daemon..."
python -m tau.main &
DAEMON_PID=$!

# Wait for services to start
sleep 2

# Check if services are running
if kill -0 $DAEMON_PID 2>/dev/null && kill -0 $FRONTEND_PID 2>/dev/null; then
    echo ""
    echo "================================"
    echo "✅ System Started Successfully!"
    echo "================================"
    echo ""
    echo "🌐 Access Points:"
    echo "  • Dashboard:    http://localhost:3000"
    echo "  • Control:      http://localhost:3000/test_frontend.html"
    echo "  • API Docs:     http://localhost:8000/docs"
    echo ""

    # Get local IP for remote access
    LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)
    if [ ! -z "$LOCAL_IP" ]; then
        echo "📱 Remote Access (same network):"
        echo "  • Dashboard:    http://$LOCAL_IP:3000"
        echo ""
    fi

    echo "Press Ctrl+C to stop the system"
    echo "================================"

    # Open browser
    sleep 1
    open "http://localhost:3000" 2>/dev/null

    # Handle shutdown
    trap "echo ''; echo 'Shutting down...'; kill $FRONTEND_PID $DAEMON_PID 2>/dev/null; echo 'Goodbye!'; exit" INT

    # Keep running
    while true; do
        if ! kill -0 $DAEMON_PID 2>/dev/null; then
            echo "⚠️  Backend daemon stopped unexpectedly"
            break
        fi
        if ! kill -0 $FRONTEND_PID 2>/dev/null; then
            echo "⚠️  Frontend server stopped unexpectedly"
            break
        fi
        sleep 5
    done

    # Cleanup on unexpected exit
    kill $FRONTEND_PID $DAEMON_PID 2>/dev/null
else
    echo ""
    echo "❌ Failed to start services"
    echo ""
    echo "Check the logs for errors:"
    echo "  tail -f tau_daemon.log"
    echo ""
    echo "Press any key to exit..."
    read -n 1
fi