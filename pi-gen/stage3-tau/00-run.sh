#!/bin/bash -e
# Stage 3, Step 00: Configure system for Tau

echo "=== Configuring system for Tau Lighting Control ==="

# Create tau system user and group
on_chroot << EOF
# Create tau user if it doesn't exist
if ! id -u tau >/dev/null 2>&1; then
    useradd -r -m -s /bin/bash -G plugdev,dialout,gpio,i2c,spi tau
    echo "tau:tau-lighting" | chpasswd
fi

# Add tau user to required groups
usermod -aG plugdev,dialout,gpio,i2c,spi,audio,video tau || true
EOF
