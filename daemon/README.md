# Tau Lighting Control Daemon

The Python control daemon for the Tau smart lighting system. Handles real-time hardware I/O, state management, and provides a REST API for the web interface.

## Architecture

```
daemon/
├── src/tau/              # Main application code
│   ├── __init__.py
│   ├── main.py           # Entry point
│   ├── config.py         # Configuration management
│   ├── database.py       # Database connection and ORM
│   ├── api/              # FastAPI REST API
│   ├── hardware/         # Hardware interfaces (LabJack, OLA)
│   ├── control/          # Control loop and state machine
│   ├── lighting/         # Lighting algorithms (circadian, mixing, etc.)
│   └── models/           # SQLAlchemy ORM models
├── tests/                # Test suite
├── config/               # Configuration files
├── requirements.txt      # Python dependencies
├── pyproject.toml        # Project configuration
└── Dockerfile            # Container image definition
```

## Development Setup

### Local Development (without Docker)

1. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
pip install -e .
```

3. Set up environment variables:
```bash
cp ../.env.example ../.env
# Edit .env with your configuration
```

4. Run the daemon:
```bash
python -m tau.main
```

### Docker Development

```bash
# From project root
docker-compose up daemon
```

## Configuration

Configuration is managed via environment variables. See `.env.example` for available options.

Key settings:
- `DATABASE_URL`: PostgreSQL connection string
- `LABJACK_MOCK`: Set to `true` for development without hardware
- `OLA_MOCK`: Set to `true` for development without DMX hardware
- `LOG_LEVEL`: Logging verbosity (DEBUG, INFO, WARNING, ERROR)

## Testing

```bash
pytest
pytest --cov=tau  # With coverage report
```

## Hardware Requirements

### Production (Linux NUC)
- LabJack U3-HV for switch inputs
- USB-to-DMX adapter with OLA support
- USB access for device communication

### Development
Set `LABJACK_MOCK=true` and `OLA_MOCK=true` to use simulated hardware interfaces.

## API Documentation

When running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Code Style

- **Formatter**: Black (line length: 100)
- **Import sorting**: isort
- **Linting**: flake8
- **Type checking**: mypy

Run formatters:
```bash
black src/ tests/
isort src/ tests/
flake8 src/ tests/
mypy src/
```
