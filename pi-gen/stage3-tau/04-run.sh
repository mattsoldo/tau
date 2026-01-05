#!/bin/bash -e
# Stage 3, Step 04: Configure LabJack USB permissions

echo "=== Configuring LabJack USB permissions ==="

# Create udev rule for LabJack U3
cat > "${ROOTFS_DIR}/etc/udev/rules.d/99-labjack.rules" << 'UDEV'
# LabJack U3-HV USB permissions
SUBSYSTEM=="usb", ATTR{idVendor}=="0cd5", ATTR{idProduct}=="0003", MODE="0666", GROUP="plugdev"
SUBSYSTEM=="usb", ATTR{idVendor}=="0cd5", ATTR{idProduct}=="0009", MODE="0666", GROUP="plugdev"

# LabJack UE9
SUBSYSTEM=="usb", ATTR{idVendor}=="0cd5", ATTR{idProduct}=="0009", MODE="0666", GROUP="plugdev"

# LabJack U6
SUBSYSTEM=="usb", ATTR{idVendor}=="0cd5", ATTR{idProduct}=="0006", MODE="0666", GROUP="plugdev"

# LabJack T-series
SUBSYSTEM=="usb", ATTR{idVendor}=="0cd5", MODE="0666", GROUP="plugdev"
UDEV

echo "LabJack udev rules installed"
