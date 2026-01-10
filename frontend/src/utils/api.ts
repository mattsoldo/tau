/**
 * Centralized API client for Tau Lighting Control
 *
 * Provides type-safe API methods and consistent error handling
 */

import type {
  Switch,
  SwitchModel,
  SwitchCreate,
  SwitchModelCreate,
} from '../types/tau';

/**
 * Get API URL for reverse proxy setup
 * - Uses empty string for relative paths (nginx handles routing)
 * - All API endpoints are proxied via /api/*
 */
const getApiUrl = (): string => {
  if (process.env.NEXT_PUBLIC_API_URL && process.env.NEXT_PUBLIC_API_URL !== 'undefined') {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  // Default to relative paths so nginx can proxy /api/* to the daemon
  return '';
};

/**
 * Get WebSocket URL for reverse proxy setup
 * - In browser: uses current origin with /api/ws path
 * - WebSocket connections are proxied via /api/ws
 */
export const getWsUrl = (): string => {
  if (process.env.NEXT_PUBLIC_WS_URL && process.env.NEXT_PUBLIC_WS_URL !== 'undefined') {
    return process.env.NEXT_PUBLIC_WS_URL;
  }

  if (typeof window !== 'undefined') {
    // Client-side: use current origin for WebSocket (proxied by nginx)
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    return `${protocol}://${window.location.host}/ws`;
  }

  // Server-side fallback (dev/test)
  const apiUrl = getApiUrl();
  if (apiUrl.startsWith('http')) {
    return apiUrl.replace(/^http/, 'ws') + '/ws';
  }
  return 'ws://localhost:8000/ws';
};

export const API_URL = getApiUrl();

/**
 * API error with structured information
 */
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail?: string
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Make an API request with consistent error handling
 */
async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_URL}${endpoint}`;

  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new ApiError(
      errorData.detail || `Request failed: ${response.status}`,
      response.status,
      errorData.detail
    );
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json();
}

/**
 * API client methods organized by resource
 */
export const api = {
  // Generic CRUD helpers
  get: <T>(endpoint: string) => request<T>(endpoint),

  post: <T>(endpoint: string, data: unknown) =>
    request<T>(endpoint, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  patch: <T>(endpoint: string, data: unknown) =>
    request<T>(endpoint, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  delete: (endpoint: string) =>
    request<void>(endpoint, { method: 'DELETE' }),

  // Fixture Models
  fixtureModels: {
    list: () => request<FixtureModel[]>('/api/fixtures/models'),
    get: (id: number) => request<FixtureModel>(`/api/fixtures/models/${id}`),
    create: (data: FixtureModelCreate) =>
      request<FixtureModel>('/api/fixtures/models', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    update: (id: number, data: Partial<FixtureModelCreate>) =>
      request<FixtureModel>(`/api/fixtures/models/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    delete: (id: number) =>
      request<void>(`/api/fixtures/models/${id}`, { method: 'DELETE' }),
  },

  // Fixtures
  fixtures: {
    list: () => request<Fixture[]>('/api/fixtures/'),
    get: (id: number) => request<Fixture>(`/api/fixtures/${id}`),
    create: (data: FixtureCreate) =>
      request<Fixture>('/api/fixtures/', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    update: (id: number, data: Partial<FixtureCreate>) =>
      request<Fixture>(`/api/fixtures/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    delete: (id: number) =>
      request<void>(`/api/fixtures/${id}`, { method: 'DELETE' }),
    getState: (id: number) => request<FixtureState>(`/api/fixtures/${id}/state`),
    merge: (data: FixtureMergeRequest) =>
      request<Fixture>('/api/fixtures/merge', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    unmerge: (id: number) =>
      request<Fixture>(`/api/fixtures/${id}/unmerge`, { method: 'POST' }),
  },

  // Groups
  groups: {
    list: () => request<Group[]>('/api/groups/'),
    get: (id: number) => request<Group>(`/api/groups/${id}`),
    create: (data: GroupCreate) =>
      request<Group>('/api/groups/', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    update: (id: number, data: Partial<GroupCreate>) =>
      request<Group>(`/api/groups/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    delete: (id: number) =>
      request<void>(`/api/groups/${id}`, { method: 'DELETE' }),
    getState: (id: number) => request<GroupState>(`/api/groups/${id}/state`),
    listFixtures: (groupId: number) =>
      request<Fixture[]>(`/api/groups/${groupId}/fixtures`),
    addFixture: (groupId: number, fixtureId: number) =>
      request<void>(`/api/groups/${groupId}/fixtures`, {
        method: 'POST',
        body: JSON.stringify({ fixture_id: fixtureId }),
      }),
    removeFixture: (groupId: number, fixtureId: number) =>
      request<void>(`/api/groups/${groupId}/fixtures/${fixtureId}`, {
        method: 'DELETE',
      }),
  },

  // Switches
  switches: {
    list: () => request<Switch[]>('/api/switches/'),
    get: (id: number) => request<Switch>(`/api/switches/${id}`),
    create: (data: SwitchCreate) =>
      request<Switch>('/api/switches/', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    update: (id: number, data: Partial<SwitchCreate>) =>
      request<Switch>(`/api/switches/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    delete: (id: number) =>
      request<void>(`/api/switches/${id}`, { method: 'DELETE' }),
  },

  // Switch Models
  switchModels: {
    list: () => request<SwitchModel[]>('/api/switches/models'),
    get: (id: number) => request<SwitchModel>(`/api/switches/models/${id}`),
    create: (data: SwitchModelCreate) =>
      request<SwitchModel>('/api/switches/models', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    update: (id: number, data: Partial<SwitchModelCreate>) =>
      request<SwitchModel>(`/api/switches/models/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    delete: (id: number) =>
      request<void>(`/api/switches/models/${id}`, { method: 'DELETE' }),
  },

  // Circadian Profiles
  circadian: {
    list: () => request<CircadianProfile[]>('/api/circadian/'),
    get: (id: number) => request<CircadianProfile>(`/api/circadian/${id}`),
    create: (data: CircadianProfileCreate) =>
      request<CircadianProfile>('/api/circadian/', {
        method: 'POST',
        body: JSON.stringify(data),
      }),
    update: (id: number, data: Partial<CircadianProfileCreate>) =>
      request<CircadianProfile>(`/api/circadian/${id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      }),
    delete: (id: number) =>
      request<void>(`/api/circadian/${id}`, { method: 'DELETE' }),
  },

  // Control
  control: {
    setFixture: (fixtureId: number, brightness: number, cct?: number) =>
      request<void>(`/api/control/fixtures/${fixtureId}`, {
        method: 'POST',
        body: JSON.stringify({ brightness, cct }),
      }),
    setGroup: (groupId: number, brightness: number, cct?: number) =>
      request<void>(`/api/control/groups/${groupId}`, {
        method: 'POST',
        body: JSON.stringify({ brightness, cct }),
      }),
  },

  // System
  system: {
    health: () => request<HealthResponse>('/health'),
    status: () => request<StatusResponse>('/status'),
  },

  // Updates (legacy git-based)
  updates: {
    getStatus: () => request<UpdateStatusResponse>('/api/updates/status'),
    check: () => request<UpdateCheckResponse>('/api/updates/check'),
    start: () => request<UpdateStartResponse>('/api/updates/start'),
    getHistory: (limit?: number) =>
      request<UpdateHistoryEntry[]>(`/api/updates/history?limit=${limit || 10}`),
    getChangelog: (fromCommit: string, toCommit?: string) =>
      request<ChangelogResponse>(
        `/api/updates/changelog?from_commit=${fromCommit}&to_commit=${toCommit || 'HEAD'}`
      ),
  },

  // Software Updates (GitHub Releases-based)
  softwareUpdate: {
    getStatus: () => request<SoftwareUpdateStatusResponse>('/api/system/update/status'),
    // Use POST for backwards compatibility with older backends
    check: () => request<SoftwareUpdateCheckResponse>('/api/system/update/check', { method: 'POST' }),
    apply: (targetVersion: string) =>
      request<SoftwareUpdateApplyResponse>('/api/system/update/apply', {
        method: 'POST',
        body: JSON.stringify({ target_version: targetVersion }),
      }),
    rollback: (targetVersion?: string) =>
      request<SoftwareUpdateRollbackResponse>('/api/system/update/rollback', {
        method: 'POST',
        body: JSON.stringify({ target_version: targetVersion }),
      }),
    getReleases: () => request<SoftwareReleaseInfo[]>('/api/system/update/releases'),
    getHistory: (limit?: number) =>
      request<SoftwareVersionHistoryEntry[]>(`/api/system/update/history?limit=${limit || 10}`),
    getBackups: () => request<SoftwareBackupInfo[]>('/api/system/update/backups'),
    getConfig: () => request<SoftwareUpdateConfig>('/api/system/update/config'),
    updateConfig: (key: string, value: string) =>
      request<SoftwareUpdateConfig>('/api/system/update/config', {
        method: 'PUT',
        body: JSON.stringify({ key, value }),
      }),
  },
};

// Type definitions for API responses
export interface FixtureModel {
  id: number;
  manufacturer: string;
  model: string;
  description: string | null;
  type: 'simple_dimmable' | 'tunable_white' | 'dim_to_warm' | 'non_dimmable' | 'other';
  dmx_footprint: number;
  cct_min_kelvin: number | null;
  cct_max_kelvin: number | null;
  warm_xy_x: number | null;
  warm_xy_y: number | null;
  cool_xy_x: number | null;
  cool_xy_y: number | null;
  warm_lumens: number | null;
  cool_lumens: number | null;
  gamma: number | null;
  created_at: string;
}

export interface FixtureModelCreate {
  manufacturer: string;
  model: string;
  description?: string | null;
  type: FixtureModel['type'];
  dmx_footprint: number;
  cct_min_kelvin?: number | null;
  cct_max_kelvin?: number | null;
  warm_xy_x?: number | null;
  warm_xy_y?: number | null;
  cool_xy_x?: number | null;
  cool_xy_y?: number | null;
  warm_lumens?: number | null;
  cool_lumens?: number | null;
  gamma?: number | null;
}

export interface Fixture {
  id: number;
  name: string;
  fixture_model_id: number;
  dmx_channel_start: number;
  secondary_dmx_channel: number | null;
  room: string | null;
  notes: string | null;
  created_at: string;
}

export interface FixtureCreate {
  name: string;
  fixture_model_id: number;
  dmx_channel_start: number;
  room?: string | null;
  notes?: string | null;
}

export interface FixtureMergeRequest {
  primary_fixture_id: number;
  secondary_fixture_id: number;
  target_model_id?: number;
}

export interface FixtureState {
  fixture_id: number;
  goal_brightness: number;
  goal_cct: number;
  current_brightness: number;
  current_cct: number;
  is_on: boolean;
  transitioning: boolean;
}

export interface Group {
  id: number;
  name: string;
  description: string | null;
  circadian_enabled: boolean;
  circadian_profile_id: number | null;
  created_at: string;
}

export interface GroupCreate {
  name: string;
  description?: string | null;
  circadian_enabled?: boolean;
  circadian_profile_id?: number | null;
}

export interface GroupState {
  group_id: number;
  circadian_suspended: boolean;
}

export interface CircadianProfile {
  id: number;
  name: string;
  description: string | null;
  curve_points: Record<string, { brightness: number; cct: number }>;
  created_at: string;
}

export interface CircadianProfileCreate {
  name: string;
  description?: string | null;
  curve_points: Record<string, { brightness: number; cct: number }>;
}

export interface HealthResponse {
  status: string;
  version: string;
  service: string;
}

export interface StatusResponse {
  status: string;
  version: string;
  service: string;
  event_loop?: Record<string, unknown>;
  scheduled_tasks?: Record<string, unknown>;
  state_manager?: Record<string, unknown>;
  persistence?: Record<string, unknown>;
  hardware?: Record<string, unknown>;
  lighting?: Record<string, unknown>;
}

export interface UpdateStatusResponse {
  current_version: string;
  available_version: string | null;
  update_available: boolean;
  is_updating: boolean;
  last_check_at: string | null;
}

export interface UpdateCheckResponse {
  update_available: boolean;
  current_version: string;
  latest_version: string;
  commits_behind: number;
  changelog: string;
}

export interface UpdateStartResponse {
  message: string;
  update_id: number;
}

export interface UpdateHistoryEntry {
  id: number;
  version_before: string | null;
  version_after: string | null;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  changelog: string | null;
  update_type: string | null;
}

export interface ChangelogResponse {
  changelog: string;
  from_commit: string;
  to_commit: string;
}

// Software Update Types (GitHub Releases-based)
export interface SoftwareUpdateStatusResponse {
  current_version: string;
  installed_at: string;
  install_method: string | null;
  update_available: boolean;
  available_version: string | null;
  release_notes: string | null;
  last_check_at: string | null;
  state: string;
  progress: Record<string, unknown>;
}

export interface SoftwareUpdateCheckResponse {
  update_available: boolean;
  current_version: string;
  latest_version: string;
  release_notes: string;
  published_at: string | null;
  prerelease: boolean;
}

export interface SoftwareUpdateApplyResponse {
  success: boolean;
  from_version: string;
  to_version: string;
  message: string;
}

export interface SoftwareUpdateRollbackResponse {
  success: boolean;
  from_version: string;
  to_version: string;
  message: string;
}

export interface SoftwareReleaseInfo {
  version: string;
  tag_name: string;
  published_at: string;
  release_notes: string | null;
  asset_url: string | null;
  asset_name: string | null;
  asset_size: number | null;
  prerelease: boolean;
  has_asset: boolean;
}

export interface SoftwareVersionHistoryEntry {
  version: string;
  installed_at: string;
  uninstalled_at: string | null;
  backup_path: string | null;
  backup_valid: boolean;
  can_rollback: boolean;
  is_current: boolean;
  release_notes: string | null;
}

export interface SoftwareBackupInfo {
  version: string;
  backup_path: string;
  created_at: string;
  size_bytes: number;
  size_mb: number;
  valid: boolean;
}

export interface SoftwareUpdateConfig {
  auto_check_enabled: string;
  check_interval_hours: string;
  include_prereleases: string;
  max_backups: string;
  github_repo: string;
  github_token: string;
  backup_location: string;
  min_free_space_mb: string;
  download_timeout_seconds: string;
  verify_after_install: string;
  rollback_on_service_failure: string;
}
