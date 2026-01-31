-- Devices
CREATE TABLE fixture_models (
    id SERIAL PRIMARY KEY,
    manufacturer VARCHAR(100) NOT NULL,
    model VARCHAR(100) NOT NULL,
    description TEXT,
    type VARCHAR(20) NOT NULL CHECK (type IN ('simple_dimmable', 'tunable_white', 'dim_to_warm', 'non_dimmable', 'other')),

    -- DMX Footprint (Required for collision detection)
    dmx_footprint INT NOT NULL DEFAULT 1,

    -- CCT Limits
    cct_min_kelvin INT DEFAULT 1800,
    cct_max_kelvin INT DEFAULT 4000,

    -- Planckian Locus Color Mixing Parameters (for tunable_white fixtures)
    -- CIE 1931 xy chromaticity coordinates for warm LED
    warm_xy_x FLOAT,
    warm_xy_y FLOAT,
    -- CIE 1931 xy chromaticity coordinates for cool LED
    cool_xy_x FLOAT,
    cool_xy_y FLOAT,
    -- Luminous flux at 100% for each channel
    warm_lumens INT,
    cool_lumens INT,
    -- PWM-to-light gamma correction (default 2.2)
    gamma FLOAT DEFAULT 2.2,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(manufacturer, model)
);

CREATE TABLE fixtures (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    fixture_model_id INT NOT NULL REFERENCES fixture_models(id) ON DELETE RESTRICT,
    dmx_channel_start INT NOT NULL UNIQUE,
    -- Secondary DMX channel for merged tunable white fixtures (warm+cool on separate channels)
    secondary_dmx_channel INT UNIQUE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    -- No overrides here. The model dictates behavior.
);

CREATE TABLE switch_models (
    id SERIAL PRIMARY KEY,
    manufacturer VARCHAR(100) NOT NULL,
    model VARCHAR(100) NOT NULL,
    
    input_type VARCHAR(50) NOT NULL CHECK (input_type IN ('retractive', 'rotary_abs', 'paddle_composite', 'switch_simple')),
    
    -- Hardware Debounce & Curve (Locked to Model)
    debounce_ms INT DEFAULT 500,
    dimming_curve VARCHAR(20) DEFAULT 'logarithmic' CHECK (dimming_curve IN ('linear', 'logarithmic')),
    
    requires_digital_pin BOOLEAN DEFAULT TRUE,
    requires_analog_pin BOOLEAN DEFAULT FALSE,
    
    UNIQUE(manufacturer, model)
);

CREATE TABLE switches (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    switch_model_id INT NOT NULL REFERENCES switch_models(id) ON DELETE RESTRICT,

    -- Input Source: 'labjack' or 'gpio'
    input_source VARCHAR(20) NOT NULL DEFAULT 'labjack'
        CHECK (input_source IN ('labjack', 'gpio')),

    -- Hardware Mapping (LabJack) - used when input_source='labjack'
    labjack_digital_pin INT,
    labjack_analog_pin INT,

    -- Hardware Mapping (GPIO) - used when input_source='gpio'
    -- BCM pin number (e.g., 17, 22, 27)
    gpio_bcm_pin INT,
    -- Pull resistor configuration: 'up' or 'down'
    gpio_pull VARCHAR(10) DEFAULT 'up' CHECK (gpio_pull IN ('up', 'down') OR gpio_pull IS NULL),

    -- Switch hardware configuration
    switch_type VARCHAR(20) NOT NULL DEFAULT 'normally-closed'
        CHECK (switch_type IN ('normally-open', 'normally-closed')),
    invert_reading BOOLEAN NOT NULL DEFAULT FALSE,

    -- Polymorphic Target
    target_group_id INT REFERENCES groups(id) ON DELETE SET NULL,
    target_fixture_id INT REFERENCES fixtures(id) ON DELETE SET NULL,

    -- Double-tap scene recall (optional)
    double_tap_scene_id INT,

    -- Optional photo for UI
    photo_url TEXT,

    CONSTRAINT one_target_only CHECK (
        (target_group_id IS NOT NULL AND target_fixture_id IS NULL) OR
        (target_group_id IS NULL AND target_fixture_id IS NOT NULL)
    ),

    -- GPIO pin validation: required when input_source is 'gpio', must be valid BCM pin
    CONSTRAINT gpio_pin_valid CHECK (
        (input_source = 'labjack') OR
        (input_source = 'gpio' AND gpio_bcm_pin IS NOT NULL AND
         gpio_bcm_pin IN (4, 5, 6, 12, 13, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27))
    )
);

-- Partial unique index to ensure GPIO pins are unique (prevents race conditions at DB level)
CREATE UNIQUE INDEX switches_gpio_bcm_pin_unique
ON switches (gpio_bcm_pin)
WHERE input_source = 'gpio' AND gpio_bcm_pin IS NOT NULL;


-- GROUPS (LOGICAL)
-- Groups can contain fixtures or other groups (nesting).
CREATE TABLE groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,

    -- Reserved for future system-managed groups
    is_system BOOLEAN DEFAULT FALSE,

    -- Circadian Configuration [cite: 144]
    circadian_enabled BOOLEAN DEFAULT FALSE,
    circadian_profile_id INT, -- FK to a profiles table (defined later)

    -- Default settings when switch turns on the group
    default_max_brightness INT DEFAULT 1000 CHECK (default_max_brightness BETWEEN 0 AND 1000),
    default_cct_kelvin INT CHECK (default_cct_kelvin BETWEEN 1000 AND 10000),

    -- Display order for UI sorting (null = sort by name)
    display_order INT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Link Fixtures to Groups (Many-to-Many allowed)
