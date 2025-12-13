# Tau Lighting Control - Example Configurations

This directory contains example configurations for the Tau lighting control system.

## Files

- `example_config.yaml` - Complete example configuration with fixtures, groups, scenes, and switches

## Configuration Structure

The example configuration demonstrates:

1. **Fixture Models** - Definitions of physical fixture types
   - Simple dimmable LEDs
   - Tunable white fixtures
   - Professional theatrical fixtures

2. **Fixtures** - Individual fixture instances
   - DMX channel assignments
   - Model references
   - Human-readable names

3. **Groups** - Logical groupings of fixtures
   - Room-based organization
   - Circadian profile assignments
   - Fixture memberships

4. **Circadian Profiles** - Time-based lighting curves
   - Standard Home (natural daylight)
   - Sleep Optimized (reduced blue light)
   - Work Focus (high CCT for alertness)

5. **Scenes** - Preset lighting configurations
   - Movie Time (dim warm)
   - Entertaining (bright inviting)
   - Reading Mode (focused bright)
   - Goodnight (all off)

6. **Switch Models** - Physical switch specifications
   - Retractive switches (momentary buttons)
   - Rotary dimmers (potentiometers)

7. **Switches** - Physical input device instances
   - LabJack pin assignments
   - Target fixture or group assignments

## Loading Configuration

To load the example configuration into your database:

```bash
# From the daemon directory
python scripts/load_example_config.py

# Or specify a custom config file
python scripts/load_example_config.py path/to/config.yaml
```

**Prerequisites:**
- PostgreSQL database running
- Database URL configured in `.env`
- Alembic migrations applied

```bash
# Apply migrations
alembic upgrade head
```

## Creating Custom Configurations

1. Copy `example_config.yaml` to a new file
2. Modify fixture models, fixtures, groups, etc.
3. Load with: `python scripts/load_example_config.py your_config.yaml`

## Configuration Values

### Brightness
- Database/API: 0-1000 (integer)
- State Manager: 0.0-1.0 (float)

### Color Temperature (CCT)
- Range: 1000-10000 Kelvin
- Typical: 2000-6500K
- Warm: 2000-3000K
- Cool: 4000-6500K

### DMX Channels
- Range: 1-512 per universe
- Must not overlap for fixtures

### LabJack Pins
- Digital: 0-15
- Analog: 0-15 (0-2.4V input range)

## Example Use Cases

### Home Setup
The example configuration demonstrates a typical home installation:
- Living room with circadian-controlled ceiling lights
- Kitchen with task lighting (no circadian)
- Bedroom with sleep-optimized circadian
- Office with work-focused circadian
- Scenes for different activities (movie, entertaining, reading)
- Physical switches for manual control

### Extending the Configuration

**Add a new fixture:**
```yaml
fixtures:
  - name: "New Light"
    model: "Phillips Hue White Ambiance"
    dmx_channel_start: 40
```

**Add a new scene:**
```yaml
scenes:
  - name: "Dinner Party"
    scope_group: "Kitchen"
    values:
      - fixture: "Kitchen Counter LEDs"
        brightness: 600  # 60%
        cct: 2700
```

**Add a new group:**
```yaml
groups:
  - name: "Bathroom"
    description: "Bathroom fixtures"
    circadian_enabled: false
    fixtures:
      - "Bathroom Vanity"
      - "Bathroom Shower"
```

## API Alternative

You can also populate the database via the REST API:

```bash
# Create a fixture model
curl -X POST http://localhost:8000/api/fixtures/models \
  -H "Content-Type: application/json" \
  -d '{
    "manufacturer": "Generic",
    "model": "LED Strip",
    "type": "simple_dimmable",
    "dmx_footprint": 1
  }'

# Create a fixture
curl -X POST http://localhost:8000/api/fixtures \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Kitchen LEDs",
    "fixture_model_id": 1,
    "dmx_channel_start": 1
  }'
```

## Validation

After loading configuration, verify via API:

```bash
# List all fixtures
curl http://localhost:8000/api/fixtures/

# List all groups
curl http://localhost:8000/api/groups/

# List all scenes
curl http://localhost:8000/api/scenes/

# Check system status
curl http://localhost:8000/status
```

## Troubleshooting

**Database connection error:**
- Check PostgreSQL is running
- Verify DATABASE_URL in `.env`
- Ensure database exists: `createdb tau_lighting`

**DMX channel conflict:**
- Check for overlapping channel assignments
- Ensure fixtures don't exceed channel range (1-512)

**Circadian profile not working:**
- Verify profile has at least 2 keyframes
- Check group has profile assigned
- Ensure circadian_enabled is true

**Switch not responding:**
- Verify LabJack pin assignments
- Check switch model requirements (digital/analog)
- Ensure target (group/fixture) exists
