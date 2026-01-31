/**
 * Tau Lighting Control System - TypeScript Type Definitions
 */

// Fixture Types
export type FixtureType =
  | 'simple_dimmable'
  | 'tunable_white'
  | 'dim_to_warm'
  | 'non_dimmable'
  | 'other';

export type MixingType = 'linear' | 'perceptual' | 'logarithmic' | 'custom';

export interface FixtureModel {
  id: number;
  manufacturer: string;
  model: string;
  description?: string;
  type: FixtureType;
  dmx_footprint: number;
  cct_min_kelvin: number;
  cct_max_kelvin: number;
  mixing_type: MixingType;
  created_at: string;
}

export interface Fixture {
  id: number;
  name: string;
  fixture_model_id: number;
  dmx_channel_start: number;
  created_at: string;
  model?: FixtureModel;
}

// Switch Types
export type SwitchInputType =
  | 'retractive'
  | 'rotary_abs'
  | 'paddle_composite'
  | 'switch_simple';

export type DimmingCurve = 'linear' | 'logarithmic';

export interface SwitchModel {
  id: number;
  manufacturer: string;
  model: string;
  input_type: SwitchInputType;
  debounce_ms: number;
  dimming_curve: DimmingCurve;
  requires_digital_pin: boolean;
  requires_analog_pin: boolean;
}

export type SwitchType = 'normally-open' | 'normally-closed';

export interface Switch {
  id: number;
  name?: string;
  switch_model_id: number;
  labjack_digital_pin?: number;
  labjack_analog_pin?: number;
  switch_type: SwitchType;
  invert_reading: boolean;
  target_group_id?: number;
  target_fixture_id?: number;
  double_tap_scene_id?: number;
  photo_url?: string;
  model?: SwitchModel;
}

export interface SwitchModelCreate {
  manufacturer: string;
  model: string;
  input_type: SwitchInputType;
  debounce_ms?: number;
  dimming_curve?: DimmingCurve;
  requires_digital_pin?: boolean;
  requires_analog_pin?: boolean;
}

export interface SwitchCreate {
  name?: string;
  switch_model_id: number;
  labjack_digital_pin?: number;
  labjack_analog_pin?: number;
  switch_type?: SwitchType;
  invert_reading?: boolean;
  target_group_id?: number;
  target_fixture_id?: number;
  double_tap_scene_id?: number;
  photo_url?: string;
}

// Group Types
export interface Group {
  id: number;
  name: string;
  description: string | null;
  circadian_enabled: boolean;
  circadian_profile_id: number | null;
  default_max_brightness: number | null;
  default_cct_kelvin: number | null;
  is_system: boolean | null;
  display_order: number | null;
  created_at: string;
  // Sleep Mode Lock Settings
  sleep_lock_enabled: boolean;
  sleep_lock_start_time: string | null;  // HH:MM format
  sleep_lock_end_time: string | null;    // HH:MM format
  sleep_lock_unlock_duration_minutes: number | null;
  sleep_lock_active: boolean | null;     // Computed field from server
}

// Circadian Types
export type InterpolationType = 'linear' | 'cosine' | 'step';

export interface CircadianCurvePoint {
  time: string; // HH:MM format
  brightness: number; // 0-1000 (tenths of percent)
  cct: number; // Kelvin
}

export interface CircadianProfile {
  id: number;
  name: string;
  description?: string;
  curve_points: CircadianCurvePoint[];
  interpolation_type: InterpolationType;
  created_at: string;
}

// Scene Types
export interface Scene {
  id: number;
  name: string;
  scope_group_id?: number;
  values?: SceneValue[];
}

export interface SceneValue {
  scene_id: number;
  fixture_id: number;
  target_brightness: number; // 0-1000
  target_cct_kelvin?: number;
}

// State Types
export interface FixtureState {
  fixture_id: number;
  current_brightness: number; // 0-1000
  current_cct: number;
  is_on: boolean;
  last_updated: string;
}

export interface GroupState {
  group_id: number;
  circadian_suspended: boolean;
  circadian_suspended_at?: string;
  last_active_scene_id?: number;
}

// API Response Types
export interface ApiResponse<T> {
  data: T;
  success: boolean;
  message?: string;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  page_size: number;
}

// Control Types
export interface ControlCommand {
  target_type: 'fixture' | 'group';
  target_id: number;
  brightness?: number; // 0-1000
  cct?: number; // Kelvin
  transition_ms?: number;
}

// WebSocket Event Types
export type WebSocketEventType =
  | 'fixture_state_changed'
  | 'group_state_changed'
  | 'scene_activated'
  | 'hardware_status'
  | 'error';

export interface WebSocketEvent {
  type: WebSocketEventType;
  timestamp: string;
  data: unknown;
}
