#!/bin/bash
#
# Tau Lighting Control System - Raspberry Pi Setup Script
#
# This script fetches the latest code from GitHub, installs dependencies,
# and runs the Tau lighting control system on a Raspberry Pi.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/YOUR_ORG/tau/main/scripts/pi-setup.sh | bash
#
# Or download and run:
#   wget https://raw.githubusercontent.com/YOUR_ORG/tau/main/scripts/pi-setup.sh
#   chmod +x pi-setup.sh
#   ./pi-setup.sh
#
# Options:
#   --gpio          Use Raspberry Pi GPIO for switch inputs (default)
#   --labjack       Use LabJack U3 for switch inputs
#   --no-frontend   Skip frontend installation
#   --dev           Install development dependencies
#

set -e

# Configuration
TAU_DIR="${TAU_DIR:-$HOME/tau}"
TAU_REPO="${TAU_REPO:-https://github.com/YOUR_ORG/tau.git}"
TAU_BRANCH="${TAU_BRANCH:-main}"
USE_GPIO="${USE_GPIO:-true}"
USE_LABJACK="${USE_LABJACK:-false}"
INSTALL_FRONTEND="${INSTALL_FRONTEND:-true}"
DEV_MODE="${DEV_MODE:-false}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --gpio)
            USE_GPIO="true"
            USE_LABJACK="false"
            shift
            ;;
        --labjack)
            USE_LABJACK="true"
            USE_GPIO="false"
            shift
            ;;
        --no-frontend)
            INSTALL_FRONTEND="false"
            shift
            ;;
        --dev)
            DEV_MODE="true"
            shift
            ;;
        --help|-h)
            echo "Tau Lighting Control System - Raspberry Pi Setup"
            echo ""
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --gpio          Use Raspberry Pi GPIO for switch inputs (default)"
            echo "  --labjack       Use LabJack U3 for switch inputs"
            echo "  --no-frontend   Skip frontend installation"
            echo "  --dev           Install development dependencies"
            echo "  --help          Show this help message"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            exit 1
            ;;
    esac
done

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running on Raspberry Pi
check_pi() {
    if [[ -f /proc/device-tree/model ]]; then
        MODEL=$(cat /proc/device-tree/model)
        if [[ "$MODEL" == *"Raspberry Pi"* ]]; then
            log_success "Detected: $MODEL"
            return 0
        fi
    fi
    log_warn "Not running on a Raspberry Pi. Some features may not work."
    return 0
}

# Check for required commands
check_requirements() {
    log_info "Checking system requirements..."

    local missing=()

    for cmd in git curl python3 pip3; do
        if ! command -v $cmd &> /dev/null; then
            missing+=($cmd)
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        log_warn "Missing commands: ${missing[*]}"
        log_info "Installing missing packages..."
        sudo apt-get update
        sudo apt-get install -y git curl python3 python3-pip python3-venv
    fi

    log_success "System requirements satisfied"
}

# Install PostgreSQL
install_postgresql() {
    log_info "Installing PostgreSQL..."

    if command -v psql &> /dev/null; then
        log_success "PostgreSQL already installed"
    else
        sudo apt-get update
        sudo apt-get install -y postgresql postgresql-contrib libpq-dev
        sudo systemctl enable postgresql
        sudo systemctl start postgresql
        log_success "PostgreSQL installed"
    fi

    # Create database and user
    log_info "Setting up Tau database..."
    sudo -u postgres psql -c "CREATE USER tau_daemon WITH PASSWORD 'tau_dev_password';" 2>/dev/null || true
    sudo -u postgres psql -c "CREATE DATABASE tau_lighting OWNER tau_daemon;" 2>/dev/null || true
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE tau_lighting TO tau_daemon;" 2>/dev/null || true
    log_success "Database configured"
}

# Install Node.js (for frontend)
install_nodejs() {
    if [[ "$INSTALL_FRONTEND" != "true" ]]; then
        log_info "Skipping Node.js installation (--no-frontend)"
        return
    fi

    log_info "Installing Node.js..."

    if command -v node &> /dev/null; then
        NODE_VERSION=$(node --version)
        log_success "Node.js already installed: $NODE_VERSION"
    else
        # Install Node.js 20 LTS
        curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
        sudo apt-get install -y nodejs
        log_success "Node.js installed: $(node --version)"
    fi
}

