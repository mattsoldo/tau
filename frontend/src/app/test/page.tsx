'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import { filterMergedFixtures } from '@/utils/fixtures';
import { useWebSocket, FixtureStateChangedEvent, GroupStateChangedEvent } from '@/hooks/useWebSocket';
import { API_URL } from '@/utils/api';

// Brightness scaling constants
// IMPORTANT: Multiple brightness representations exist in the system:
// - WebSocket broadcasts: 0.0-1.0 (daemon internal state)
// - REST API (brightness_percent): 0-100 (user-facing API)
// - Frontend state: 0-1000 (internal, for smooth slider control)
// - Frontend display: 0-100 (UI, same as REST API scale)
//
// Conversion: WebSocket (0.0-1.0) × BRIGHTNESS_SCALE → State (0-1000)
const BRIGHTNESS_SCALE = 1000; // Multiply WebSocket 0.0-1.0 to get state 0-1000

// === Types ===

type FixtureType = 'simple_dimmable' | 'tunable_white' | 'dim_to_warm' | 'non_dimmable' | 'other';

interface FixtureModel {
  id: number;
  manufacturer: string;
  model: string;
  type: FixtureType;
  dmx_footprint: number;
  cct_min_kelvin: number;
  cct_max_kelvin: number;
}

interface Fixture {
  id: number;
  name: string;
  fixture_model_id: number;
  dmx_channel_start: number;
  secondary_dmx_channel: number | null;
}

interface FixtureState {
  fixture_id: number;
  goal_brightness: number;
  goal_cct: number;
  current_brightness: number;
  current_cct: number;
  is_on: boolean;
  override_active?: boolean;
  override_expires_at?: number;
}

interface Group {
  id: number;
  name: string;
  description?: string;
  is_system?: boolean;
  circadian_enabled?: boolean;
}

interface FixtureWithState extends Fixture {
  model?: FixtureModel;
  state?: FixtureState;
}

interface GroupWithFixtures extends Group {
  fixtures: FixtureWithState[];
}

// === Helper Functions ===

const kelvinToColor = (kelvin: number): string => {
  const clampedKelvin = Math.max(1000, Math.min(40000, kelvin));
  const temp = clampedKelvin / 100;
  let r: number, g: number, b: number;

  if (temp <= 66) {
    r = 255;
    if (temp <= 20) {
      g = Math.max(40, (temp - 10) * 9.7 + 56);
      b = 0;
    } else {
      g = 99.4708025861 * Math.log(temp) - 161.1195681661;
      b = temp - 10;
      b = 138.5177312231 * Math.log(b) - 305.0447927307;
    }
  } else {
    r = temp - 60;
    r = 329.698727446 * Math.pow(r, -0.1332047592);
    g = temp - 60;
    g = 288.1221695283 * Math.pow(g, -0.0755148492);
    b = 255;
  }

  r = Math.max(0, Math.min(255, r));
  g = Math.max(0, Math.min(255, g));
  b = Math.max(0, Math.min(255, b));

  return `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`;
};

const typeLabels: Record<FixtureType, { label: string; color: string }> = {
  simple_dimmable: { label: 'Dimmable', color: 'bg-blue-500/15 text-blue-400 border-blue-500/30' },
  tunable_white: { label: 'Tunable', color: 'bg-amber-500/15 text-amber-400 border-amber-500/30' },
  dim_to_warm: { label: 'Dim to Warm', color: 'bg-orange-500/15 text-orange-400 border-orange-500/30' },
  non_dimmable: { label: 'On/Off', color: 'bg-gray-500/15 text-gray-400 border-gray-500/30' },
  other: { label: 'Other', color: 'bg-purple-500/15 text-purple-400 border-purple-500/30' },
};

