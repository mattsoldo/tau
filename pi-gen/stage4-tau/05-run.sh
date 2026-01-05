#!/bin/bash -e
# Stage 4, Step 05: Install systemd services

echo "=== Installing systemd services ==="

# Create tau-daemon service
cat > "${ROOTFS_DIR}/etc/systemd/system/tau-daemon.service" << 'SERVICE'
[Unit]
Description=Tau Lighting Control Daemon
After=network.target postgresql.service olad.service
Wants=postgresql.service olad.service

[Service]
Type=simple
User=tau
Group=tau
WorkingDirectory=/opt/tau-daemon/daemon
EnvironmentFile=/opt/tau-daemon/daemon/.env
Environment="PYTHONPATH=/opt/tau-daemon/daemon/src"

ExecStart=/opt/tau-daemon/daemon/.venv/bin/python -m tau.main
Restart=on-failure
RestartSec=10s

# Security
NoNewPrivileges=true
PrivateTmp=true

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tau-daemon

[Install]
WantedBy=multi-user.target
SERVICE

# Create tau-frontend service
cat > "${ROOTFS_DIR}/etc/systemd/system/tau-frontend.service" << 'SERVICE'
[Unit]
Description=Tau Lighting Control Frontend (Next.js)
After=network.target tau-daemon.service
Wants=tau-daemon.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/tau-daemon/frontend
Environment="NODE_ENV=production"
Environment="PORT=80"

ExecStart=/usr/bin/npm start
Restart=on-failure
RestartSec=10s

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tau-frontend

[Install]
WantedBy=multi-user.target
SERVICE

echo "Systemd services installed"
