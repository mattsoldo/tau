#!/bin/bash -e
# Stage 4, Step 01: Copy Tau application files

echo "=== Copying Tau application files ==="

# The tau source is staged in pi-gen-repo/tau-source by the build script
# This path is relative to the pi-gen directory
TAU_SOURCE="${PI_GEN_REPO_DIR:-/pi-gen}/tau-source"

# If running in Docker, the path may be different
if [ ! -d "$TAU_SOURCE" ] && [ -d "/pi-gen/tau-source" ]; then
    TAU_SOURCE="/pi-gen/tau-source"
fi

# Fallback to checking relative paths
if [ ! -d "$TAU_SOURCE" ]; then
    # Try the work directory
    for path in \
        "${STAGE_WORK_DIR}/../../../tau-source" \
        "${BASE_DIR}/tau-source" \
        "$(dirname "${BASH_SOURCE[0]}")/../../tau-source" \
        "/home/user/tau"
    do
        if [ -d "$path" ]; then
            TAU_SOURCE="$path"
            break
        fi
    done
fi

echo "Using TAU_SOURCE: $TAU_SOURCE"

if [ ! -d "$TAU_SOURCE" ]; then
    echo "ERROR: Cannot find Tau source directory!"
    echo "Searched paths:"
    echo "  - /pi-gen/tau-source"
    echo "  - ${STAGE_WORK_DIR}/../../../tau-source"
    echo "  - ${BASE_DIR}/tau-source"
    exit 1
fi

# Copy daemon (backend)
echo "Copying daemon..."
cp -r "${TAU_SOURCE}/daemon" "${ROOTFS_DIR}/opt/tau-daemon/"

# Copy database scripts
echo "Copying database..."
cp -r "${TAU_SOURCE}/database" "${ROOTFS_DIR}/opt/tau-daemon/"

# Copy frontend
echo "Copying frontend..."
cp -r "${TAU_SOURCE}/frontend" "${ROOTFS_DIR}/opt/tau-daemon/"

# Copy root files if they exist
echo "Copying configuration files..."
[ -f "${TAU_SOURCE}/docker-compose.yml" ] && cp "${TAU_SOURCE}/docker-compose.yml" "${ROOTFS_DIR}/opt/tau-daemon/" || true
[ -f "${TAU_SOURCE}/.env.example" ] && cp "${TAU_SOURCE}/.env.example" "${ROOTFS_DIR}/opt/tau-daemon/" || true

# Remove any existing node_modules, .venv, etc. that may have been copied
echo "Cleaning up..."
rm -rf "${ROOTFS_DIR}/opt/tau-daemon/frontend/node_modules" 2>/dev/null || true
rm -rf "${ROOTFS_DIR}/opt/tau-daemon/frontend/.next" 2>/dev/null || true
rm -rf "${ROOTFS_DIR}/opt/tau-daemon/daemon/.venv" 2>/dev/null || true
rm -rf "${ROOTFS_DIR}/opt/tau-daemon/daemon/venv" 2>/dev/null || true
find "${ROOTFS_DIR}/opt/tau-daemon" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "${ROOTFS_DIR}/opt/tau-daemon" -type f -name "*.pyc" -delete 2>/dev/null || true

# Set ownership
chown -R 1000:1000 "${ROOTFS_DIR}/opt/tau-daemon"

echo "Tau application files copied successfully"
