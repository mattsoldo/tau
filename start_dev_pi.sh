#!/bin/bash
# Start Tau in Development Mode on Raspberry Pi (Port 80)
# This script uses nginx to proxy the Next.js dev server so you can develop on port 80

set -e

echo "========================================="
echo "Tau Dev Mode - Raspberry Pi (Port 80)"
echo "========================================="
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "❌ Error: This script must be run with sudo"
  echo "   Usage: sudo ./start_dev_pi.sh"
  exit 1
fi

# Get the actual user (not root when using sudo)
ACTUAL_USER="${SUDO_USER:-$USER}"
ACTUAL_HOME=$(eval echo ~$ACTUAL_USER)

echo "Running as: $ACTUAL_USER"
echo

# Stop production tau-daemon service
echo "🛑 Stopping production tau-daemon service..."
systemctl stop tau-daemon || true
echo "✓ Production daemon stopped"
echo

# Configure nginx for dev mode (proxy to Next.js dev server on 3000)
echo "📋 Configuring nginx for dev mode..."
cat > /etc/nginx/sites-available/tau-dev << 'NGINX_EOF'
upstream tau_backend {
    server 127.0.0.1:8000;
}

upstream tau_frontend_dev {
    server 127.0.0.1:3000;
}

upstream ola_web {
    server 127.0.0.1:9090;
}

server {
    listen 80;
    server_name _;

    # Proxy settings
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # API backend routes
    location /api/ {
        proxy_pass http://tau_backend;
        proxy_http_version 1.1;
    }

    # Health and status endpoints
    location /health {
        proxy_pass http://tau_backend;
        proxy_http_version 1.1;
    }

    location /status {
        proxy_pass http://tau_backend;
        proxy_http_version 1.1;
    }

    # WebSocket support
    location /api/ws {
        proxy_pass http://tau_backend/ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }

    # LabJack and OLA monitor HTML files (served by backend)
    location ~ ^/(labjack_monitor\.html|ola_mock_interface\.html)$ {
        proxy_pass http://tau_backend;
        proxy_http_version 1.1;
    }

    # OLA Web UI (port 9090)
    location /ola/ {
        proxy_pass http://ola_web/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Next.js dev server (with hot reload)
    location / {
        proxy_pass http://tau_frontend_dev;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        # Disable buffering for hot reload
        proxy_buffering off;
    }

    # Next.js HMR (Hot Module Replacement)
    location /_next/webpack-hmr {
        proxy_pass http://tau_frontend_dev/_next/webpack-hmr;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
NGINX_EOF

# Enable dev config
rm -f /etc/nginx/sites-enabled/tau
ln -sf /etc/nginx/sites-available/tau-dev /etc/nginx/sites-enabled/tau-dev

# Test and reload nginx
nginx -t
systemctl reload nginx
echo "✓ Nginx configured for dev mode"
echo

# Start backend daemon in dev mode (foreground)
echo "🚀 Starting backend daemon in dev mode..."
cd /opt/tau-daemon/daemon

# Export environment as tau user
export PYTHONPATH=/opt/tau-daemon/daemon/src
export DATABASE_URL="postgresql://tau_daemon:tau_password@localhost:5432/tau_lighting"
export LABJACK_MOCK="${LABJACK_MOCK:-false}"
export OLA_MOCK="${OLA_MOCK:-false}"
export LOG_LEVEL="${LOG_LEVEL:-DEBUG}"

echo "   Database: $DATABASE_URL"
echo "   LabJack: $LABJACK_MOCK (mock)"
echo "   OLA: $OLA_MOCK (mock)"
echo "   Log level: $LOG_LEVEL"
echo

# Start daemon as tau user in background
sudo -u tau PYTHONPATH=$PYTHONPATH DATABASE_URL=$DATABASE_URL LABJACK_MOCK=$LABJACK_MOCK OLA_MOCK=$OLA_MOCK LOG_LEVEL=$LOG_LEVEL .venv/bin/python -m tau.main &
DAEMON_PID=$!
echo "✓ Daemon started (PID: $DAEMON_PID)"
echo

# Wait for daemon to be ready
echo "⏳ Waiting for daemon to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "✓ Daemon is ready"
        break
    fi
    sleep 1
    if [ $i -eq 30 ]; then
        echo "❌ Daemon failed to start within 30 seconds"
        kill $DAEMON_PID 2>/dev/null || true
        exit 1
    fi
done
echo

# Start frontend dev server
echo "🚀 Starting Next.js dev server..."
cd /opt/tau-daemon/frontend

# Start dev server as tau user in background
sudo -u tau npm run dev &
FRONTEND_PID=$!
echo "✓ Frontend dev server started (PID: $FRONTEND_PID)"
echo

# Wait for frontend to be ready
echo "⏳ Waiting for frontend dev server..."
for i in {1..30}; do
    if curl -s http://localhost:3000 > /dev/null 2>&1; then
        echo "✓ Frontend is ready"
        break
    fi
    sleep 1
done
echo

echo "========================================="
echo "✅ Development mode ready on port 80!"
echo "========================================="
echo
echo "Access at: http://$(hostname -I | awk '{print $1}')"
echo
echo "Backend:       http://localhost:8000 (direct)"
echo "Frontend Dev:  http://localhost:3000 (direct)"
echo "Via Nginx:     http://localhost (port 80)"
echo
echo "Features:"
echo "  - Hot reload enabled (save files to see changes)"
echo "  - API requests proxied to backend"
echo "  - Real hardware: LabJack=$LABJACK_MOCK, OLA=$OLA_MOCK"
echo
echo "Logs:"
echo "  - Backend: Check terminal or 'journalctl -f'"
echo "  - Frontend: Check terminal"
echo "  - Nginx: /var/log/nginx/error.log"
echo
echo "To stop dev mode:"
echo "  1. Press Ctrl+C"
echo "  2. Run: sudo systemctl start tau-daemon"
echo "  3. Run: sudo ./daemon/deployment/setup_nginx.sh (to restore prod config)"
echo

# Function to cleanup on exit
cleanup() {
    echo
    echo "🛑 Stopping development servers..."
    kill $DAEMON_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    echo "✓ Stopped"
}

trap cleanup SIGINT SIGTERM

# Wait for processes
wait
