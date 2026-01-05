#!/bin/bash -e
# Stage 3, Step 01: Configure PostgreSQL

echo "=== Configuring PostgreSQL ==="

on_chroot << EOF
# Enable PostgreSQL to start on boot
systemctl enable postgresql
EOF

# Create first-boot directory if it doesn't exist
mkdir -p "${ROOTFS_DIR}/opt/tau-firstboot"

# Create PostgreSQL configuration script for first boot
cat > "${ROOTFS_DIR}/opt/tau-firstboot/setup-postgres.sh" << 'SCRIPT'
#!/bin/bash
set -e

# Wait for PostgreSQL to be ready
for i in {1..30}; do
    if sudo -u postgres pg_isready; then
        break
    fi
    sleep 1
done

# Create tau database and user if they don't exist
sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='tau_daemon'" | grep -q 1 || \
    sudo -u postgres createuser tau_daemon

sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='tau_lighting'" | grep -q 1 || \
    sudo -u postgres createdb tau_lighting -O tau_daemon

# Set password
sudo -u postgres psql -c "ALTER USER tau_daemon WITH PASSWORD 'tau_lighting_db';"

# Allow local connections with password
echo "host tau_lighting tau_daemon 127.0.0.1/32 md5" | sudo tee -a /etc/postgresql/*/main/pg_hba.conf

# Restart PostgreSQL to apply changes
sudo systemctl restart postgresql

echo "PostgreSQL configured successfully"
SCRIPT

chmod +x "${ROOTFS_DIR}/opt/tau-firstboot/setup-postgres.sh"
