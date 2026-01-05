#!/bin/bash -e
# Stage 4, Step 03: Build frontend

echo "=== Building frontend ==="

on_chroot << EOF
cd /opt/tau-daemon/frontend

# Install npm dependencies
npm ci

# Build the production frontend
# The frontend dynamically detects API URL from browser hostname
npm run build

# Clean up dev dependencies to save space
npm prune --production

# Set ownership
chown -R tau:tau /opt/tau-daemon/frontend
EOF
