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

    mixing_type VARCHAR(20) NOT NULL CHECK (mixing_type IN ('linear', 'perceptual', 'logarithmic', 'custom')),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(manufacturer, model)
);

CREATE TABLE fixtures (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    fixture_model_id INT NOT NULL REFERENCES fixture_models(id) ON DELETE RESTRICT,
    dmx_channel_start INT NOT NULL UNIQUE, 
    
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
    dimming_curve VARCHAR(20) DEFAULT 'logarithmic',
    
    requires_digital_pin BOOLEAN DEFAULT TRUE,
    requires_analog_pin BOOLEAN DEFAULT FALSE,
    
    UNIQUE(manufacturer, model)
);

CREATE TABLE switches (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    switch_model_id INT NOT NULL REFERENCES switch_models(id) ON DELETE RESTRICT,
    
    -- Hardware Mapping
    labjack_digital_pin INT,
    labjack_analog_pin INT,
    
    -- Polymorphic Target
    target_group_id INT REFERENCES groups(id) ON DELETE SET NULL,
    target_fixture_id INT REFERENCES fixtures(id) ON DELETE SET NULL,
    
    CONSTRAINT one_target_only CHECK (
        (target_group_id IS NOT NULL AND target_fixture_id IS NULL) OR
        (target_group_id IS NULL AND target_fixture_id IS NOT NULL)
    )
    -- No overrides here.
);


-- GROUPS (LOGICAL)
-- Groups can contain fixtures or other groups (nesting).
CREATE TABLE groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    
    -- Circadian Configuration [cite: 144]
    circadian_enabled BOOLEAN DEFAULT FALSE,
    circadian_profile_id INT, -- FK to a profiles table (defined later)
    
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
    -- Schema: [ {"time": "07:00", "brightness": 80, "cct": 5500}, ... ]
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
        {"time": "08:00", "brightness": 90, "cct": 4000},
        {"time": "18:00", "brightness": 90, "cct": 3000},
        {"time": "20:00", "brightness": 40, "cct": 2700},
        {"time": "23:00", "brightness": 0, "cct": 2200}
    ]'::jsonb
),
(
    'Bedroom', 
    'Lower intensity, aggressive warm shift in evening.',
    '[
        {"time": "07:00", "brightness": 0, "cct": 2700},
        {"time": "09:00", "brightness": 70, "cct": 4000},
        {"time": "19:00", "brightness": 50, "cct": 2700},
        {"time": "21:00", "brightness": 10, "cct": 2200}
    ]'::jsonb
);

-- SCENES
-- Scenes capture static values for recall.
CREATE TABLE scenes (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    
    -- Scope: Does this scene belong to a specific group? (Optional)
    scope_group_id INT REFERENCES groups(id) ON DELETE CASCADE
);

-- Stores the actual values for lights in a scene [cite: 129-131]
CREATE TABLE scene_values (
    scene_id INT REFERENCES scenes(id) ON DELETE CASCADE,
    
    -- The target of this specific value (Fixture or Group)
    fixture_id INT REFERENCES fixtures(id) ON DELETE CASCADE,
    
    target_brightness_percent INT CHECK (target_brightness_percent BETWEEN 0 AND 100),
    target_cct_kelvin INT,
    
    PRIMARY KEY (scene_id, fixture_id)
);

-- RUNTIME STATE (PERSISTENCE)
-- This table is the "Source of Truth" for reboot recovery.
-- Updated on every change, read on startup.
CREATE TABLE fixture_state (
    fixture_id INT PRIMARY KEY REFERENCES fixtures(id) ON DELETE CASCADE,
    
    current_brightness INT DEFAULT 0,
    current_cct INT DEFAULT 2700,
    is_on BOOLEAN DEFAULT FALSE,
    
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tracks logical state of groups (e.g. is Circadian suspended?) [cite: 150]
CREATE TABLE group_state (
    group_id INT PRIMARY KEY REFERENCES groups(id) ON DELETE CASCADE,
    
    circadian_suspended BOOLEAN DEFAULT FALSE,
    circadian_suspended_at TIMESTAMP,
    
    last_active_scene_id INT REFERENCES scenes(id)
);