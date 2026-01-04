#!/bin/bash
# Uninstall script for Tau Lighting Control System on Raspberry Pi
# This script completely removes all Tau components for clean testing

set -e

echo "========================================"
echo "Tau Lighting System - Uninstall"
echo "========================================"
echo ""
echo "⚠️  WARNING: This will completely remove Tau and all its data!"
read -p "Are you sure you want to continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Uninstall cancelled."
    exit 0
fi

echo ""
echo "Starting uninstall process..."

# 1. Stop and disable services
echo ""
echo "1. Stopping and disabling services..."
sudo systemctl stop tau-daemon 2>/dev/null || echo "  tau-daemon not running"
sudo systemctl stop tau-frontend 2>/dev/null || echo "  tau-frontend not running"
sudo systemctl disable tau-daemon 2>/dev/null || echo "  tau-daemon not enabled"
sudo systemctl disable tau-frontend 2>/dev/null || echo "  tau-frontend not enabled"
echo "✓ Services stopped and disabled"

# 2. Remove systemd service files
echo ""
echo "2. Removing systemd service files..."
sudo rm -f /etc/systemd/system/tau-daemon.service
sudo rm -f /etc/systemd/system/tau-frontend.service
sudo systemctl daemon-reload
echo "✓ Service files removed"

# 3. Remove installation directory
echo ""
echo "3. Removing installation directory..."
sudo rm -rf /opt/tau-daemon
echo "✓ Installation directory removed"

# 4. Drop PostgreSQL database and user
echo ""
echo "4. Removing PostgreSQL database and user..."
sudo -u postgres psql -c "DROP DATABASE IF EXISTS tau_lighting;" 2>/dev/null || echo "  Database already removed"
sudo -u postgres psql -c "DROP USER IF EXISTS tau_daemon;" 2>/dev/null || echo "  User already removed"
echo "✓ Database and user removed"

# 5. Remove tau system user
echo ""
echo "5. Removing tau system user..."
if id "tau" &>/dev/null; then
    sudo userdel tau 2>/dev/null || echo "  User removal failed (non-critical)"
    echo "✓ System user removed"
else
    echo "  tau user does not exist"
fi

# 6. Remove logs
echo ""
echo "6. Removing log directory..."
sudo rm -rf /var/log/tau
echo "✓ Logs removed"

# 7. Remove sudo configuration
echo ""
echo "7. Removing sudo configuration..."
sudo rm -f /etc/sudoers.d/tau-daemon
echo "✓ Sudo configuration removed"

# 8. Remove udev rules
echo ""
echo "8. Removing LabJack udev rules..."
sudo rm -f /etc/udev/rules.d/99-labjack.rules
sudo udevadm control --reload-rules 2>/dev/null || true
sudo udevadm trigger 2>/dev/null || true
echo "✓ Udev rules removed"

# 9. Clean up any remaining configuration
echo ""
echo "9. Cleaning up remaining files..."
# Remove any backup files
sudo rm -f /tmp/tau.env 2>/dev/null || true
echo "✓ Cleanup complete"

echo ""
echo "========================================"
echo "✅ Uninstall Complete!"
echo "========================================"
echo ""
echo "The following were removed:"
echo "  • Systemd services (tau-daemon, tau-frontend)"
echo "  • Installation directory (/opt/tau-daemon)"
echo "  • PostgreSQL database (tau_lighting)"
echo "  • PostgreSQL user (tau_daemon)"
echo "  • System user (tau)"
echo "  • Log directory (/var/log/tau)"
echo "  • Sudo configuration (/etc/sudoers.d/tau-daemon)"
echo "  • LabJack udev rules (/etc/udev/rules.d/99-labjack.rules)"
echo ""
echo "System packages (Python, PostgreSQL, OLA, Node.js) were NOT removed."
echo "To remove them manually, run:"
echo "  sudo apt-get remove --purge postgresql ola nodejs"
echo "  sudo apt-get autoremove"
echo ""
echo "To reinstall Tau, run:"
echo "  cd ~"
echo "  git clone https://github.com/mattsoldo/tau.git"
echo "  cd tau/daemon"
echo "  chmod +x setup_pi.sh"
echo "  sudo ./setup_pi.sh"
echo ""
echo "========================================"
