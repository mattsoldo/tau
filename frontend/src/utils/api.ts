/**
 * Centralized API client for Tau Lighting Control
 *
 * Provides type-safe API methods and consistent error handling
 */

/**
 * Get API URL dynamically based on environment
 * - In browser: uses current hostname from window.location
 * - On server: uses environment variable or localhost fallback
 * This allows the frontend to work with any IP address without rebuilding
 */
const getApiUrl = (): string => {
  if (typeof window !== 'undefined') {
    // Client-side: use current hostname from browser
    const protocol = window.location.protocol === 'https:' ? 'https' : 'http';
    return `${protocol}://${window.location.hostname}:8000`;
  }
  // Server-side: use env var or localhost
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
};

/**
 * Get WebSocket URL dynamically based on environment
 * - In browser: uses current hostname from window.location
 * - On server: uses environment variable or localhost fallback
 */
export const getWsUrl = (): string => {
  if (typeof window !== 'undefined') {
    // Client-side: use current hostname from browser
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    return `${protocol}://${window.location.hostname}:8000`;
  }
  // Server-side: use env var or localhost
  return process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';
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
      request<void>(`/api/control/fixture/${fixtureId}`, {
        method: 'POST',
        body: JSON.stringify({ brightness, cct }),
      }),
    setGroup: (groupId: number, brightness: number, cct?: number) =>
      request<void>(`/api/control/group/${groupId}`, {
        method: 'POST',
        body: JSON.stringify({ brightness, cct }),
      }),
  },

  // System
  system: {
    health: () => request<HealthResponse>('/health'),
    status: () => request<StatusResponse>('/status'),
  },

  // Updates
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
