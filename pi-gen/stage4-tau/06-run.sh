#!/bin/bash -e
# Stage 4, Step 06: Create first-boot setup script

echo "=== Creating first-boot setup script ==="

# Create the first-boot setup script
cat > "${ROOTFS_DIR}/opt/tau-firstboot/tau-setup.sh" << 'SCRIPT'
#!/bin/bash
set -e

LOG_FILE="/var/log/tau/firstboot.log"
MARKER_FILE="/opt/tau-daemon/.firstboot-complete"

# Check if first boot setup already completed
if [ -f "$MARKER_FILE" ]; then
    echo "First boot setup already completed, skipping..."
    exit 0
fi

echo "$(date): Starting Tau first boot setup" | tee -a "$LOG_FILE"

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..." | tee -a "$LOG_FILE"
for i in {1..60}; do
    if sudo -u postgres pg_isready; then
        echo "PostgreSQL is ready" | tee -a "$LOG_FILE"
        break
    fi
    sleep 2
done

# Create database and user
echo "Setting up database..." | tee -a "$LOG_FILE"
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='tau_daemon'" | grep -q 1 || \
    sudo -u postgres createuser tau_daemon

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='tau_lighting'" | grep -q 1 || \
    sudo -u postgres createdb tau_lighting -O tau_daemon

sudo -u postgres psql -c "ALTER USER tau_daemon WITH PASSWORD 'tau_lighting_db';"

# Configure PostgreSQL to allow local password connections
PG_HBA=$(find /etc/postgresql -name pg_hba.conf | head -1)
if [ -n "$PG_HBA" ]; then
    if ! grep -q "tau_daemon" "$PG_HBA"; then
        echo "host tau_lighting tau_daemon 127.0.0.1/32 md5" >> "$PG_HBA"
        echo "host tau_lighting tau_daemon ::1/128 md5" >> "$PG_HBA"
        systemctl reload postgresql
    fi
fi

# Initialize database schema
echo "Initializing database schema..." | tee -a "$LOG_FILE"
cd /opt/tau-daemon/daemon
sudo -u tau bash -c "source .env && .venv/bin/alembic upgrade head" 2>&1 | tee -a "$LOG_FILE" || {
    # If alembic fails, try running init.sql directly
    echo "Alembic failed, trying direct SQL init..." | tee -a "$LOG_FILE"
    sudo -u postgres psql -d tau_lighting -f /opt/tau-daemon/database/init.sql 2>&1 | tee -a "$LOG_FILE"
}

# Enable and start services
echo "Enabling services..." | tee -a "$LOG_FILE"
systemctl daemon-reload
systemctl enable tau-daemon
systemctl enable tau-frontend

# Start services
echo "Starting services..." | tee -a "$LOG_FILE"
systemctl start tau-daemon
sleep 5
systemctl start tau-frontend

# Mark first boot as complete
touch "$MARKER_FILE"
echo "$(date): Tau first boot setup complete" | tee -a "$LOG_FILE"

# Print access information
PI_IP=$(hostname -I | awk '{print $1}')
echo ""
echo "=========================================="
echo "  Tau Lighting Control is ready!"
echo "=========================================="
echo ""
echo "  Web Interface: http://${PI_IP}/"
echo "  API Docs:      http://${PI_IP}:8000/docs"
echo "  OLA Interface: http://${PI_IP}:9090"
echo ""
echo "  Default credentials:"
echo "    Username: tau"
echo "    Password: tau-lighting"
echo ""
echo "=========================================="
SCRIPT

chmod +x "${ROOTFS_DIR}/opt/tau-firstboot/tau-setup.sh"

# Create systemd service for first-boot setup
cat > "${ROOTFS_DIR}/etc/systemd/system/tau-firstboot.service" << 'SERVICE'
[Unit]
Description=Tau Lighting Control First Boot Setup
After=network-online.target postgresql.service
Wants=network-online.target
ConditionPathExists=!/opt/tau-daemon/.firstboot-complete

[Service]
Type=oneshot
ExecStart=/opt/tau-firstboot/tau-setup.sh
RemainAfterExit=yes
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
SERVICE

echo "First-boot setup script created"