CREATE TABLE group_fixtures (
    group_id INT REFERENCES groups(id) ON DELETE CASCADE,
    fixture_id INT REFERENCES fixtures(id) ON DELETE CASCADE,
    PRIMARY KEY (group_id, fixture_id)
);

-- Link Groups to Parent Groups (Nesting) 
CREATE TABLE group_hierarchy (
    parent_group_id INT REFERENCES groups(id) ON DELETE CASCADE,
    child_group_id INT REFERENCES groups(id) ON DELETE CASCADE,
    PRIMARY KEY (parent_group_id, child_group_id),
    CHECK (parent_group_id != child_group_id) -- Prevent self-parenting
);


-- CIRCADIAN PROFILES
-- Defines the shape of the day for different room types
CREATE TABLE circadian_profiles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE, -- e.g., "Living Room Default", "Bedroom Kids"
    description TEXT,
    
    -- Curve Data: Stored as JSON to allow flexible number of points.
    -- Schema: [ {"time": "07:00", "brightness": 800, "cct": 5500}, ... ]
    -- Note: brightness is 0-1000 (tenths of a percent, e.g., 800 = 80.0%)
    curve_points JSONB NOT NULL,
    
    -- Interpolation Method: How to calculate values between points
    interpolation_type VARCHAR(20) DEFAULT 'linear' CHECK (interpolation_type IN ('linear', 'cosine', 'step')),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert Default Profiles (Example Data based on Guidelines)
INSERT INTO circadian_profiles (name, description, curve_points) VALUES 
(
    'Standard Day', 
    'Bright day, warm evening. Good for Living Rooms.',
    '[
        {"time": "06:00", "brightness": 0, "cct": 2700},
        {"time": "08:00", "brightness": 900, "cct": 4000},
        {"time": "18:00", "brightness": 900, "cct": 3000},
        {"time": "20:00", "brightness": 400, "cct": 2700},
        {"time": "23:00", "brightness": 0, "cct": 2200}
    ]'::jsonb
),
(
    'Bedroom', 
    'Lower intensity, aggressive warm shift in evening.',
    '[
        {"time": "07:00", "brightness": 0, "cct": 2700},
        {"time": "09:00", "brightness": 700, "cct": 4000},
        {"time": "19:00", "brightness": 500, "cct": 2700},
        {"time": "21:00", "brightness": 100, "cct": 2200}
    ]'::jsonb
);

-- SCENES
-- Scenes capture static values for recall.
CREATE TABLE scenes (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,

    -- Scope: Does this scene belong to a specific group? (Optional)
    scope_group_id INT REFERENCES groups(id) ON DELETE CASCADE,

    -- Scene type: 'toggle' or 'idempotent'
    -- toggle: activating again turns off fixtures if at scene level
    -- idempotent: always sets fixtures to scene level
    scene_type VARCHAR(20) NOT NULL DEFAULT 'idempotent'
        CHECK (scene_type IN ('toggle', 'idempotent')),

    -- Display order for UI sorting (null = sort by name)
    display_order INT
);

-- Stores the actual values for lights in a scene [cite: 129-131]
CREATE TABLE scene_values (
    scene_id INT REFERENCES scenes(id) ON DELETE CASCADE,
    
    -- The target of this specific value (Fixture or Group)
    fixture_id INT REFERENCES fixtures(id) ON DELETE CASCADE,
    
    target_brightness INT CHECK (target_brightness BETWEEN 0 AND 1000), -- 0-1000 (tenths of a percent)
    target_cct_kelvin INT,
    
    PRIMARY KEY (scene_id, fixture_id)
);

-- RUNTIME STATE (PERSISTENCE)
-- This table is the "Source of Truth" for reboot recovery.
-- Updated on every change, read on startup.
CREATE TABLE fixture_state (
    fixture_id INT PRIMARY KEY REFERENCES fixtures(id) ON DELETE CASCADE,

    current_brightness INT DEFAULT 0 CHECK (current_brightness BETWEEN 0 AND 1000), -- 0-1000 (tenths of a percent)
    current_cct INT DEFAULT 2700,
    is_on BOOLEAN DEFAULT FALSE,

    -- Override state (bypasses group/circadian control)
    override_active BOOLEAN DEFAULT FALSE,
    override_expires_at TIMESTAMP,
    override_source VARCHAR(20), -- 'fixture' or 'group'

    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tracks logical state of groups (e.g. is Circadian suspended?) [cite: 150]
CREATE TABLE group_state (
    group_id INT PRIMARY KEY REFERENCES groups(id) ON DELETE CASCADE,

    circadian_suspended BOOLEAN DEFAULT FALSE,
    circadian_suspended_at TIMESTAMP,

    last_active_scene_id INT REFERENCES scenes(id)
);

-- SYSTEM SETTINGS
-- Global configuration values stored in database for runtime modification
CREATE TABLE system_settings (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) NOT NULL UNIQUE,
    value TEXT NOT NULL,
    description TEXT,
    value_type VARCHAR(20) NOT NULL DEFAULT 'str' CHECK (value_type IN ('int', 'float', 'bool', 'str'))
);

-- Insert default system settings
INSERT INTO system_settings (key, value, description, value_type) VALUES
(
    'dim_speed_ms',
    '2000',
    'Time in milliseconds for a full 0-100% brightness transition when dimming',
    'int'
),
(
    'tap_window_ms',
    '500',
    'Time window in milliseconds to detect double-tap on switches (200-900ms). Lower = faster toggle, less time for double-tap.',
    'int'
),
(
    'street_address',
    '',
    'Street address for home location display in header',
    'str'
);
