-- Tau Lighting Control System - Database Initialization Script
-- PostgreSQL 15+

-- Create database (run as superuser if needed)
-- CREATE DATABASE tau_lighting;

-- Connect to the database
-- \c tau_lighting;

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

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

    -- Dim-to-Warm Configuration
    dim_to_warm_enabled BOOLEAN DEFAULT FALSE,
    dim_to_warm_max_cct INT,  -- CCT at 100% brightness (Kelvin). Overrides system default.
    dim_to_warm_min_cct INT,  -- CCT at minimum brightness (Kelvin). Overrides system default.

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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


-- GROUPS (LOGICAL)
-- Groups can contain fixtures or other groups (nesting).
CREATE TABLE groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT,

    -- Circadian Configuration
    circadian_enabled BOOLEAN DEFAULT FALSE,
    circadian_profile_id INT, -- FK to a profiles table (defined later)

    -- Dim-to-Warm Configuration
    dim_to_warm_enabled BOOLEAN DEFAULT FALSE,
    dim_to_warm_max_cct INT,  -- CCT at 100% brightness (Kelvin). Overrides system default.
    dim_to_warm_min_cct INT,  -- CCT at minimum brightness (Kelvin). Overrides system default.

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

-- SWITCHES (PHYSICAL INPUTS)
-- Physical switch/dimmer devices that control fixtures or groups
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

    -- Optional photo for UI
    photo_url TEXT,

    CONSTRAINT one_target_only CHECK (
        (target_group_id IS NOT NULL AND target_fixture_id IS NULL) OR
        (target_group_id IS NULL AND target_fixture_id IS NOT NULL)
    )
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

-- SCENES
-- Scenes capture static values for recall.
CREATE TABLE scenes (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,

    -- Scope: Does this scene belong to a specific group? (Optional)
    scope_group_id INT REFERENCES groups(id) ON DELETE CASCADE
);

-- Stores the actual values for lights in a scene
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

    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tracks logical state of groups (e.g. is Circadian suspended?)
CREATE TABLE group_state (
    group_id INT PRIMARY KEY REFERENCES groups(id) ON DELETE CASCADE,

    circadian_suspended BOOLEAN DEFAULT FALSE,
    circadian_suspended_at TIMESTAMP,

    last_active_scene_id INT REFERENCES scenes(id)
);

-- SYSTEM SETTINGS (Singleton)
-- Global configuration for the lighting system (dim-to-warm defaults, etc.)
CREATE TABLE system_settings (
    id INT PRIMARY KEY DEFAULT 1,

    -- Dim-to-Warm Global Settings
    dim_to_warm_max_cct_kelvin INT NOT NULL DEFAULT 3000,  -- CCT at 100% brightness
    dim_to_warm_min_cct_kelvin INT NOT NULL DEFAULT 1800,  -- CCT at minimum brightness
    dim_to_warm_curve_exponent REAL NOT NULL DEFAULT 0.5,  -- Power curve (0.5 = incandescent-like)

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Ensure only one row exists
    CONSTRAINT system_settings_singleton CHECK (id = 1)
);

-- Add Foreign Key Constraint for circadian_profile_id after table creation
ALTER TABLE groups ADD CONSTRAINT fk_groups_circadian_profile
    FOREIGN KEY (circadian_profile_id) REFERENCES circadian_profiles(id) ON DELETE SET NULL;

-- Create Indexes for Performance
CREATE INDEX idx_fixtures_model_id ON fixtures(fixture_model_id);
CREATE INDEX idx_fixtures_dmx_channel ON fixtures(dmx_channel_start);

CREATE INDEX idx_switches_model_id ON switches(switch_model_id);
CREATE INDEX idx_switches_digital_pin ON switches(labjack_digital_pin);
CREATE INDEX idx_switches_analog_pin ON switches(labjack_analog_pin);
CREATE INDEX idx_switches_target_group ON switches(target_group_id);
CREATE INDEX idx_switches_target_fixture ON switches(target_fixture_id);

CREATE INDEX idx_group_fixtures_group ON group_fixtures(group_id);
CREATE INDEX idx_group_fixtures_fixture ON group_fixtures(fixture_id);

CREATE INDEX idx_group_hierarchy_parent ON group_hierarchy(parent_group_id);
CREATE INDEX idx_group_hierarchy_child ON group_hierarchy(child_group_id);

CREATE INDEX idx_groups_circadian_profile ON groups(circadian_profile_id);
CREATE INDEX idx_groups_circadian_enabled ON groups(circadian_enabled) WHERE circadian_enabled = TRUE;

CREATE INDEX idx_scenes_scope_group ON scenes(scope_group_id);
CREATE INDEX idx_scene_values_scene ON scene_values(scene_id);
CREATE INDEX idx_scene_values_fixture ON scene_values(fixture_id);

CREATE INDEX idx_fixture_state_is_on ON fixture_state(is_on) WHERE is_on = TRUE;
CREATE INDEX idx_fixture_state_last_updated ON fixture_state(last_updated);

CREATE INDEX idx_group_state_circadian_suspended ON group_state(circadian_suspended) WHERE circadian_suspended = TRUE;

-- Dim-to-warm indexes
CREATE INDEX idx_fixtures_dim_to_warm_enabled ON fixtures(dim_to_warm_enabled) WHERE dim_to_warm_enabled = TRUE;
CREATE INDEX idx_groups_dim_to_warm_enabled ON groups(dim_to_warm_enabled) WHERE dim_to_warm_enabled = TRUE;

-- Insert default system settings
INSERT INTO system_settings (id, dim_to_warm_max_cct_kelvin, dim_to_warm_min_cct_kelvin, dim_to_warm_curve_exponent)
VALUES (1, 3000, 1800, 0.5)
ON CONFLICT (id) DO NOTHING;

-- Insert Default Circadian Profiles
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

-- Create a view for easy querying of fixture status with model info
CREATE VIEW v_fixture_status AS
SELECT
    f.id,
    f.name,
    fm.manufacturer,
    fm.model,
    fm.type,
    f.dmx_channel_start,
    fm.dmx_footprint,
    COALESCE(fs.current_brightness, 0) as current_brightness,
    COALESCE(fs.current_cct, 2700) as current_cct,
    COALESCE(fs.is_on, false) as is_on,
    fs.last_updated
FROM fixtures f
INNER JOIN fixture_models fm ON f.fixture_model_id = fm.id
LEFT JOIN fixture_state fs ON f.id = fs.fixture_id;

-- Create a view for group membership (including nested groups)
CREATE VIEW v_group_membership AS
WITH RECURSIVE group_tree AS (
    -- Base case: direct fixture memberships
    SELECT
        gf.group_id,
        gf.fixture_id,
        1 as depth
    FROM group_fixtures gf

    UNION ALL

    -- Recursive case: fixtures from child groups
    SELECT
        gh.parent_group_id as group_id,
        gt.fixture_id,
        gt.depth + 1
    FROM group_tree gt
    INNER JOIN group_hierarchy gh ON gt.group_id = gh.child_group_id
    WHERE gt.depth < 4  -- Limit nesting depth as per spec
)
SELECT DISTINCT
    g.id as group_id,
    g.name as group_name,
    gt.fixture_id,
    f.name as fixture_name,
    gt.depth
FROM group_tree gt
INNER JOIN groups g ON gt.group_id = g.id
INNER JOIN fixtures f ON gt.fixture_id = f.fixture_id
ORDER BY g.id, gt.depth, f.name;

-- Grant permissions (adjust as needed for your deployment)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO tau_daemon;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO tau_daemon;