# Install GPIO libraries
install_gpio_libs() {
    if [[ "$USE_GPIO" != "true" ]]; then
        log_info "Skipping GPIO libraries (not using GPIO)"
        return
    fi

    log_info "Installing GPIO libraries..."

    # Install pigpio for hardware PWM
    if ! command -v pigpiod &> /dev/null; then
        sudo apt-get install -y pigpio python3-pigpio
        log_success "pigpio installed"
    else
        log_success "pigpio already installed"
    fi

    # Enable and start pigpiod service
    sudo systemctl enable pigpiod
    sudo systemctl start pigpiod || true
    log_success "pigpiod service enabled"

    # Install Python GPIO libraries (will be installed in venv)
    log_info "GPIO Python libraries will be installed in virtual environment"
}

# Install LabJack libraries
install_labjack_libs() {
    if [[ "$USE_LABJACK" != "true" ]]; then
        log_info "Skipping LabJack libraries (not using LabJack)"
        return
    fi

    log_info "Installing LabJack libraries..."

    # Install LabJack Exodriver
    if ! ldconfig -p | grep -q liblabjackusb; then
        log_info "Installing LabJack Exodriver..."
        cd /tmp
        git clone https://github.com/labjack/exodriver.git
        cd exodriver
        sudo ./install.sh
        cd -
        rm -rf /tmp/exodriver
        log_success "LabJack Exodriver installed"
    else
        log_success "LabJack Exodriver already installed"
    fi
}

# Clone or update repository
clone_repo() {
    log_info "Setting up Tau repository..."

    if [[ -d "$TAU_DIR/.git" ]]; then
        log_info "Updating existing repository..."
        cd "$TAU_DIR"
        git fetch origin
        git checkout "$TAU_BRANCH"
        git pull origin "$TAU_BRANCH"
        log_success "Repository updated"
    else
        log_info "Cloning repository..."
        git clone -b "$TAU_BRANCH" "$TAU_REPO" "$TAU_DIR"
        log_success "Repository cloned to $TAU_DIR"
    fi

    cd "$TAU_DIR"
}

# Setup Python virtual environment
setup_python_env() {
    log_info "Setting up Python virtual environment..."

    cd "$TAU_DIR/daemon"

    # Create virtual environment if it doesn't exist
    if [[ ! -d "venv" ]]; then
        python3 -m venv venv
        log_success "Virtual environment created"
    fi

    # Activate virtual environment
    source venv/bin/activate

    # Upgrade pip
    pip install --upgrade pip

    # Install requirements
    log_info "Installing Python dependencies..."
    pip install -r requirements.txt

    # Install GPIO libraries if using GPIO
    if [[ "$USE_GPIO" == "true" ]]; then
        pip install gpiozero pigpio RPi.GPIO
        log_success "GPIO Python libraries installed"
    fi

    # Install package in development mode
    pip install -e .

    log_success "Python environment configured"
}

# Setup frontend
setup_frontend() {
    if [[ "$INSTALL_FRONTEND" != "true" ]]; then
        log_info "Skipping frontend setup (--no-frontend)"
        return
    fi

    log_info "Setting up frontend..."

    cd "$TAU_DIR/frontend"

    # Install dependencies
    npm install

    # Build for production
    npm run build

    log_success "Frontend configured"
}

# Create environment file
create_env_file() {
    log_info "Creating environment configuration..."

    cd "$TAU_DIR"

    # Get Pi's IP address
    PI_IP=$(hostname -I | awk '{print $1}')

    cat > .env << EOF
# Tau Lighting Control System - Raspberry Pi Configuration
# Generated by pi-setup.sh on $(date)

# Database Configuration
POSTGRES_DB=tau_lighting
POSTGRES_USER=tau_daemon
POSTGRES_PASSWORD=tau_dev_password
POSTGRES_PORT=5432
DATABASE_URL=postgresql://tau_daemon:tau_dev_password@localhost:5432/tau_lighting

# Daemon Configuration
DAEMON_PORT=8000
DAEMON_HOST=0.0.0.0
LOG_LEVEL=INFO

# Hardware Configuration
LABJACK_MOCK=false
OLA_MOCK=true

# Raspberry Pi GPIO Configuration
USE_GPIO=$USE_GPIO
GPIO_USE_PIGPIO=true
GPIO_PULL_UP=true
# Custom pin mappings (optional, uses defaults if not set)
# GPIO_INPUT_PINS=0:17,1:27,2:22,3:23,4:24,5:25
# GPIO_PWM_PINS=0:12,1:13

# Frontend Configuration
NODE_ENV=production
FRONTEND_PORT=3000
NEXT_PUBLIC_API_URL=http://${PI_IP}:8000
NEXT_PUBLIC_WS_URL=ws://${PI_IP}:8000

# CORS - Allow access from local network
CORS_ALLOW_ALL=true
EOF

    log_success "Environment file created"
    log_info "Pi IP address: $PI_IP"
}