const formatTimeRemaining = (expiresAt: number): string => {
  const now = Date.now() / 1000;
  const remaining = expiresAt - now;
  if (remaining <= 0) return 'Expiring...';
  const hours = Math.floor(remaining / 3600);
  const minutes = Math.floor((remaining % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
};

export default function LightTestPage() {
  const [groupsWithFixtures, setGroupsWithFixtures] = useState<GroupWithFixtures[]>([]);
  const [fixtureModels, setFixtureModels] = useState<FixtureModel[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set());

  // Debouncing refs
  const pendingChanges = useRef<Map<number, { brightness?: number; cct?: number }>>(new Map());
  const debounceTimers = useRef<Map<number, NodeJS.Timeout>>(new Map());
  const groupDebounceTimers = useRef<Map<number, NodeJS.Timeout>>(new Map());
  const userGoalState = useRef<Map<number, { brightness: number; cct: number; timestamp: number }>>(new Map());
  const userGroupGoalState = useRef<Map<number, { brightness?: number; cct?: number; timestamp: number }>>(new Map());

  // Track pending API requests to avoid WebSocket race conditions
  // (replaces timestamp-based grace period - more robust)
  const pendingRequestsRef = useRef<Set<string>>(new Set());

  // WebSocket integration for real-time updates from switch actions
  const handleFixtureStateChanged = useCallback((event: FixtureStateChangedEvent) => {
    const key = `fixture-${event.fixture_id}`;

    // Don't overwrite if there's a pending API request for this fixture
    // This prevents race conditions where WebSocket updates arrive while
    // user-initiated API calls are still in flight
    if (pendingRequestsRef.current.has(key)) {
      return;
    }

    setGroupsWithFixtures(prev => {
      let hasChanges = false;

      const updated = prev.map(group => ({
        ...group,
        fixtures: group.fixtures.map(f => {
          if (f.id !== event.fixture_id || !f.state) return f;

          const newBrightness = event.brightness * BRIGHTNESS_SCALE;
          const newCct = event.color_temp ?? f.state.goal_cct;
          const newIsOn = event.brightness > 0;

          // Early return if state hasn't actually changed
          if (
            f.state.goal_brightness === newBrightness &&
            f.state.goal_cct === newCct &&
            f.state.is_on === newIsOn
          ) {
            return f;
          }

          hasChanges = true;
          return {
            ...f,
            state: {
              ...f.state,
              goal_brightness: newBrightness,
              goal_cct: newCct,
              is_on: newIsOn,
            },
          };
        }),
      }));

      // Avoid unnecessary re-renders if nothing changed
      return hasChanges ? updated : prev;
    });
  }, []);

  const handleGroupStateChanged = useCallback((event: GroupStateChangedEvent) => {
    const key = `group-${event.group_id}`;

    // Don't overwrite if there's a pending API request for this group
    if (pendingRequestsRef.current.has(key)) {
      return;
    }

    // Update all fixtures in the affected group
    setGroupsWithFixtures(prev => {
      let hasChanges = false;

      const updated = prev.map(group => {
        if (group.id !== event.group_id) return group;

        const updatedFixtures = group.fixtures.map(f => {
          if (!f.state) return f;

          const newBrightness = event.brightness * BRIGHTNESS_SCALE;
          const newCct = event.color_temp ?? f.state.goal_cct;
          const newIsOn = event.brightness > 0;

          // Early return if state hasn't actually changed
          if (
            f.state.goal_brightness === newBrightness &&
            f.state.goal_cct === newCct &&
            f.state.is_on === newIsOn
          ) {
            return f;
          }

          hasChanges = true;
          return {
            ...f,
            state: {
              ...f.state,
              goal_brightness: newBrightness,
              goal_cct: newCct,
              is_on: newIsOn,
            },
          };
        });

        return { ...group, fixtures: updatedFixtures };
      });

      // Avoid unnecessary re-renders if nothing changed
      return hasChanges ? updated : prev;
    });
  }, []);

  // Connect to WebSocket for real-time updates
  useWebSocket({
    onFixtureStateChanged: handleFixtureStateChanged,
    onGroupStateChanged: handleGroupStateChanged,
  });

  // Fetch all data
  const fetchData = useCallback(async () => {
    try {
      const [fixturesRes, modelsRes, groupsRes] = await Promise.all([
        fetch(`${API_URL}/api/fixtures/`),
        fetch(`${API_URL}/api/fixtures/models`),
        fetch(`${API_URL}/api/groups/`),
      ]);

      if (!fixturesRes.ok || !modelsRes.ok || !groupsRes.ok) {
        throw new Error('Failed to fetch data');
      }

      const [fixturesData, modelsData, groupsData] = await Promise.all([
        fixturesRes.json(),
        modelsRes.json(),
        groupsRes.json(),
      ]);

      setFixtureModels(modelsData);

      // Filter out fixtures that are merged into other fixtures
      const visibleFixtures = filterMergedFixtures(fixturesData);

      // Fetch state for all visible fixtures
      const now = Date.now();
      const fixturesWithState: FixtureWithState[] = await Promise.all(
        visibleFixtures.map(async (fixture: Fixture) => {
          const model = modelsData.find((m: FixtureModel) => m.id === fixture.fixture_model_id);
          let state: FixtureState | undefined;

          try {
            const stateRes = await fetch(`${API_URL}/api/fixtures/${fixture.id}/state`);
            if (stateRes.ok) {
              const fetchedState = await stateRes.json();
              const userGoal = userGoalState.current.get(fixture.id);
              const isUserControlling = userGoal && (now - userGoal.timestamp) < 500;

              state = {
                fixture_id: fixture.id,
                goal_brightness: isUserControlling ? userGoal.brightness * 10 : fetchedState.goal_brightness ?? 0,
                goal_cct: isUserControlling ? userGoal.cct : fetchedState.goal_cct ?? 2700,
                current_brightness: fetchedState.current_brightness ?? 0,
                current_cct: fetchedState.current_cct ?? 2700,
                is_on: (fetchedState.current_brightness ?? 0) > 0,
                override_active: fetchedState.override_active ?? false,
                override_expires_at: fetchedState.override_expires_at,
              };
            }
          } catch {
            // State might not exist yet
          }

          return { ...fixture, model, state };
        })
      );

      // Fetch fixtures for each group and build group structures
      const groupsWithFixturesData: GroupWithFixtures[] = await Promise.all(
        groupsData.map(async (group: Group) => {
          try {
            const fixturesInGroupRes = await fetch(`${API_URL}/api/groups/${group.id}/fixtures`);
            if (fixturesInGroupRes.ok) {
              const fixtureIds: { id: number }[] = await fixturesInGroupRes.json();
              const fixtures = fixtureIds
                .map(f => fixturesWithState.find(fw => fw.id === f.id))
                .filter((f): f is FixtureWithState => f !== undefined);
              return { ...group, fixtures };
            }
          } catch {
            // Ignore errors fetching group fixtures
          }
          return { ...group, fixtures: [] };
        })
      );

      // Sort groups: system groups first, then by name
      groupsWithFixturesData.sort((a, b) => {
        if (a.is_system && !b.is_system) return -1;
        if (!a.is_system && b.is_system) return 1;
        return a.name.localeCompare(b.name);
      });

      setGroupsWithFixtures(groupsWithFixturesData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 2000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Toggle group expansion
  const toggleGroup = (groupId: number) => {
    setExpandedGroups(prev => {
      const next = new Set(prev);
      if (next.has(groupId)) {
        next.delete(groupId);
      } else {
        next.add(groupId);
      }
      return next;
    });
  };

  // Send fixture control command
  const sendFixtureControl = useCallback(async (fixtureId: number, brightness?: number, colorTemp?: number) => {
    const key = `fixture-${fixtureId}`;

    const existingTimer = debounceTimers.current.get(fixtureId);
    if (existingTimer) clearTimeout(existingTimer);

    const pending = pendingChanges.current.get(fixtureId) || {};
    if (brightness !== undefined) pending.brightness = brightness;
    if (colorTemp !== undefined) pending.cct = colorTemp;
    pendingChanges.current.set(fixtureId, pending);

    const timer = setTimeout(async () => {
      const changes = pendingChanges.current.get(fixtureId);
      if (!changes) {
        pendingRequestsRef.current.delete(key);
        return;
      }

      try {
        const body: Record<string, number> = {};
        if (changes.brightness !== undefined) body.brightness = changes.brightness;
        if (changes.cct !== undefined) body.color_temp = changes.cct;

        await fetch(`${API_URL}/api/control/fixtures/${fixtureId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });

        pendingChanges.current.delete(fixtureId);
      } catch (err) {
        console.error('Fixture control error:', err);
      } finally {
        // Always remove pending request marker when request completes
        pendingRequestsRef.current.delete(key);
      }
    }, 50);

    debounceTimers.current.set(fixtureId, timer);
  }, []);

  // Send group brightness control command
  const sendGroupControl = useCallback(async (groupId: number, brightness: number) => {
    const key = `group-${groupId}`;

    // Mark this group as having a pending request
    pendingRequestsRef.current.add(key);

    const existingTimer = groupDebounceTimers.current.get(groupId);
    if (existingTimer) clearTimeout(existingTimer);

    // Store user-set value immediately and force re-render
    const existing = userGroupGoalState.current.get(groupId);
    userGroupGoalState.current.set(groupId, {
      brightness,
      cct: existing?.cct,
      timestamp: Date.now(),
    });

    // Force immediate UI update by updating state
    setGroupsWithFixtures(prev => [...prev]);

    const timer = setTimeout(async () => {
      try {
        await fetch(`${API_URL}/api/control/groups/${groupId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ brightness }),
        });
      } catch (err) {
        console.error('Group control error:', err);
      } finally {
        // Always remove pending request marker when request completes
        pendingRequestsRef.current.delete(key);
      }
    }, 50);

    groupDebounceTimers.current.set(groupId, timer);
  }, []);

  // Send group CCT control command
  const sendGroupCctControl = useCallback(async (groupId: number, colorTemp: number) => {
    const key = `group-${groupId}`;

    // Mark this group as having a pending request
    pendingRequestsRef.current.add(key);

    const timerKey = groupId + 10000; // Offset to avoid collisions with brightness timers
    const existingTimer = groupDebounceTimers.current.get(timerKey);
    if (existingTimer) clearTimeout(existingTimer);

    // Store user-set value immediately and force re-render
    const existing = userGroupGoalState.current.get(groupId);
    userGroupGoalState.current.set(groupId, {
      brightness: existing?.brightness,
      cct: colorTemp,
      timestamp: Date.now(),
    });

    // Force immediate UI update by updating state
    setGroupsWithFixtures(prev => [...prev]);

    const timer = setTimeout(async () => {
      try {
        await fetch(`${API_URL}/api/control/groups/${groupId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ color_temp: colorTemp }),
        });
      } catch (err) {
        console.error('Group CCT control error:', err);
      } finally {
        // Always remove pending request marker when request completes
        pendingRequestsRef.current.delete(key);
      }
    }, 50);

    groupDebounceTimers.current.set(timerKey, timer);
  }, []);

  // Update fixture state locally
  const updateFixtureState = useCallback((fixtureId: number, brightness?: number, cct?: number) => {
    const key = `fixture-${fixtureId}`;

    // Mark this fixture as having a pending request
    pendingRequestsRef.current.add(key);

    const existing = userGoalState.current.get(fixtureId);
    userGoalState.current.set(fixtureId, {
      brightness: brightness ?? (existing?.brightness ?? 0),
      cct: cct ?? (existing?.cct ?? 2700),
      timestamp: Date.now(),
    });

    setGroupsWithFixtures(prev => prev.map(group => ({
      ...group,
      fixtures: group.fixtures.map(f => {
        if (f.id !== fixtureId) return f;
        const newGoalBrightness = brightness !== undefined ? brightness * 10 : f.state?.goal_brightness ?? 0;
        const newGoalCct = cct ?? f.state?.goal_cct ?? 2700;
        return {
          ...f,
          state: {
            fixture_id: fixtureId,
            goal_brightness: newGoalBrightness,
            goal_cct: newGoalCct,
            current_brightness: f.state?.current_brightness ?? 0,
            current_cct: f.state?.current_cct ?? 2700,
            is_on: newGoalBrightness > 0,
            override_active: true, // Will be set by control API
            override_expires_at: f.state?.override_expires_at,
          },
        };
      }),
    })));
  }, []);

  // Handle fixture brightness change
  const handleFixtureBrightnessChange = useCallback((fixture: FixtureWithState, value: number) => {
    const normalizedValue = value / 100;
    updateFixtureState(fixture.id, value);
    sendFixtureControl(fixture.id, normalizedValue);
  }, [sendFixtureControl, updateFixtureState]);

  // Handle fixture CCT change
  const handleFixtureCctChange = useCallback((fixture: FixtureWithState, value: number) => {
    updateFixtureState(fixture.id, undefined, value);
    sendFixtureControl(fixture.id, undefined, value);
  }, [sendFixtureControl, updateFixtureState]);

  // Remove override from fixture
  const handleRemoveOverride = useCallback(async (fixtureId: number) => {
    try {
      await fetch(`${API_URL}/api/control/overrides/fixtures/${fixtureId}`, {
        method: 'DELETE',
      });
      // Update local state
      setGroupsWithFixtures(prev => prev.map(group => ({
        ...group,
        fixtures: group.fixtures.map(f => {
          if (f.id !== fixtureId) return f;
          return {
            ...f,
            state: f.state ? { ...f.state, override_active: false, override_expires_at: undefined } : undefined,
          };
        }),
      })));
    } catch (err) {
      console.error('Remove override error:', err);
    }
  }, []);

  // Quick actions
  const handleAllOff = useCallback(async () => {
    try {
      await fetch(`${API_URL}/api/control/all-off`, { method: 'POST' });
      userGoalState.current.clear();
      userGroupGoalState.current.clear();
      fetchData();
    } catch (err) {
      console.error('All off error:', err);
    }
  }, [fetchData]);

  const handleAllOn = useCallback(async () => {
    try {
      await fetch(`${API_URL}/api/control/panic`, { method: 'POST' });
      userGoalState.current.clear();
      userGroupGoalState.current.clear();
      fetchData();
    } catch (err) {
      console.error('All on error:', err);
    }
  }, [fetchData]);

  // Helpers
  const supportsCct = (fixture: FixtureWithState): boolean => fixture.model?.type === 'tunable_white';
  const isDimmable = (fixture: FixtureWithState): boolean => fixture.model?.type !== 'non_dimmable';

  // Get group brightness - prioritize user-set value, fall back to average
  const getGroupBrightness = (group: GroupWithFixtures): number => {
    const userGoal = userGroupGoalState.current.get(group.id);
    const now = Date.now();
    const isUserControlling = userGoal && userGoal.brightness !== undefined && (now - userGoal.timestamp) < 5000;

    if (isUserControlling) {
      return userGoal.brightness! * 100; // User-set value in percentage
    }

    // Fall back to calculating average from fixtures
    if (group.fixtures.length === 0) return 0;
    const total = group.fixtures.reduce((sum, f) => sum + ((f.state?.goal_brightness ?? 0) / 10), 0);
    return total / group.fixtures.length;
  };

  // Get group CCT - prioritize user-set value, fall back to average
  const getGroupCct = (group: GroupWithFixtures): number | null => {
    const userGoal = userGroupGoalState.current.get(group.id);
    const now = Date.now();
    const isUserControlling = userGoal && userGoal.cct !== undefined && (now - userGoal.timestamp) < 5000;

    if (isUserControlling) {
      return userGoal.cct!; // User-set CCT value
    }

    // Fall back to calculating average from tunable fixtures
    const tunableFixtures = group.fixtures.filter(f => f.model?.type === 'tunable_white');
    if (tunableFixtures.length === 0) return null;
    const total = tunableFixtures.reduce((sum, f) => sum + (f.state?.goal_cct ?? 2700), 0);
    return Math.round(total / tunableFixtures.length);
  };

  // Get group's average CURRENT brightness (transitioning state)
  const getGroupCurrentBrightness = (group: GroupWithFixtures): number => {
    if (group.fixtures.length === 0) return 0;
    const total = group.fixtures.reduce((sum, f) => sum + ((f.state?.current_brightness ?? 0) / 10), 0);
    return total / group.fixtures.length;
  };

  // Get group's average CURRENT CCT (transitioning state)
  const getGroupCurrentCct = (group: GroupWithFixtures): number | null => {
    const tunableFixtures = group.fixtures.filter(f => f.model?.type === 'tunable_white');
    if (tunableFixtures.length === 0) return null;
    const total = tunableFixtures.reduce((sum, f) => sum + (f.state?.current_cct ?? 2700), 0);
    return Math.round(total / tunableFixtures.length);
  };

  // Check if group has any tunable white fixtures
  const groupHasTunableFixtures = (group: GroupWithFixtures): boolean => {
    return group.fixtures.some(f => f.model?.type === 'tunable_white');
  };

  // Get CCT range for group (min/max from all tunable fixtures)
  const getGroupCctRange = (group: GroupWithFixtures): { min: number; max: number } => {
    const tunableFixtures = group.fixtures.filter(f => f.model?.type === 'tunable_white');
    if (tunableFixtures.length === 0) return { min: 2700, max: 6500 };
    const min = Math.min(...tunableFixtures.map(f => f.model?.cct_min_kelvin ?? 2700));
    const max = Math.max(...tunableFixtures.map(f => f.model?.cct_max_kelvin ?? 6500));
    return { min, max };
  };

  // Count overrides in group
  const getOverrideCount = (group: GroupWithFixtures): number => {
    return group.fixtures.filter(f => f.state?.override_active).length;
  };

  return (
    <div className="min-h-screen text-white flex">
      {/* Sidebar */}
      <aside className="w-64 bg-[#111113] border-r border-[#1f1f24] flex flex-col">

        <div className="p-4 border-b border-[#1f1f24]">
          <h3 className="text-xs font-medium text-[#636366] uppercase tracking-wider mb-3">Quick Actions</h3>
          <div className="space-y-2">
            <button
              onClick={handleAllOn}
              className="w-full px-4 py-2.5 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z" />
              </svg>
              All Lights On
            </button>
            <button
              onClick={handleAllOff}
              className="w-full px-4 py-2.5 bg-[#2a2a2f] hover:bg-[#3a3a3f] text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2 border border-[#3a3a3f]"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M21.752 15.002A9.718 9.718 0 0118 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 003 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 009.002-5.998z" />
              </svg>
              All Lights Off
            </button>
          </div>
        </div>

        <div className="p-4 border-b border-[#1f1f24]">
          <h3 className="text-xs font-medium text-[#636366] uppercase tracking-wider mb-3">Status</h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-[#a1a1a6]">Groups</span>
              <span className="font-medium">{groupsWithFixtures.length}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[#a1a1a6]">Total Fixtures</span>
              <span className="font-medium">
                {groupsWithFixtures.reduce((sum, g) => sum + g.fixtures.length, 0)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-[#a1a1a6]">Active Overrides</span>
              <span className="font-medium text-amber-400">
                {groupsWithFixtures.reduce((sum, g) => sum + getOverrideCount(g), 0)}
              </span>
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="p-8">
          <div className="mb-8">
            <h1 className="text-3xl font-bold">Light Testing</h1>
            <p className="text-[#636366] mt-1">Control groups and individual fixtures</p>
          </div>

          {error && (
            <div className="mb-6 px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
              {error}
            </div>
          )}

          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin"></div>
            </div>
          ) : groupsWithFixtures.length === 0 ? (
            <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] p-12 text-center">
              <h3 className="text-lg font-semibold mb-2">No Groups Found</h3>
              <p className="text-[#636366] mb-4">Configure groups and fixtures to get started.</p>
              <Link
                href="/config/fixtures"
                className="inline-flex items-center gap-2 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors"
              >
                Configure Fixtures
              </Link>
            </div>
          ) : (
            <div className="space-y-4">
              {groupsWithFixtures.map((group) => {
                const isExpanded = expandedGroups.has(group.id);
                const avgBrightness = getGroupBrightness(group);
                const overrideCount = getOverrideCount(group);
                const hasLightsOn = group.fixtures.some(f => (f.state?.current_brightness ?? 0) > 0);

                return (
                  <div
                    key={group.id}
                    className={`bg-[#1a1a1f] rounded-xl border transition-all ${
                      hasLightsOn ? 'border-amber-500/30' : 'border-[#2a2a2f]'
                    }`}
                  >
                    {/* Group Header */}
                    <div className="p-5">
                      <div className="flex items-start justify-between mb-4">
                        <div className="flex items-center gap-3">
                          <button
                            onClick={() => toggleGroup(group.id)}
                            className={`w-10 h-10 rounded-lg flex items-center justify-center transition-all ${
                              hasLightsOn ? 'bg-amber-500/20' : 'bg-[#2a2a2f]'
                            }`}
                          >
                            <svg
                              className={`w-5 h-5 transition-transform ${isExpanded ? 'rotate-90' : ''} ${
                                hasLightsOn ? 'text-amber-400' : 'text-[#636366]'
                              }`}
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                              viewBox="0 0 24 24"
                            >
                              <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                            </svg>
                          </button>
                          <div>
                            <div className="flex items-center gap-2">
                              <h3 className="font-semibold text-lg">{group.name}</h3>
                              {group.is_system && (
                                <span className="text-xs px-2 py-0.5 rounded-full bg-purple-500/15 text-purple-400 border border-purple-500/30">
                                  System
                                </span>
                              )}
                              {group.circadian_enabled && (
                                <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-400 border border-blue-500/30">
                                  Circadian
                                </span>
                              )}
                            </div>
                            <div className="flex items-center gap-3 mt-1 text-xs text-[#636366]">
                              <span>{group.fixtures.length} fixtures</span>
                              {overrideCount > 0 && (
                                <span className="text-amber-400">
                                  {overrideCount} override{overrideCount !== 1 ? 's' : ''}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* Group brightness indicator */}
                        <div className="text-right">
                          <div className="text-2xl font-bold tabular-nums">{Math.round(avgBrightness)}%</div>
                          <div className="text-xs text-[#636366]">
                            {(() => {
                              const userGoal = userGroupGoalState.current.get(group.id);
                              const now = Date.now();
                              const isUserSet = userGoal && userGoal.brightness !== undefined && (now - userGoal.timestamp) < 5000;
                              return isUserSet ? 'group brightness' : 'avg brightness';
                            })()}
                          </div>
                        </div>
                      </div>

                      {/* Group Brightness Slider */}
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <label className="text-sm text-[#a1a1a6]">Group Brightness</label>
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium tabular-nums text-amber-400" title="Your setting (goal)">
                              Goal: {Math.round(avgBrightness)}%
                            </span>
                            <span className="text-sm text-[#636366]">→</span>
                            <span className="text-sm font-medium tabular-nums text-green-400" title="Average current level">
                              Now: {Math.round(getGroupCurrentBrightness(group))}%
                            </span>
                          </div>
                        </div>
                        <div className="relative h-2">
                          {/* Background showing current and goal */}
                          <div className="absolute top-0 left-0 right-0 h-2 bg-[#2a2a2f] rounded-full pointer-events-none">
                            <div
                              className="h-full bg-green-500/40 rounded-full transition-all duration-100"
                              style={{ width: `${getGroupCurrentBrightness(group)}%` }}
                              title={`Average current: ${Math.round(getGroupCurrentBrightness(group))}%`}
                            />
                          </div>
                          <input
                            type="range"
                            min="0"
                            max="100"
                            value={avgBrightness}
                            onChange={(e) => {
                              const value = parseInt(e.target.value) / 100;
                              sendGroupControl(group.id, value);
                            }}
                            className="absolute top-0 left-0 w-full h-2 bg-transparent rounded-full appearance-none cursor-pointer
                              [&::-webkit-slider-runnable-track]:h-2
                              [&::-webkit-slider-runnable-track]:rounded-full
                              [&::-webkit-slider-runnable-track]:bg-transparent
                              [&::-webkit-slider-thumb]:appearance-none
                              [&::-webkit-slider-thumb]:w-5
                              [&::-webkit-slider-thumb]:h-5
                              [&::-webkit-slider-thumb]:rounded-full
                              [&::-webkit-slider-thumb]:bg-amber-500
                              [&::-webkit-slider-thumb]:cursor-pointer
                              [&::-webkit-slider-thumb]:shadow-[0_2px_8px_rgba(0,0,0,0.3)]
                              [&::-webkit-slider-thumb]:border-2
                              [&::-webkit-slider-thumb]:border-amber-400"
                          />
                        </div>
                        <div className="flex justify-between mt-2">
                          {[0, 25, 50, 75, 100].map((val) => (
                            <button
                              key={val}
                              onClick={() => sendGroupControl(group.id, val / 100)}
                              className="px-3 py-1 text-xs font-medium rounded bg-[#2a2a2f] text-[#a1a1a6] hover:bg-[#3a3a3f] hover:text-white transition-colors"
                            >
                              {val}%
                            </button>
                          ))}
                        </div>
                      </div>

                      {/* Group CCT Slider - only shown if group has tunable white fixtures */}
                      {groupHasTunableFixtures(group) && (() => {
                        const groupCct = getGroupCct(group) ?? 3500;
                        const groupCurrentCct = getGroupCurrentCct(group) ?? 3500;
                        const { min: cctMin, max: cctMax } = getGroupCctRange(group);
                        return (
                          <div className="mt-4">
                            <div className="flex items-center justify-between mb-2">
                              <label className="text-sm text-[#a1a1a6]">Group Color Temperature</label>
                              <div className="flex items-center gap-2">
                                <span className="text-sm font-medium tabular-nums text-amber-400" title="Your setting (goal)">
                                  Goal: {groupCct}K
                                </span>
                                <span className="text-sm text-[#636366]">→</span>
                                <span className="text-sm font-medium tabular-nums text-green-400" title="Average current level">
                                  Now: {groupCurrentCct}K
                                </span>
                              </div>
                            </div>
                            <div className="relative h-2">
                              {/* Background gradient with current position indicator */}
                              <div
                                className="absolute top-0 left-0 right-0 h-2 rounded-full pointer-events-none"
                                style={{
                                  background: `linear-gradient(to right, ${kelvinToColor(cctMin)}, ${kelvinToColor(cctMax)})`,
                                }}
                              >
                                {/* Current CCT indicator */}
                                <div
                                  className="absolute top-1/2 -translate-y-1/2 w-1.5 h-4 bg-green-400 rounded-full shadow-lg transition-all duration-100"
                                  style={{
                                    left: `${((groupCurrentCct - cctMin) / (cctMax - cctMin)) * 100}%`,
                                  }}
                                  title={`Average current: ${groupCurrentCct}K`}
                                />
                              </div>
                              <input
                                type="range"
                                min={cctMin}
                                max={cctMax}
                                value={groupCct}
                                onChange={(e) => {
                                  const value = parseInt(e.target.value);
                                  sendGroupCctControl(group.id, value);
                                }}
                                className="absolute top-0 left-0 w-full h-2 bg-transparent rounded-full appearance-none cursor-pointer
                                  [&::-webkit-slider-runnable-track]:h-2
                                  [&::-webkit-slider-runnable-track]:rounded-full
                                  [&::-webkit-slider-runnable-track]:bg-transparent
                                  [&::-webkit-slider-thumb]:appearance-none
                                  [&::-webkit-slider-thumb]:w-5
                                  [&::-webkit-slider-thumb]:h-5
                                  [&::-webkit-slider-thumb]:rounded-full
                                  [&::-webkit-slider-thumb]:bg-white
                                  [&::-webkit-slider-thumb]:border-2
                                  [&::-webkit-slider-thumb]:border-gray-600
                                  [&::-webkit-slider-thumb]:cursor-pointer
                                  [&::-webkit-slider-thumb]:shadow-[0_2px_8px_rgba(0,0,0,0.3)]"
                              />
                            </div>
                            <div className="flex justify-between mt-2">
                              {[cctMin, Math.round((cctMin + cctMax) / 2), cctMax].map((val) => (
                                <button
                                  key={val}
                                  onClick={() => sendGroupCctControl(group.id, val)}
                                  className="px-3 py-1 text-xs font-medium rounded bg-[#2a2a2f] text-[#a1a1a6] hover:bg-[#3a3a3f] hover:text-white transition-colors"
                                >
                                  {val}K
                                </button>
                              ))}
                            </div>
                          </div>
                        );
                      })()}
                    </div>

                    {/* Expanded Fixtures */}
                    {isExpanded && group.fixtures.length > 0 && (
                      <div className="border-t border-[#2a2a2f] p-5 pt-4">
                        <div className="text-xs font-medium text-[#636366] uppercase tracking-wider mb-3">
                          Fixtures in Group
                        </div>
                        <div className="space-y-3">
                          {group.fixtures.map((fixture) => {
                            const brightness = (fixture.state?.goal_brightness ?? 0) / 10;
                            const cct = fixture.state?.goal_cct ?? 2700;
                            const currentBrightness = (fixture.state?.current_brightness ?? 0) / 10;
                            const currentCct = fixture.state?.current_cct ?? 2700;
                            const isOn = brightness > 0;
                            const canDim = isDimmable(fixture);
                            const canTuneCct = supportsCct(fixture);
                            const cctMin = fixture.model?.cct_min_kelvin ?? 2700;
                            const cctMax = fixture.model?.cct_max_kelvin ?? 6500;
                            const hasOverride = fixture.state?.override_active;

                            return (
                              <div
                                key={fixture.id}
                                className={`bg-[#0f0f11] rounded-lg p-4 border ${
                                  hasOverride ? 'border-amber-500/40' : 'border-[#2a2a2f]'
                                }`}
                              >
                                <div className="flex items-start justify-between mb-3">
                                  <div className="flex items-center gap-3">
                                    <div
                                      className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                                        currentBrightness > 0 ? '' : 'bg-[#2a2a2f]'
                                      }`}
                                      style={{
                                        backgroundColor: currentBrightness > 0 ? kelvinToColor(currentCct) : undefined,
                                        opacity: currentBrightness > 0 ? 0.4 + (currentBrightness / 100) * 0.6 : 1,
                                      }}
                                    >
                                      <svg
                                        className={`w-4 h-4 ${isOn ? 'text-black' : 'text-[#636366]'}`}
                                        fill="currentColor"
                                        viewBox="0 0 24 24"
                                      >
                                        <path d="M12 2.25a.75.75 0 01.75.75v2.25a.75.75 0 01-1.5 0V3a.75.75 0 01.75-.75zM7.5 12a4.5 4.5 0 119 0 4.5 4.5 0 01-9 0z" />
                                      </svg>
                                    </div>
                                    <div>
                                      <div className="flex items-center gap-2">
                                        <span className="font-medium">{fixture.name}</span>
                                        {fixture.model && (
                                          <span className={`text-xs px-1.5 py-0.5 rounded border ${typeLabels[fixture.model.type].color}`}>
                                            {typeLabels[fixture.model.type].label}
                                          </span>
                                        )}
                                        {hasOverride && (
                                          <span className="text-xs px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30 flex items-center gap-1">
                                            <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                                              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-12a1 1 0 10-2 0v4a1 1 0 00.293.707l2.828 2.829a1 1 0 101.415-1.415L11 9.586V6z" clipRule="evenodd" />
                                            </svg>
                                            Override
                                            {fixture.state?.override_expires_at && (
                                              <span className="text-amber-300">
                                                ({formatTimeRemaining(fixture.state.override_expires_at)})
                                              </span>
                                            )}
                                          </span>
                                        )}
                                      </div>
                                      <span className="text-xs text-[#636366]">DMX {fixture.dmx_channel_start}</span>
                                    </div>
                                  </div>

                                  {hasOverride && (
                                    <button
                                      onClick={() => handleRemoveOverride(fixture.id)}
                                      className="text-xs px-2 py-1 rounded bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors"
                                    >
                                      Remove Override
                                    </button>
                                  )}
                                </div>

                                {/* Fixture Controls */}
                                <div className="space-y-3">
                                  {canDim && (
                                    <div>
                                      <div className="flex items-center justify-between mb-1">
                                        <label className="text-xs text-[#a1a1a6]">Brightness</label>
                                        <div className="flex items-center gap-2">
                                          <span className="text-xs font-medium tabular-nums text-amber-400" title="Your setting (goal)">
                                            Goal: {Math.round(brightness)}%
                                          </span>
                                          <span className="text-xs text-[#636366]">→</span>
                                          <span className="text-xs font-medium tabular-nums text-green-400" title="Actual current level">
                                            Now: {Math.round(currentBrightness)}%
                                          </span>
                                        </div>
                                      </div>
                                      <div className="relative h-1.5">
                                        {/* Background showing current and goal */}
                                        <div className="absolute top-0 left-0 right-0 h-1.5 bg-[#2a2a2f] rounded-full pointer-events-none">
                                          <div
                                            className="h-full bg-green-500/40 rounded-full transition-all duration-100"
                                            style={{ width: `${currentBrightness}%` }}
                                            title={`Current: ${Math.round(currentBrightness)}%`}
                                          />
                                        </div>
                                        <input
                                          type="range"
                                          min="0"
                                          max="100"
                                          value={brightness}
                                          onChange={(e) => handleFixtureBrightnessChange(fixture, parseInt(e.target.value))}
                                          className="absolute top-0 left-0 w-full h-1.5 bg-transparent rounded-full appearance-none cursor-pointer
                                            [&::-webkit-slider-runnable-track]:h-1.5
                                            [&::-webkit-slider-runnable-track]:rounded-full
                                            [&::-webkit-slider-runnable-track]:bg-transparent
                                            [&::-webkit-slider-thumb]:appearance-none
                                            [&::-webkit-slider-thumb]:w-4
                                            [&::-webkit-slider-thumb]:h-4
                                            [&::-webkit-slider-thumb]:rounded-full
                                            [&::-webkit-slider-thumb]:bg-amber-500
                                            [&::-webkit-slider-thumb]:cursor-pointer
                                            [&::-webkit-slider-thumb]:shadow-[0_2px_6px_rgba(0,0,0,0.3)]
                                            [&::-webkit-slider-thumb]:border-2
                                            [&::-webkit-slider-thumb]:border-amber-400"
                                        />
                                      </div>
                                    </div>
                                  )}

                                  {canTuneCct && (
                                    <div>
                                      <div className="flex items-center justify-between mb-1">
                                        <label className="text-xs text-[#a1a1a6]">Color Temperature</label>
                                        <div className="flex items-center gap-2">
                                          <span className="text-xs font-medium tabular-nums text-amber-400" title="Your setting (goal)">
                                            Goal: {cct}K
                                          </span>
                                          <span className="text-xs text-[#636366]">→</span>
                                          <span className="text-xs font-medium tabular-nums text-green-400" title="Actual current level">
                                            Now: {currentCct}K
                                          </span>
                                        </div>
                                      </div>
                                      <div className="relative h-1.5">
                                        {/* Background gradient with current position indicator */}
                                        <div
                                          className="absolute top-0 left-0 right-0 h-1.5 rounded-full pointer-events-none"
                                          style={{
                                            background: `linear-gradient(to right, ${kelvinToColor(cctMin)}, ${kelvinToColor(cctMax)})`,
                                          }}
                                        >
                                          {/* Current CCT indicator */}
                                          <div
                                            className="absolute top-1/2 -translate-y-1/2 w-1 h-3 bg-green-400 rounded-full shadow-lg transition-all duration-100"
                                            style={{
                                              left: `${((currentCct - cctMin) / (cctMax - cctMin)) * 100}%`,
                                            }}
                                            title={`Current: ${currentCct}K`}
                                          />
                                        </div>
                                        <input
                                          type="range"
                                          min={cctMin}
                                          max={cctMax}
                                          value={cct}
                                          onChange={(e) => handleFixtureCctChange(fixture, parseInt(e.target.value))}
                                          className="absolute top-0 left-0 w-full h-1.5 bg-transparent rounded-full appearance-none cursor-pointer
                                            [&::-webkit-slider-runnable-track]:h-1.5
                                            [&::-webkit-slider-runnable-track]:rounded-full
                                            [&::-webkit-slider-runnable-track]:bg-transparent
                                            [&::-webkit-slider-thumb]:appearance-none
                                            [&::-webkit-slider-thumb]:w-4
                                            [&::-webkit-slider-thumb]:h-4
                                            [&::-webkit-slider-thumb]:rounded-full
                                            [&::-webkit-slider-thumb]:bg-white
                                            [&::-webkit-slider-thumb]:border-2
                                            [&::-webkit-slider-thumb]:border-gray-600
                                            [&::-webkit-slider-thumb]:cursor-pointer
                                            [&::-webkit-slider-thumb]:shadow-[0_2px_6px_rgba(0,0,0,0.3)]"
                                        />
                                      </div>
                                    </div>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
