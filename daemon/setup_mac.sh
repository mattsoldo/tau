#!/bin/bash
# Setup script for Tau Lighting Control System on macOS
# Tested on macOS Ventura/Sonoma and Mac mini

set -e

echo "======================================"
echo "Tau Lighting System - macOS Setup"
echo "======================================"

# Check if running on macOS
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "Error: This script is for macOS only"
    exit 1
fi

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# 1. Install Homebrew if not present
if ! command_exists brew; then
    echo "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
else
    echo "✓ Homebrew already installed"
fi

# 2. Install PostgreSQL
if ! command_exists psql; then
    echo "Installing PostgreSQL..."
    brew install postgresql@15
    brew services start postgresql@15
    echo 'export PATH="/opt/homebrew/opt/postgresql@15/bin:$PATH"' >> ~/.zshrc
else
    echo "✓ PostgreSQL already installed"
fi

# 3. Install Python 3.12 via pyenv (recommended for Mac)
if ! command_exists pyenv; then
    echo "Installing pyenv..."
    brew install pyenv
    echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.zshrc
    echo 'command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.zshrc
    echo 'eval "$(pyenv init -)"' >> ~/.zshrc
    source ~/.zshrc
fi

# Install Python 3.12 if not present
if ! pyenv versions | grep -q "3.12"; then
    echo "Installing Python 3.12..."
    pyenv install 3.12.9
    pyenv local 3.12.9
else
    echo "✓ Python 3.12 already installed"
    pyenv local 3.12.9
fi

# 4. Install OLA (Open Lighting Architecture) - Optional
echo ""
echo "Do you want to install OLA for real DMX output? (y/n)"
read -r install_ola
if [[ "$install_ola" == "y" ]]; then
    if ! command_exists olad; then
        echo "Installing OLA..."
        brew install ola

        # Create OLA config directory
        mkdir -p ~/.olad

        echo "OLA installed. To start OLA daemon:"
        echo "  olad -c ~/.olad"
        echo "  Web interface: http://localhost:9090"
    else
        echo "✓ OLA already installed"
    fi
else
    echo "Skipping OLA installation (will use mock mode)"
fi

# 5. Install LabJack drivers - Optional
echo ""
echo "Do you want to install LabJack drivers? (y/n)"
read -r install_labjack
if [[ "$install_labjack" == "y" ]]; then
    echo "Downloading LabJack installer..."
    curl -O https://labjack.com/sites/default/files/software/LabJack-2023-11-13.dmg
    echo "Please open the downloaded DMG and install LabJack software"
    echo "Press Enter when installation is complete..."
    read -r
    rm -f LabJack-*.dmg
else
    echo "Skipping LabJack installation (will use mock mode)"
fi

# 6. Create Python virtual environment
echo ""
echo "Creating Python virtual environment..."
python3.12 -m venv venv
source venv/bin/activate

# 7. Install Python dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# 8. Setup PostgreSQL database
echo ""
echo "Setting up PostgreSQL database..."
createuser -s tau_daemon 2>/dev/null || echo "User already exists"
createdb tau_lighting 2>/dev/null || echo "Database already exists"

# Set password for tau_daemon user
psql -d tau_lighting -c "ALTER USER tau_daemon WITH PASSWORD 'tau_password';" 2>/dev/null

# 9. Run database migrations
echo "Running database migrations..."
export DATABASE_URL="postgresql://tau_daemon:tau_password@localhost/tau_lighting"
export PYTHONPATH="$PWD/src"
alembic upgrade head

# 10. Create environment file
echo "Creating .env file..."
cat > .env <<EOF
# Tau Lighting System - Environment Configuration
DATABASE_URL=postgresql://tau_daemon:tau_password@localhost/tau_lighting
PYTHONPATH=$PWD/src
LOG_LEVEL=INFO
CONTROL_LOOP_HZ=30

# Hardware Configuration (set to false for real hardware)
LABJACK_MOCK=true
OLA_MOCK=true

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=["http://localhost:3000", "http://localhost:8000"]
EOF

# 11. Load example configuration
echo ""
echo "Loading example configuration..."
python scripts/load_example_config.py

# 12. Create launch script
echo "Creating launch script..."
cat > start_tau.sh <<'EOF'
#!/bin/bash
# Start Tau Lighting System

# Activate virtual environment
source venv/bin/activate

# Load environment
source .env

# Start frontend server in background
echo "Starting frontend server..."
python -m http.server 3000 &
FRONTEND_PID=$!

# Start backend daemon
echo "Starting Tau daemon..."
python -m tau.main &
DAEMON_PID=$!

echo "======================================"
echo "Tau Lighting System Started"
echo "======================================"
echo "Frontend:    http://localhost:3000"
echo "API Docs:    http://localhost:8000/docs"
echo "======================================"
echo "Press Ctrl+C to stop"

# Wait and handle shutdown
trap "kill $FRONTEND_PID $DAEMON_PID 2>/dev/null; exit" INT
wait
EOF
chmod +x start_tau.sh

# 13. Create stop script
cat > stop_tau.sh <<'EOF'
#!/bin/bash
# Stop Tau Lighting System

echo "Stopping Tau services..."
pkill -f "python -m http.server 3000"
pkill -f "python -m tau.main"
echo "Services stopped"
EOF
chmod +x stop_tau.sh

echo ""
echo "======================================"
echo "✅ Setup Complete!"
echo "======================================"
echo ""
echo "To start the system:"
echo "  ./start_tau.sh"
echo ""
echo "To stop the system:"
echo "  ./stop_tau.sh"
echo ""
echo "To run in development mode:"
echo "  source venv/bin/activate"
echo "  source .env"
echo "  python -m tau.main"
echo ""
echo "======================================"