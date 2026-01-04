-- Migration 002: Add Dim-to-Warm Support
-- This migration adds dim-to-warm functionality for mimicking incandescent light behavior

-- ============================================================================
-- 1. Create system_settings table for global configuration
-- ============================================================================

CREATE TABLE IF NOT EXISTS system_settings (
    id INT PRIMARY KEY DEFAULT 1,

    -- Dim-to-Warm Global Settings
    -- Default CCT at 100% brightness (Kelvin) - lower of this or fixture max
    dim_to_warm_max_cct_kelvin INT NOT NULL DEFAULT 3000,
    -- Default CCT at minimum brightness (Kelvin) - higher of this or fixture min
    dim_to_warm_min_cct_kelvin INT NOT NULL DEFAULT 1800,
    -- Curve exponent: 0.5 = square root (incandescent-like), 1.0 = linear
    dim_to_warm_curve_exponent REAL NOT NULL DEFAULT 0.5,

    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Ensure only one row exists (singleton pattern)
    CONSTRAINT system_settings_singleton CHECK (id = 1)
);

-- Insert default settings if not exists
INSERT INTO system_settings (id, dim_to_warm_max_cct_kelvin, dim_to_warm_min_cct_kelvin, dim_to_warm_curve_exponent)
VALUES (1, 3000, 1800, 0.5)
ON CONFLICT (id) DO NOTHING;

-- ============================================================================
-- 2. Add dim-to-warm columns to fixtures table
-- ============================================================================

-- Enable dim-to-warm behavior for this fixture
ALTER TABLE fixtures
ADD COLUMN IF NOT EXISTS dim_to_warm_enabled BOOLEAN DEFAULT FALSE;

-- Optional per-fixture CCT overrides
ALTER TABLE fixtures
ADD COLUMN IF NOT EXISTS dim_to_warm_max_cct INT;

ALTER TABLE fixtures
ADD COLUMN IF NOT EXISTS dim_to_warm_min_cct INT;

-- Add comments
COMMENT ON COLUMN fixtures.dim_to_warm_enabled IS 'Enable dim-to-warm behavior for this fixture';
COMMENT ON COLUMN fixtures.dim_to_warm_max_cct IS 'CCT at 100% brightness (Kelvin). Overrides system default.';
COMMENT ON COLUMN fixtures.dim_to_warm_min_cct IS 'CCT at minimum brightness (Kelvin). Overrides system default.';

-- ============================================================================
-- 3. Add dim-to-warm columns to groups table
-- ============================================================================

-- Enable dim-to-warm behavior for all fixtures in this group
ALTER TABLE groups
ADD COLUMN IF NOT EXISTS dim_to_warm_enabled BOOLEAN DEFAULT FALSE;

-- Optional per-group CCT overrides
ALTER TABLE groups
ADD COLUMN IF NOT EXISTS dim_to_warm_max_cct INT;

ALTER TABLE groups
ADD COLUMN IF NOT EXISTS dim_to_warm_min_cct INT;

-- Add comments
COMMENT ON COLUMN groups.dim_to_warm_enabled IS 'Enable dim-to-warm behavior for all fixtures in this group';
COMMENT ON COLUMN groups.dim_to_warm_max_cct IS 'CCT at 100% brightness (Kelvin). Overrides system default.';
COMMENT ON COLUMN groups.dim_to_warm_min_cct IS 'CCT at minimum brightness (Kelvin). Overrides system default.';

-- ============================================================================
-- 4. Create indexes for dim-to-warm columns
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_fixtures_dim_to_warm_enabled
ON fixtures(dim_to_warm_enabled)
WHERE dim_to_warm_enabled = TRUE;

CREATE INDEX IF NOT EXISTS idx_groups_dim_to_warm_enabled
ON groups(dim_to_warm_enabled)
WHERE dim_to_warm_enabled = TRUE;

-- ============================================================================
-- Migration complete
-- ============================================================================
