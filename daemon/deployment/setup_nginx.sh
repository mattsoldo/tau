#!/bin/bash
# Setup nginx reverse proxy for Tau Lighting Control
# This script installs and configures nginx to serve the frontend and proxy API requests

set -e  # Exit on error

echo "========================================="
echo "Tau Lighting Control - Nginx Setup"
echo "========================================="
echo

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "ERROR: This script must be run as root (use sudo)"
  exit 1
fi

# Install nginx if not already installed
echo "📦 Checking for nginx..."
if ! command -v nginx &> /dev/null; then
    echo "Installing nginx..."
    apt-get update
    apt-get install -y nginx
else
    echo "✓ nginx is already installed"
fi

# Stop tau-frontend service if it's running (we'll use nginx instead)
echo
echo "🛑 Stopping old frontend service..."
if systemctl is-active --quiet tau-frontend; then
    systemctl stop tau-frontend
    echo "✓ Stopped tau-frontend"
fi

if systemctl is-enabled --quiet tau-frontend 2>/dev/null; then
    systemctl disable tau-frontend
    echo "✓ Disabled tau-frontend (nginx will serve static files instead)"
fi

# Build the frontend static files
echo
echo "🔨 Building frontend static files..."
cd /opt/tau-daemon/frontend
sudo -u tau npm run build
echo "✓ Frontend built successfully"

# Create nginx log directory if it doesn't exist
mkdir -p /var/log/nginx

# Copy nginx configuration
echo
echo "📋 Installing nginx configuration..."
cp /opt/tau-daemon/daemon/deployment/tau-nginx.conf /etc/nginx/sites-available/tau

# Remove default nginx site if it exists
if [ -L /etc/nginx/sites-enabled/default ]; then
    rm /etc/nginx/sites-enabled/default
    echo "✓ Removed default nginx site"
fi

# Create symlink to enable the site
if [ -L /etc/nginx/sites-enabled/tau ]; then
    rm /etc/nginx/sites-enabled/tau
fi
ln -s /etc/nginx/sites-available/tau /etc/nginx/sites-enabled/tau
echo "✓ Enabled Tau nginx site"

# Test nginx configuration
echo
echo "🧪 Testing nginx configuration..."
nginx -t

# Restart nginx to apply changes
echo
echo "♻️  Restarting nginx..."
systemctl restart nginx
systemctl enable nginx
echo "✓ nginx restarted and enabled"

# Check status
echo
echo "📊 Service status:"
systemctl status nginx --no-pager -l || true

echo
echo "========================================="
echo "✅ Nginx setup complete!"
echo "========================================="
echo
echo "The Tau web interface is now available at:"
echo "  http://$(hostname -I | awk '{print $1}')"
echo
echo "Backend API is proxied via /api/*"
echo "WebSocket connections via /api/ws"
echo
echo "Note: The old tau-frontend service has been disabled."
echo "Nginx now serves the static frontend files directly."
