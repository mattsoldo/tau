#!/bin/bash
#
# Tau Lighting Control - Custom Raspberry Pi Image Builder
#
# This script uses pi-gen to create a custom Raspberry Pi OS image
# with Tau Lighting Control pre-installed and configured.
#
# Prerequisites:
#   - Docker installed and running
#   - At least 10GB free disk space
#   - Internet connection
#
# Usage:
#   ./build.sh [options]
#
# Options:
#   --clean         Remove previous build artifacts before building
#   --continue      Continue a previous build (skip completed stages)
#   --docker        Use Docker build (recommended, default)
#   --native        Use native build (requires Debian-based system)
#   --help          Show this help message
#

set -e

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TAU_ROOT="$(dirname "$SCRIPT_DIR")"
PI_GEN_DIR="${SCRIPT_DIR}/pi-gen-repo"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default options
BUILD_MODE="docker"
CLEAN_BUILD=false
CONTINUE_BUILD=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --clean)
            CLEAN_BUILD=true
            shift
            ;;
        --continue)
            CONTINUE_BUILD=true
            shift
            ;;
        --docker)
            BUILD_MODE="docker"
            shift
            ;;
        --native)
            BUILD_MODE="native"
            shift
            ;;
        --help)
            head -30 "$0" | tail -25
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  Tau Lighting Control - Image Builder${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if [[ "$BUILD_MODE" == "docker" ]]; then
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Error: Docker is not installed${NC}"
        echo "Please install Docker: https://docs.docker.com/get-docker/"
        exit 1
    fi

    if ! docker info &> /dev/null; then
        echo -e "${RED}Error: Docker daemon is not running${NC}"
        echo "Please start Docker and try again"
        exit 1
    fi
    echo -e "${GREEN}✓ Docker is available${NC}"
fi

# Clone or update pi-gen
if [ ! -d "$PI_GEN_DIR" ]; then
    echo -e "${YELLOW}Cloning pi-gen repository...${NC}"
    git clone --depth 1 https://github.com/RPi-Distro/pi-gen.git "$PI_GEN_DIR"
else
    echo -e "${YELLOW}Updating pi-gen repository...${NC}"
    cd "$PI_GEN_DIR"
    git pull origin master || true
fi

cd "$PI_GEN_DIR"

# Clean previous build if requested
if [[ "$CLEAN_BUILD" == true ]]; then
    echo -e "${YELLOW}Cleaning previous build...${NC}"
    rm -rf work deploy
    rm -f stage3-tau stage4-tau
fi

# Skip default stages 3, 4, 5 (we use our custom stages)
touch stage3/SKIP stage3/SKIP_IMAGES
touch stage4/SKIP stage4/SKIP_IMAGES
touch stage5/SKIP stage5/SKIP_IMAGES

# Link our custom stages
echo -e "${YELLOW}Linking custom stages...${NC}"
rm -f stage3-tau stage4-tau
ln -sf "${SCRIPT_DIR}/stage3-tau" stage3-tau
ln -sf "${SCRIPT_DIR}/stage4-tau" stage4-tau

# Copy config file
echo -e "${YELLOW}Copying configuration...${NC}"
cp "${SCRIPT_DIR}/config" config

# Make stage scripts executable
chmod +x "${SCRIPT_DIR}/stage3-tau"/*.sh 2>/dev/null || true
chmod +x "${SCRIPT_DIR}/stage4-tau"/*.sh 2>/dev/null || true

# Copy tau source files to a staging directory for the build
echo -e "${YELLOW}Preparing Tau source files...${NC}"
STAGING_DIR="${PI_GEN_DIR}/tau-source"
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"

# Copy only necessary files (exclude node_modules, .venv, etc.)
rsync -av --progress \
    --exclude 'node_modules' \
    --exclude '.venv' \
    --exclude 'venv' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.git' \
    --exclude '.next' \
    --exclude 'pi-gen' \
    --exclude 'pi-gen-repo' \
    --exclude '*.img' \
    --exclude '*.zip' \
    "${TAU_ROOT}/" "$STAGING_DIR/"

# Update stage4-tau to use the staging directory
sed -i "s|TAU_SOURCE=.*|TAU_SOURCE=\"${STAGING_DIR}\"|g" "${SCRIPT_DIR}/stage4-tau/01-run.sh"

# Build the image
echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  Starting pi-gen build...${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo -e "${YELLOW}This will take 30-60 minutes depending on your system.${NC}"
echo ""

if [[ "$BUILD_MODE" == "docker" ]]; then
    # Docker build
    if [[ "$CONTINUE_BUILD" == true ]]; then
        DOCKER_OPTS="-c"
    else
        DOCKER_OPTS=""
    fi

    ./build-docker.sh $DOCKER_OPTS
else
    # Native build (requires Debian-based system with sudo)
    if [[ "$CONTINUE_BUILD" == true ]]; then
        sudo CONTINUE=1 ./build.sh
    else
        sudo ./build.sh
    fi
fi

# Check for output
echo ""
if [ -d "deploy" ]; then
    echo -e "${GREEN}================================================${NC}"
    echo -e "${GREEN}  Build Complete!${NC}"
    echo -e "${GREEN}================================================${NC}"
    echo ""
    echo "Image files are located in:"
    echo "  ${PI_GEN_DIR}/deploy/"
    echo ""
    ls -lh deploy/

    # Copy to tau pi-gen directory
    echo ""
    echo "Copying image to ${SCRIPT_DIR}/output/..."
    mkdir -p "${SCRIPT_DIR}/output"
    cp deploy/*.img* "${SCRIPT_DIR}/output/" 2>/dev/null || true
    cp deploy/*.zip "${SCRIPT_DIR}/output/" 2>/dev/null || true

    echo ""
    echo "To write the image to an SD card:"
    echo ""
    echo "  # On Linux/macOS:"
    echo "  sudo dd if=output/tau-lighting-*.img of=/dev/sdX bs=4M status=progress"
    echo ""
    echo "  # Or use Raspberry Pi Imager:"
    echo "  https://www.raspberrypi.com/software/"
    echo ""
else
    echo -e "${RED}Build may have failed. Check the logs above.${NC}"
    exit 1
fi
