#!/bin/bash -e
# Stage 4, Step 02: Install Python dependencies and create virtual environment

echo "=== Setting up Python environment ==="

on_chroot << EOF
cd /opt/tau-daemon/daemon

# Create virtual environment
python3 -m venv .venv

# Upgrade pip
.venv/bin/pip install --upgrade pip wheel setuptools

# Install requirements
.venv/bin/pip install -r requirements.txt

# Install OLA Python bindings
.venv/bin/pip install ola || echo "OLA Python bindings may need to be installed separately"

# Install LabJackPython
.venv/bin/pip install LabJackPython

# Set ownership
chown -R tau:tau /opt/tau-daemon
EOF
