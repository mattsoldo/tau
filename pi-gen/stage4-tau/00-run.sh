#!/bin/bash -e
# Stage 4, Step 00: Create directory structure

echo "=== Creating Tau directory structure ==="

# Create installation directories
mkdir -p "${ROOTFS_DIR}/opt/tau-daemon"
mkdir -p "${ROOTFS_DIR}/opt/tau-firstboot"
mkdir -p "${ROOTFS_DIR}/var/log/tau"

# Set ownership
chown -R 1000:1000 "${ROOTFS_DIR}/opt/tau-daemon"
chown -R 1000:1000 "${ROOTFS_DIR}/var/log/tau"
