'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

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
  // Goal state (what user/scene requested - used for slider position)
  goal_brightness: number;
  goal_cct: number;
  // Current state (actual output, may be transitioning - used for visual feedback)
  current_brightness: number;
  current_cct: number;
  is_on: boolean;
}

interface Group {
  id: number;
  name: string;
}

interface FixtureWithState extends Fixture {
  model?: FixtureModel;
  state?: FixtureState;
}

// === Helper Functions ===

const kelvinToColor = (kelvin: number): string => {
  // Convert Kelvin to approximate RGB color for visualization
  // Clamp to reasonable range (1000K - 40000K)
  const clampedKelvin = Math.max(1000, Math.min(40000, kelvin));
  const temp = clampedKelvin / 100;
  let r: number, g: number, b: number;

  if (temp <= 66) {
    r = 255;
    // For very warm temps (< 20), use a more amber-friendly formula
    if (temp <= 20) {
      // Linear interpolation for very warm colors (1000K-2000K)
      // At 1000K (temp=10): g ≈ 56 (deep amber)
      // At 2000K (temp=20): g ≈ 137 (warm orange)
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

type ControlMode = 'cct' | 'channel';

export default function LightTestPage() {
  const [fixtures, setFixtures] = useState<FixtureWithState[]>([]);
  const [fixtureModels, setFixtureModels] = useState<FixtureModel[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Track control mode per fixture (cct = CCT slider, channel = direct DMX control)
  const [controlModes, setControlModes] = useState<Record<number, ControlMode>>({});

  // Track channel overrides when in channel mode (to prevent slider jumping from rounding)
  const [channelOverrides, setChannelOverrides] = useState<Record<number, { warm: number; cool: number }>>({});

  // Track pending changes for debouncing
  const pendingChanges = useRef<Map<number, { brightness?: number; cct?: number }>>(new Map());
  const debounceTimers = useRef<Map<number, NodeJS.Timeout>>(new Map());

  // Track user-set goal values to prevent polling from overwriting them
  // Key: fixture_id, Value: { brightness: 0-100, cct: Kelvin, timestamp: ms }
  const userGoalState = useRef<Map<number, { brightness: number; cct: number; timestamp: number }>>(new Map());

  // Fetch data
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
      setGroups(groupsData);

      // Fetch state for each fixture
      const now = Date.now();
      const fixturesWithState: FixtureWithState[] = await Promise.all(
        fixturesData.map(async (fixture: Fixture) => {
          const model = modelsData.find((m: FixtureModel) => m.id === fixture.fixture_model_id);
          let state: FixtureState | undefined;

          try {
            const stateRes = await fetch(`${API_URL}/api/fixtures/${fixture.id}/state`);
            if (stateRes.ok) {
              const fetchedState = await stateRes.json();

              // Check if user has set goal values recently (within 500ms)
              // If so, preserve user's goal values instead of overwriting with polled values
              const userGoal = userGoalState.current.get(fixture.id);
              const isUserControlling = userGoal && (now - userGoal.timestamp) < 500;

              state = {
                fixture_id: fixture.id,
                // Use user's goal values if they're actively controlling, otherwise use API goal values
                goal_brightness: isUserControlling ? userGoal.brightness * 10 : fetchedState.goal_brightness ?? 0,
                goal_cct: isUserControlling ? userGoal.cct : fetchedState.goal_cct ?? 2700,
                // Current state always comes from the backend (for visual feedback)
                current_brightness: fetchedState.current_brightness ?? 0,
                current_cct: fetchedState.current_cct ?? 2700,
                is_on: (fetchedState.current_brightness ?? 0) > 0,
              };
            }
          } catch {
            // State might not exist yet
          }

          return { ...fixture, model, state };
        })
      );

      setFixtures(fixturesWithState);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load fixtures');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Track if we've initialized the lights to default state
  const hasInitialized = useRef(false);

  useEffect(() => {
    fetchData();
    // Poll for state updates every 2 seconds
    const interval = setInterval(fetchData, 2000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Initialize all lights to off at 2900K on first load
  useEffect(() => {
    if (hasInitialized.current || fixtures.length === 0) return;
    hasInitialized.current = true;

    const initializeLights = async () => {
      try {
        // Turn all lights off
        await fetch(`${API_URL}/api/control/all-off`, { method: 'POST' });

        // Set all fixtures to 2900K CCT
        await Promise.all(
          fixtures.map(fixture =>
            fetch(`${API_URL}/api/control/fixtures/${fixture.id}`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ brightness: 0, color_temp: 2900 }),
            })
          )
        );

        // Update local state
        setFixtures(prev => prev.map(f => ({
          ...f,
          state: {
            fixture_id: f.id,
            goal_brightness: 0,
            goal_cct: 2900,
            current_brightness: 0,
            current_cct: 2900,
            is_on: false,
          },
        })));
      } catch (err) {
        console.error('Failed to initialize lights:', err);
      }
    };

    initializeLights();
  }, [fixtures.length]);

  // Send control command with debouncing
  const sendControl = useCallback(async (fixtureId: number, brightness?: number, colorTemp?: number) => {
    // Clear existing timer
    const existingTimer = debounceTimers.current.get(fixtureId);
    if (existingTimer) {
      clearTimeout(existingTimer);
    }

    // Merge with pending changes
    const pending = pendingChanges.current.get(fixtureId) || {};
    if (brightness !== undefined) pending.brightness = brightness;
    if (colorTemp !== undefined) pending.cct = colorTemp;
    pendingChanges.current.set(fixtureId, pending);

    // Debounce the API call
    const timer = setTimeout(async () => {
      const changes = pendingChanges.current.get(fixtureId);
      if (!changes) return;

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
        console.error('Control error:', err);
      }
    }, 50); // 50ms debounce for smooth slider feel

    debounceTimers.current.set(fixtureId, timer);
  }, []);

  // Update local state immediately for responsive UI
  // Note: brightness param is 0-100 from UI, convert to 0-1000 for internal storage
  const updateFixtureState = useCallback((fixtureId: number, brightness?: number, cct?: number) => {
    // Record user's goal values with timestamp to prevent polling from overwriting
    const existing = userGoalState.current.get(fixtureId);
    userGoalState.current.set(fixtureId, {
      brightness: brightness ?? (existing?.brightness ?? 0),
      cct: cct ?? (existing?.cct ?? 2700),
      timestamp: Date.now(),
    });

    setFixtures(prev => prev.map(f => {
      if (f.id !== fixtureId) return f;
      const newGoalBrightness = brightness !== undefined ? brightness * 10 : f.state?.goal_brightness ?? 0;
      const newGoalCct = cct ?? f.state?.goal_cct ?? 2700;
      return {
        ...f,
        state: {
          fixture_id: fixtureId,
          // Update goal state (what sliders show)
          goal_brightness: newGoalBrightness,
          goal_cct: newGoalCct,
          // Current state stays the same until next poll (visual feedback)
          current_brightness: f.state?.current_brightness ?? 0,
          current_cct: f.state?.current_cct ?? 2700,
          is_on: newGoalBrightness > 0,
        },
      };
    }));
  }, []);

  // Handle brightness change
  const handleBrightnessChange = useCallback((fixture: FixtureWithState, value: number) => {
    const normalizedValue = value / 100; // Convert 0-100 to 0-1
    updateFixtureState(fixture.id, value);
    sendControl(fixture.id, normalizedValue);
  }, [sendControl, updateFixtureState]);

  // Handle CCT change
  const handleCctChange = useCallback((fixture: FixtureWithState, value: number) => {
    updateFixtureState(fixture.id, undefined, value);
    sendControl(fixture.id, undefined, value);
  }, [sendControl, updateFixtureState]);

  // Handle toggle
  const handleToggle = useCallback((fixture: FixtureWithState) => {
    const isOn = (fixture.state?.current_brightness ?? 0) > 0;
    const newBrightness = isOn ? 0 : 100;
    updateFixtureState(fixture.id, newBrightness);
    sendControl(fixture.id, newBrightness / 100);
  }, [sendControl, updateFixtureState]);

  // Quick actions
  const handleAllOff = useCallback(async () => {
    try {
      await fetch(`${API_URL}/api/control/all-off`, { method: 'POST' });
      // Clear user goal tracking since this is a bulk action
      userGoalState.current.clear();
      setFixtures(prev => prev.map(f => ({
        ...f,
        state: {
          ...f.state!,
          goal_brightness: 0,
          current_brightness: 0,
          is_on: false,
        },
      })));
    } catch (err) {
      console.error('All off error:', err);
    }
  }, []);

  const handleAllOn = useCallback(async () => {
    try {
      await fetch(`${API_URL}/api/control/panic`, { method: 'POST' });
      // Clear user goal tracking since this is a bulk action
      userGoalState.current.clear();
      setFixtures(prev => prev.map(f => ({
        ...f,
        state: {
          ...f.state!,
          goal_brightness: 1000,  // 1000 = 100%
          current_brightness: 1000,
          is_on: true,
        },
      })));
    } catch (err) {
      console.error('All on error:', err);
    }
  }, []);

  // Check if fixture supports CCT
  const supportsCct = (fixture: FixtureWithState): boolean => {
    return fixture.model?.type === 'tunable_white';
  };

  // Check if fixture is dimmable
  const isDimmable = (fixture: FixtureWithState): boolean => {
    return fixture.model?.type !== 'non_dimmable';
  };

  return (
    <div className="min-h-screen bg-[#0a0a0b] text-white flex">
      {/* Sidebar */}
      <aside className="w-64 bg-[#111113] border-r border-[#1f1f24] flex flex-col">
        {/* Logo */}
        <div className="p-5 border-b border-[#1f1f24]">
          <Link href="/" className="flex items-center gap-3">
            <div className="w-9 h-9 bg-gradient-to-br from-amber-500 to-amber-700 rounded-lg flex items-center justify-center">
              <svg className="w-5 h-5 fill-[#0a0a0b]" viewBox="0 0 24 24">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
              </svg>
            </div>
            <span className="text-lg font-semibold">Light Test</span>
          </Link>
        </div>

        {/* Quick Actions */}
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

        {/* Stats */}
        <div className="p-4 border-b border-[#1f1f24]">
          <h3 className="text-xs font-medium text-[#636366] uppercase tracking-wider mb-3">Status</h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-[#a1a1a6]">Fixtures</span>
              <span className="font-medium">{fixtures.length}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[#a1a1a6]">Lights On</span>
              <span className="font-medium text-amber-400">
                {fixtures.filter(f => (f.state?.current_brightness ?? 0) > 0).length}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-[#a1a1a6]">Groups</span>
              <span className="font-medium">{groups.length}</span>
            </div>
          </div>
        </div>

        {/* Footer links */}
        <div className="mt-auto p-4 border-t border-[#1f1f24] space-y-1">
          <Link
            href="/config/fixtures"
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-[#636366] hover:text-white hover:bg-white/5 transition-all"
          >
            <svg className="w-5 h-5 stroke-current" fill="none" strokeWidth="1.5" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            Configure Fixtures
          </Link>
          <Link
            href="/dashboard"
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-[#636366] hover:text-white hover:bg-white/5 transition-all"
          >
            <svg className="w-5 h-5 stroke-current" fill="none" strokeWidth="1.5" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
            </svg>
            Dashboard
          </Link>
          <Link
            href="/"
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-[#636366] hover:text-white hover:bg-white/5 transition-all"
          >
            <svg className="w-5 h-5 stroke-current" fill="none" strokeWidth="1.5" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
            </svg>
            Home
          </Link>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="p-8">
          <div className="mb-8">
            <h1 className="text-3xl font-bold">Light Testing</h1>
            <p className="text-[#636366] mt-1">Control and test your lighting fixtures</p>
          </div>

          {/* Error Banner */}
          {error && (
            <div className="mb-6 px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
              {error}
            </div>
          )}

          {/* Loading State */}
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin"></div>
            </div>
          ) : fixtures.length === 0 ? (
            <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] p-12 text-center">
              <div className="w-16 h-16 mx-auto mb-4 text-[#636366]">
                <svg fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 18v-5.25m0 0a6.01 6.01 0 001.5-.189m-1.5.189a6.01 6.01 0 01-1.5-.189m3.75 7.478a12.06 12.06 0 01-4.5 0m3.75 2.383a14.406 14.406 0 01-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 10-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold mb-2">No Fixtures Configured</h3>
              <p className="text-[#636366] mb-4">Add fixtures to start testing lights.</p>
              <Link
                href="/config/fixtures"
                className="inline-flex items-center gap-2 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors"
              >
                Configure Fixtures
              </Link>
            </div>
          ) : (
            <div className="grid gap-4">
              {fixtures.map((fixture) => {
                // Backend stores brightness as 0-1000, convert to 0-100 for display
                // Use GOAL brightness for slider position (what user set)
                const brightness = (fixture.state?.goal_brightness ?? 0) / 10;
                const cct = fixture.state?.goal_cct ?? 2700;
                // Use CURRENT brightness for visual feedback (actual light output)
                const currentBrightness = (fixture.state?.current_brightness ?? 0) / 10;
                const currentCct = fixture.state?.current_cct ?? 2700;
                const isOn = brightness > 0;
                const canDim = isDimmable(fixture);
                const canTuneCct = supportsCct(fixture);
                const cctMin = fixture.model?.cct_min_kelvin ?? 2700;
                const cctMax = fixture.model?.cct_max_kelvin ?? 6500;

                return (
                  <div
                    key={fixture.id}
                    className={`bg-[#1a1a1f] rounded-xl border transition-all ${
                      isOn ? 'border-amber-500/30' : 'border-[#2a2a2f]'
                    }`}
                  >
                    <div className="p-5">
                      {/* Header */}
                      <div className="flex items-start justify-between mb-4">
                        <div className="flex items-center gap-3">
                          {/* Light indicator - uses CURRENT state for actual visual feedback */}
                          <div
                            className={`w-12 h-12 rounded-xl flex items-center justify-center transition-all ${
                              currentBrightness > 0 ? 'shadow-lg' : 'bg-[#2a2a2f]'
                            }`}
                            style={{
                              backgroundColor: currentBrightness > 0
                                ? kelvinToColor(currentCct)
                                : undefined,
                              opacity: currentBrightness > 0 ? 0.3 + (currentBrightness / 100) * 0.7 : 1,
                            }}
                          >
                            <svg
                              className={`w-6 h-6 transition-colors ${
                                isOn ? 'text-black' : 'text-[#636366]'
                              }`}
                              fill="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path d="M12 2.25a.75.75 0 01.75.75v2.25a.75.75 0 01-1.5 0V3a.75.75 0 01.75-.75zM7.5 12a4.5 4.5 0 119 0 4.5 4.5 0 01-9 0zM18.894 6.166a.75.75 0 00-1.06-1.06l-1.591 1.59a.75.75 0 101.06 1.061l1.591-1.59zM21.75 12a.75.75 0 01-.75.75h-2.25a.75.75 0 010-1.5H21a.75.75 0 01.75.75zM17.834 18.894a.75.75 0 001.06-1.06l-1.59-1.591a.75.75 0 10-1.061 1.06l1.59 1.591zM12 18a.75.75 0 01.75.75V21a.75.75 0 01-1.5 0v-2.25A.75.75 0 0112 18zM7.758 17.303a.75.75 0 00-1.061-1.06l-1.591 1.59a.75.75 0 001.06 1.061l1.591-1.59zM6 12a.75.75 0 01-.75.75H3a.75.75 0 010-1.5h2.25A.75.75 0 016 12zM6.697 7.757a.75.75 0 001.06-1.06l-1.59-1.591a.75.75 0 00-1.061 1.06l1.59 1.591z" />
                            </svg>
                          </div>

                          <div>
                            <h3 className="font-semibold text-lg">{fixture.name}</h3>
                            <div className="flex items-center gap-2 mt-1">
                              <span className="text-xs text-[#636366]">DMX {fixture.dmx_channel_start}</span>
                              {fixture.secondary_dmx_channel && (
                                <span className="text-xs text-amber-400">+{fixture.secondary_dmx_channel}</span>
                              )}
                              {fixture.model && (
                                <span className={`text-xs px-2 py-0.5 rounded-full border ${typeLabels[fixture.model.type].color}`}>
                                  {typeLabels[fixture.model.type].label}
                                </span>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* On/Off Toggle */}
                        <button
                          onClick={() => handleToggle(fixture)}
                          className={`relative w-14 h-8 rounded-full transition-colors ${
                            isOn ? 'bg-amber-500' : 'bg-[#3a3a3f]'
                          }`}
                        >
                          <div
                            className={`absolute top-1 w-6 h-6 bg-white rounded-full shadow transition-transform ${
                              isOn ? 'translate-x-7' : 'translate-x-1'
                            }`}
                          />
                        </button>
                      </div>

                      {/* Controls */}
                      <div className="space-y-4">
                        {/* Brightness Slider */}
                        {canDim && (
                          <div>
                            <div className="flex items-center justify-between mb-2">
                              <label className="text-sm text-[#a1a1a6]">Brightness</label>
                              <span className="text-sm font-medium tabular-nums">{Math.round(brightness)}%</span>
                            </div>
                            <input
                              type="range"
                              min="0"
                              max="100"
                              value={brightness}
                              onChange={(e) => handleBrightnessChange(fixture, parseInt(e.target.value))}
                              className="w-full h-2 bg-[#2a2a2f] rounded-full appearance-none cursor-pointer
                                [&::-webkit-slider-thumb]:appearance-none
                                [&::-webkit-slider-thumb]:w-5
                                [&::-webkit-slider-thumb]:h-5
                                [&::-webkit-slider-thumb]:rounded-full
                                [&::-webkit-slider-thumb]:bg-amber-500
                                [&::-webkit-slider-thumb]:cursor-pointer
                                [&::-webkit-slider-thumb]:shadow-lg
                                [&::-webkit-slider-thumb]:transition-transform
                                [&::-webkit-slider-thumb]:hover:scale-110"
                              style={{
                                background: `linear-gradient(to right, #f59e0b ${brightness}%, #2a2a2f ${brightness}%)`,
                              }}
                            />
                            {/* Quick brightness buttons */}
                            <div className="flex gap-2 mt-2">
                              {[0, 25, 50, 75, 100].map((val) => (
                                <button
                                  key={val}
                                  onClick={() => handleBrightnessChange(fixture, val)}
                                  className={`flex-1 py-1.5 text-xs font-medium rounded transition-colors ${
                                    Math.round(brightness) === val
                                      ? 'bg-amber-500 text-black'
                                      : 'bg-[#2a2a2f] text-[#a1a1a6] hover:bg-[#3a3a3f] hover:text-white'
                                  }`}
                                >
                                  {val}%
                                </button>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Tunable White Controls */}
                        {canTuneCct && (() => {
                          const mode = controlModes[fixture.id] || 'cct';
                          const cctNormalized = Math.max(0, Math.min(1, (cct - cctMin) / (cctMax - cctMin)));
                          const dmxBrightness = (brightness / 100) * 255;

                          // Calculate channel values from brightness/CCT
                          const calculatedWarm = Math.round(dmxBrightness * (1 - cctNormalized));
                          const calculatedCool = Math.round(dmxBrightness * cctNormalized);

                          // Use overrides in channel mode to prevent slider jumping
                          const override = channelOverrides[fixture.id];
                          const warmLevel = mode === 'channel' && override ? override.warm : calculatedWarm;
                          const coolLevel = mode === 'channel' && override ? override.cool : calculatedCool;

                          const handleChannelChange = (channel: 'warm' | 'cool', value: number) => {
                            const newWarm = channel === 'warm' ? value : warmLevel;
                            const newCool = channel === 'cool' ? value : coolLevel;

                            // Store the override to prevent jumping
                            setChannelOverrides(prev => ({
                              ...prev,
                              [fixture.id]: { warm: newWarm, cool: newCool }
                            }));

                            const total = newWarm + newCool;

                            if (total === 0) {
                              handleBrightnessChange(fixture, 0);
                              return;
                            }

                            const newBrightness = Math.min(100, (total / 255) * 100);
                            const newCctNormalized = newCool / total;
                            const newCct = Math.round(cctMin + newCctNormalized * (cctMax - cctMin));

                            updateFixtureState(fixture.id, newBrightness, newCct);
                            sendControl(fixture.id, newBrightness / 100, newCct);
                          };

                          const handleModeSwitch = (newMode: ControlMode) => {
                            if (newMode === 'cct') {
                              // Clear overrides when switching to CCT mode
                              setChannelOverrides(prev => {
                                const next = { ...prev };
                                delete next[fixture.id];
                                return next;
                              });
                            } else {
                              // Initialize overrides with current calculated values when entering channel mode
                              setChannelOverrides(prev => ({
                                ...prev,
                                [fixture.id]: { warm: calculatedWarm, cool: calculatedCool }
                              }));
                            }
                            setControlModes(prev => ({ ...prev, [fixture.id]: newMode }));
                          };

                          return (
                            <div>
                              {/* Mode Toggle */}
                              <div className="flex items-center gap-2 mb-3">
                                <button
                                  onClick={() => handleModeSwitch('cct')}
                                  className={`flex-1 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                                    mode === 'cct'
                                      ? 'bg-amber-500/20 text-amber-400 border border-amber-500/40'
                                      : 'bg-[#2a2a2f] text-[#636366] hover:text-[#a1a1a6]'
                                  }`}
                                >
                                  CCT Mode
                                </button>
                                <button
                                  onClick={() => handleModeSwitch('channel')}
                                  className={`flex-1 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                                    mode === 'channel'
                                      ? 'bg-blue-500/20 text-blue-400 border border-blue-500/40'
                                      : 'bg-[#2a2a2f] text-[#636366] hover:text-[#a1a1a6]'
                                  }`}
                                >
                                  Channel Mode
                                </button>
                              </div>

                              {mode === 'cct' ? (
                                <>
                                  {/* CCT Slider */}
                                  <div className="flex items-center justify-between mb-2">
                                    <label className="text-sm text-[#a1a1a6]">Color Temperature</label>
                                    <span className="text-sm font-medium tabular-nums">{cct}K</span>
                                  </div>
                                  <div className="relative">
                                    <input
                                      type="range"
                                      min={cctMin}
                                      max={cctMax}
                                      value={cct}
                                      onChange={(e) => handleCctChange(fixture, parseInt(e.target.value))}
                                      className="w-full h-2 rounded-full appearance-none cursor-pointer
                                        [&::-webkit-slider-thumb]:appearance-none
                                        [&::-webkit-slider-thumb]:w-5
                                        [&::-webkit-slider-thumb]:h-5
                                        [&::-webkit-slider-thumb]:rounded-full
                                        [&::-webkit-slider-thumb]:bg-white
                                        [&::-webkit-slider-thumb]:border-2
                                        [&::-webkit-slider-thumb]:border-[#636366]
                                        [&::-webkit-slider-thumb]:cursor-pointer
                                        [&::-webkit-slider-thumb]:shadow-lg
                                        [&::-webkit-slider-thumb]:transition-transform
                                        [&::-webkit-slider-thumb]:hover:scale-110"
                                      style={{
                                        background: `linear-gradient(to right, ${kelvinToColor(cctMin)}, ${kelvinToColor((cctMin + cctMax) / 2)}, ${kelvinToColor(cctMax)})`,
                                      }}
                                    />
                                  </div>
                                  {/* CCT presets */}
                                  <div className="flex gap-2 mt-2">
                                    {[
                                      { label: 'Warm', value: cctMin },
                                      { label: 'Neutral', value: Math.round((cctMin + cctMax) / 2) },
                                      { label: 'Cool', value: cctMax },
                                    ].map((preset) => (
                                      <button
                                        key={preset.label}
                                        onClick={() => handleCctChange(fixture, preset.value)}
                                        className={`flex-1 py-1.5 text-xs font-medium rounded transition-colors ${
                                          Math.abs(cct - preset.value) < 100
                                            ? 'bg-white/10 text-white border border-white/20'
                                            : 'bg-[#2a2a2f] text-[#a1a1a6] hover:bg-[#3a3a3f] hover:text-white'
                                        }`}
                                      >
                                        {preset.label}
                                      </button>
                                    ))}
                                  </div>

                                  {/* Read-only Channel Power Levels */}
                                  <div className="mt-4 pt-4 border-t border-[#2a2a2f]">
                                    <div className="text-xs text-[#636366] mb-2">DMX Channel Output</div>
                                    <div className="grid grid-cols-2 gap-3">
                                      <div className="bg-[#2a2a2f] rounded-lg p-3">
                                        <div className="flex items-center justify-between mb-1.5">
                                          <span className="text-xs text-[#a1a1a6]">CH {fixture.dmx_channel_start}</span>
                                          <span className="text-xs font-medium text-amber-400">Warm</span>
                                        </div>
                                        <div className="flex items-center gap-2">
                                          <div className="flex-1 h-2 bg-[#1a1a1f] rounded-full overflow-hidden">
                                            <div
                                              className="h-full bg-gradient-to-r from-amber-600 to-amber-400 transition-all"
                                              style={{ width: `${(warmLevel / 255) * 100}%` }}
                                            />
                                          </div>
                                          <span className="text-sm font-mono font-medium w-10 text-right">{warmLevel}</span>
                                        </div>
                                      </div>
                                      <div className="bg-[#2a2a2f] rounded-lg p-3">
                                        <div className="flex items-center justify-between mb-1.5">
                                          <span className="text-xs text-[#a1a1a6]">CH {fixture.secondary_dmx_channel}</span>
                                          <span className="text-xs font-medium text-blue-400">Cool</span>
                                        </div>
                                        <div className="flex items-center gap-2">
                                          <div className="flex-1 h-2 bg-[#1a1a1f] rounded-full overflow-hidden">
                                            <div
                                              className="h-full bg-gradient-to-r from-blue-600 to-blue-400 transition-all"
                                              style={{ width: `${(coolLevel / 255) * 100}%` }}
                                            />
                                          </div>
                                          <span className="text-sm font-mono font-medium w-10 text-right">{coolLevel}</span>
                                        </div>
                                      </div>
                                    </div>
                                  </div>
                                </>
                              ) : (
                                /* Channel Mode - Direct DMX Control */
                                <div>
                                  <div className="text-xs text-[#636366] mb-2">DMX Channel Control</div>
                                  <div className="grid grid-cols-2 gap-3">
                                    {/* Warm Channel */}
                                    <div className="bg-[#2a2a2f] rounded-lg p-3">
                                      <div className="flex items-center justify-between mb-1.5">
                                        <span className="text-xs text-[#a1a1a6]">CH {fixture.dmx_channel_start}</span>
                                        <span className="text-xs font-medium text-amber-400">Warm</span>
                                      </div>
                                      <div className="flex items-center gap-2">
                                        <input
                                          type="range"
                                          min="0"
                                          max="255"
                                          value={warmLevel}
                                          onChange={(e) => handleChannelChange('warm', parseInt(e.target.value))}
                                          className="flex-1 h-2 bg-[#1a1a1f] rounded-full appearance-none cursor-pointer
                                            [&::-webkit-slider-thumb]:appearance-none
                                            [&::-webkit-slider-thumb]:w-4
                                            [&::-webkit-slider-thumb]:h-4
                                            [&::-webkit-slider-thumb]:rounded-full
                                            [&::-webkit-slider-thumb]:bg-amber-500
                                            [&::-webkit-slider-thumb]:cursor-pointer
                                            [&::-webkit-slider-thumb]:shadow-lg"
                                          style={{
                                            background: `linear-gradient(to right, #f59e0b ${(warmLevel / 255) * 100}%, #1a1a1f ${(warmLevel / 255) * 100}%)`,
                                          }}
                                        />
                                        <span className="text-sm font-mono font-medium w-10 text-right">{warmLevel}</span>
                                      </div>
                                    </div>
                                    {/* Cool Channel */}
                                    <div className="bg-[#2a2a2f] rounded-lg p-3">
                                      <div className="flex items-center justify-between mb-1.5">
                                        <span className="text-xs text-[#a1a1a6]">CH {fixture.secondary_dmx_channel}</span>
                                        <span className="text-xs font-medium text-blue-400">Cool</span>
                                      </div>
                                      <div className="flex items-center gap-2">
                                        <input
                                          type="range"
                                          min="0"
                                          max="255"
                                          value={coolLevel}
                                          onChange={(e) => handleChannelChange('cool', parseInt(e.target.value))}
                                          className="flex-1 h-2 bg-[#1a1a1f] rounded-full appearance-none cursor-pointer
                                            [&::-webkit-slider-thumb]:appearance-none
                                            [&::-webkit-slider-thumb]:w-4
                                            [&::-webkit-slider-thumb]:h-4
                                            [&::-webkit-slider-thumb]:rounded-full
                                            [&::-webkit-slider-thumb]:bg-blue-500
                                            [&::-webkit-slider-thumb]:cursor-pointer
                                            [&::-webkit-slider-thumb]:shadow-lg"
                                          style={{
                                            background: `linear-gradient(to right, #3b82f6 ${(coolLevel / 255) * 100}%, #1a1a1f ${(coolLevel / 255) * 100}%)`,
                                          }}
                                        />
                                        <span className="text-sm font-mono font-medium w-10 text-right">{coolLevel}</span>
                                      </div>
                                    </div>
                                  </div>
                                  {/* Show computed CCT/Brightness in channel mode */}
                                  <div className="mt-3 flex items-center justify-center gap-4 text-xs text-[#636366]">
                                    <span>≈ {Math.round(brightness)}% brightness</span>
                                    <span>≈ {cct}K</span>
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })()}
                      </div>
                    </div>
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
