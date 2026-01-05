#!/bin/bash -e
# Stage 3, Step 03: Configure OLA (Open Lighting Architecture)

echo "=== Configuring OLA ==="

on_chroot << EOF
# Enable OLA daemon to start on boot
systemctl enable olad

# Add tau user to ola group for hardware access
usermod -aG plugdev tau || true
EOF

# Create OLA configuration directory
mkdir -p "${ROOTFS_DIR}/home/tau/.ola"
chown 1000:1000 "${ROOTFS_DIR}/home/tau/.ola"