# Initialize database schema
init_database() {
    log_info "Initializing database schema..."

    cd "$TAU_DIR/daemon"
    source venv/bin/activate

    # Run database initialization SQL
    if [[ -f "$TAU_DIR/database/init.sql" ]]; then
        PGPASSWORD=tau_dev_password psql -h localhost -U tau_daemon -d tau_lighting -f "$TAU_DIR/database/init.sql"
        log_success "Database schema initialized"
    fi

    # Run any seeds if available
    if [[ -d "$TAU_DIR/database/seeds" ]]; then
        for seed in "$TAU_DIR/database/seeds"/*.sql; do
            if [[ -f "$seed" ]]; then
                PGPASSWORD=tau_dev_password psql -h localhost -U tau_daemon -d tau_lighting -f "$seed"
            fi
        done
        log_success "Database seeds applied"
    fi
}

# Create systemd service
create_systemd_service() {
    log_info "Creating systemd service..."

    # Create daemon service
    sudo tee /etc/systemd/system/tau-daemon.service > /dev/null << EOF
[Unit]
Description=Tau Lighting Control Daemon
After=network.target postgresql.service pigpiod.service
Requires=postgresql.service
Wants=pigpiod.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$TAU_DIR/daemon
Environment="PATH=$TAU_DIR/daemon/venv/bin"
EnvironmentFile=$TAU_DIR/.env
ExecStart=$TAU_DIR/daemon/venv/bin/python -m tau.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    if [[ "$INSTALL_FRONTEND" == "true" ]]; then
        # Create frontend service
        sudo tee /etc/systemd/system/tau-frontend.service > /dev/null << EOF
[Unit]
Description=Tau Lighting Control Frontend
After=network.target tau-daemon.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$TAU_DIR/frontend
EnvironmentFile=$TAU_DIR/.env
ExecStart=/usr/bin/npm start
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    fi

    # Reload systemd
    sudo systemctl daemon-reload

    log_success "Systemd services created"
}

# Start services
start_services() {
    log_info "Starting Tau services..."

    sudo systemctl enable tau-daemon
    sudo systemctl start tau-daemon
    log_success "Tau daemon started"

    if [[ "$INSTALL_FRONTEND" == "true" ]]; then
        sudo systemctl enable tau-frontend
        sudo systemctl start tau-frontend
        log_success "Tau frontend started"
    fi

    # Wait for services to start
    sleep 3

    # Check status
    if systemctl is-active --quiet tau-daemon; then
        log_success "Tau daemon is running"
    else
        log_error "Tau daemon failed to start"
        sudo journalctl -u tau-daemon -n 20 --no-pager
    fi
}

# Print access information
print_info() {
    PI_IP=$(hostname -I | awk '{print $1}')

    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Tau Lighting Control System${NC}"
    echo -e "${GREEN}  Installation Complete!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo -e "Access the web interface at:"
    echo -e "  ${BLUE}http://${PI_IP}:3000${NC}"
    echo ""
    echo -e "API endpoint:"
    echo -e "  ${BLUE}http://${PI_IP}:8000${NC}"
    echo ""
    echo -e "API documentation:"
    echo -e "  ${BLUE}http://${PI_IP}:8000/docs${NC}"
    echo ""
    echo -e "Manage services:"
    echo -e "  ${YELLOW}sudo systemctl status tau-daemon${NC}"
    echo -e "  ${YELLOW}sudo systemctl status tau-frontend${NC}"
    echo -e "  ${YELLOW}sudo journalctl -u tau-daemon -f${NC}"
    echo ""
    echo -e "Configuration file:"
    echo -e "  ${YELLOW}$TAU_DIR/.env${NC}"
    echo ""

    if [[ "$USE_GPIO" == "true" ]]; then
        echo -e "GPIO Configuration:"
        echo -e "  Input pins (default): GPIO 17, 27, 22, 23, 24, 25, 5, 6"
        echo -e "  PWM pins (default): GPIO 12, 13"
        echo -e "  Edit GPIO_INPUT_PINS and GPIO_PWM_PINS in .env to customize"
        echo ""
    fi
}

# Main installation flow
main() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  Tau Lighting Control System${NC}"
    echo -e "${BLUE}  Raspberry Pi Setup${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""

    check_pi
    check_requirements
    install_postgresql
    install_nodejs
    install_gpio_libs
    install_labjack_libs
    clone_repo
    setup_python_env
    setup_frontend
    create_env_file
    init_database
    create_systemd_service
    start_services
    print_info
}

# Run main function
main "$@"
