#!/bin/bash -e
# Stage 3, Step 02: Install Node.js 20.x LTS

echo "=== Installing Node.js 20.x LTS ==="

on_chroot << EOF
# Install Node.js 20.x from NodeSource
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

# Verify installation
node --version
npm --version
EOF
