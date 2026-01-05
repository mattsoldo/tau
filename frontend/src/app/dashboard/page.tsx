'use client';

import { useEffect, useState, useRef, useMemo, useCallback } from 'react';

const API_URL = ''; // Use relative paths for nginx proxy

// Timing constants (PRD Section 10.1-10.2)
const TAP_WINDOW_MS = 500;
const RAMP_INTERVAL_MS = 50;
const SLIDER_DEBOUNCE_MS = 150; // Debounce slider API calls
const RAMP_STEP = 2;
const SCENE_1_BRIGHTNESS = 75;
const SCENE_2_BRIGHTNESS = 25;

// Error dismiss timeouts
const ERROR_DISMISS_MS = 3000;
const VALIDATION_ERROR_DISMISS_MS = 2000;

// Data polling intervals
const STATUS_POLL_INTERVAL_MS = 2000;
const OVERRIDES_POLL_INTERVAL_MS = 2000;

// Brightness scaling constants
const BRIGHTNESS_SCALE = 1000; // API uses 0-1000 scale
const BRIGHTNESS_DISPLAY_SCALE = 10; // Display uses 0-100, state uses 0-1000

interface SystemStatus {
  status: string;
  version: string;
  service: string;
  event_loop?: {
    iterations: number;
    total_time_s: number;
    avg_time_ms: number;
    min_time_ms: number;
    max_time_ms: number;
    frequency_hz: number;
    running: boolean;
  };
  hardware?: {
    labjack: {
      connected: boolean;
      model: string;
      serial_number: string;
      read_count: number;
      write_count: number;
      error_count: number;
      digital_inputs: Record<string, boolean>;
    };
    ola: {
      connected: boolean;
      max_universes: number;
      channel_set_count: number;
      non_zero_channels: number;
      error_count: number;
    };
    health_checks: {
      passed: number;
      failed: number;
    };
    overall_healthy: boolean;
  };
  lighting?: {
    hardware_updates: number;
    circadian: {
      profiles_loaded: number;
    };
    scenes: {
      scenes_recalled: number;
    };
    switches: {
      events_processed: number;
    };
  };
}

interface Fixture {
  id: number;
  name: string;
  dmx_channel_start: number;
  fixture_model_id: number;
}

interface FixtureModel {
  id: number;
  cct_min_kelvin: number;
  cct_max_kelvin: number;
}

interface FixtureState {
  fixture_id: number;
  goal_brightness: number;
  goal_cct: number;
  current_brightness: number;
  current_cct: number;
  is_on: boolean;
}

interface Group {
  id: number;
  name: string;
  is_system: boolean;
  circadian_enabled: boolean;
}

interface ActiveOverride {
  fixture_id: number;
  override_source: string;
  expires_at: number;
  time_remaining_hours: number;
}

interface LightState {
  brightness: number;
  lightOn: boolean;
  scene: 'off' | 'full' | 'scene1' | 'scene2' | 'custom';
}

function formatNumber(num: number): string {
  if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
  if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
  return num.toString();
}

function formatUptime(seconds: number): string {
  if (seconds >= 3600) return (seconds / 3600).toFixed(1) + 'h';
  if (seconds >= 60) return (seconds / 60).toFixed(1) + 'm';
  return seconds.toFixed(0) + 's';
}

export default function DashboardPage() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [fixtures, setFixtures] = useState<Fixture[]>([]);
  const [fixtureStates, setFixtureStates] = useState<Map<number, FixtureState>>(new Map());
  const [fixtureModels, setFixtureModels] = useState<Map<number, FixtureModel>>(new Map());
  const [groups, setGroups] = useState<Group[]>([]);
  const [groupFixtures, setGroupFixtures] = useState<Map<number, Fixture[]>>(new Map());
  const [activeOverrides, setActiveOverrides] = useState<ActiveOverride[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [expandedFixtures, setExpandedFixtures] = useState<Set<number>>(new Set());
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set());
  const [editingBrightness, setEditingBrightness] = useState<{ type: 'fixture' | 'group'; id: number } | null>(null);
  const [brightnessInputValue, setBrightnessInputValue] = useState('');
  const [controlError, setControlError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  // Request version refs for race condition handling
  const requestVersionRef = useRef<Map<string, number>>(new Map());
  const mountedRef = useRef(true);

  // Auto-dismiss control errors
  useEffect(() => {
    if (controlError) {
      const timeout = setTimeout(() => setControlError(null), ERROR_DISMISS_MS);
      return () => clearTimeout(timeout);
    }
  }, [controlError]);

  // Auto-dismiss validation errors
  useEffect(() => {
    if (validationError) {
      const timeout = setTimeout(() => setValidationError(null), VALIDATION_ERROR_DISMISS_MS);
      return () => clearTimeout(timeout);
    }
  }, [validationError]);

  // Cleanup debounce timeouts on unmount
  useEffect(() => {
    mountedRef.current = true;
    const debounceRef = sliderDebounceRef.current;
    return () => {
      mountedRef.current = false;
      debounceRef.forEach(timeout => clearTimeout(timeout));
      debounceRef.clear();
    };
  }, []);

  // Light simulator state for each FIO channel
  const [lightStates, setLightStates] = useState<LightState[]>(
    Array(8).fill(null).map(() => ({ brightness: 0, lightOn: false, scene: 'off' as const }))
  );

  // Refs for tracking switch input state (not reactive, used in intervals)
  const switchRefs = useRef({
    lastState: Array(8).fill(false) as boolean[],
    pressTime: Array(8).fill(null) as (number | null)[],
    tapCount: Array(8).fill(0) as number[],
    holdInterval: Array(8).fill(null) as (ReturnType<typeof setTimeout> | null)[],
    tapTimeout: Array(8).fill(null) as (ReturnType<typeof setTimeout> | null)[],
    rampDirection: Array(8).fill(1) as number[],
  });

  // Refs for debouncing slider API calls
  const sliderDebounceRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  // Get current light state for a channel (for use in callbacks)
  const lightStatesRef = useRef(lightStates);
  lightStatesRef.current = lightStates;

  // Handle switch input for a channel (PRD Section 10.1)
  // This function is intentionally not wrapped in useCallback - it's called from refs
  const handleSwitchInput = (channel: number, switchPressed: boolean) => {
    const refs = switchRefs.current;
    const wasPressed = refs.lastState[channel];

    // Skip if no state change (edge detection)
    if (switchPressed === wasPressed) return;

    // Rising edge - switch pressed
    if (switchPressed && !wasPressed) {
      refs.pressTime[channel] = Date.now();

      // Start hold detection
      refs.holdInterval[channel] = setTimeout(() => {
        const currentState = lightStatesRef.current[channel];

        // Start ramping
        if (currentState.lightOn) {
          refs.rampDirection[channel] = -1; // Ramp down
        } else {
          refs.rampDirection[channel] = 1; // Ramp up
          setLightStates(prev => {
            const newStates = [...prev];
            newStates[channel] = { brightness: 0, lightOn: true, scene: 'custom' };
            return newStates;
          });
        }

        // Continuous ramping
        refs.holdInterval[channel] = setInterval(() => {
          setLightStates(prev => {
            const newStates = [...prev];
            const current = newStates[channel];
            const newBrightness = Math.max(0, Math.min(100, current.brightness + (refs.rampDirection[channel] * RAMP_STEP)));
            const lightOn = newBrightness > 0;

            let scene: LightState['scene'] = 'custom';
            if (!lightOn || newBrightness === 0) scene = 'off';
            else if (newBrightness === 100) scene = 'full';
            else if (newBrightness === SCENE_1_BRIGHTNESS) scene = 'scene1';
            else if (newBrightness === SCENE_2_BRIGHTNESS) scene = 'scene2';

            newStates[channel] = { brightness: newBrightness, lightOn, scene };
            return newStates;
          });
        }, RAMP_INTERVAL_MS);
      }, TAP_WINDOW_MS);
    }

    // Falling edge - switch released
    if (!switchPressed && wasPressed) {
      const pressDuration = Date.now() - (refs.pressTime[channel] || 0);

      // Clear hold interval
      if (refs.holdInterval[channel]) {
        clearTimeout(refs.holdInterval[channel]);
        clearInterval(refs.holdInterval[channel]);
        refs.holdInterval[channel] = null;
      }

      // Was it a tap?
      if (pressDuration < TAP_WINDOW_MS) {
        refs.tapCount[channel]++;

        // Clear existing tap timeout
        if (refs.tapTimeout[channel]) {
          clearTimeout(refs.tapTimeout[channel]);
        }

        // Wait for more taps or execute
        refs.tapTimeout[channel] = setTimeout(() => {
          const count = refs.tapCount[channel];
          refs.tapCount[channel] = 0;
          refs.tapTimeout[channel] = null;

          // Execute tap action inline (avoid stale closure)
          setLightStates(prev => {
            const newStates = [...prev];
            const current = newStates[channel];

            switch (count) {
              case 1:
                if (current.lightOn) {
                  newStates[channel] = { brightness: 0, lightOn: false, scene: 'off' };
                } else {
                  newStates[channel] = { brightness: 100, lightOn: true, scene: 'full' };
                }
                break;
              case 2:
                newStates[channel] = { brightness: SCENE_1_BRIGHTNESS, lightOn: true, scene: 'scene1' };
                break;
              default:
                newStates[channel] = { brightness: SCENE_2_BRIGHTNESS, lightOn: true, scene: 'scene2' };
                break;
            }
            return newStates;
          });
        }, TAP_WINDOW_MS);
      }
    }

    refs.lastState[channel] = switchPressed;
  };

  // Store digital inputs in ref to track across polls
  const digitalInputsRef = useRef<Record<string, boolean>>({});

  // Fast polling for digital inputs (100ms for responsive tap detection)
  useEffect(() => {
    let mounted = true;

    const pollDigitalInputs = async () => {
      if (!mounted) return;

      try {
        const response = await fetch(`${API_URL}/api/labjack/status`);
        if (!response.ok) return;

        const data = await response.json();
        const inputs = data.statistics?.digital_inputs || {};

        // Process each channel
        for (let i = 0; i < 8; i++) {
          const key = String(i);
          const isPressed = inputs[key] === true;
          handleSwitchInput(i, isPressed);
        }

        digitalInputsRef.current = inputs;
      } catch {
        // Ignore errors in fast poll
      }
    };

    // Poll every 100ms for responsive input detection
    const interval = setInterval(pollDigitalInputs, 100);
    pollDigitalInputs();

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [statusRes, fixturesRes, groupsRes, modelsRes] = await Promise.all([
          fetch(`${API_URL}/status`),
          fetch(`${API_URL}/api/fixtures/`),
          fetch(`${API_URL}/api/groups/`),
          fetch(`${API_URL}/api/fixtures/models`),
        ]);

        if (!statusRes.ok) throw new Error('Status API error');

        setStatus(await statusRes.json());
        const fixturesData = await fixturesRes.json();
        setFixtures(fixturesData);
        const groupsData = await groupsRes.json();
        setGroups(groupsData);

        // Build models map
        const modelsData = await modelsRes.json();
        const modelsMap = new Map<number, FixtureModel>();
        modelsData.forEach((m: FixtureModel) => modelsMap.set(m.id, m));
        setFixtureModels(modelsMap);

        // Fetch fixtures for each group
        const groupFixturesMap = new Map<number, Fixture[]>();
        const groupFixturesResults = await Promise.allSettled(
          groupsData.map(async (g: Group) => {
            const groupFixturesRes = await fetch(`${API_URL}/api/groups/${g.id}/fixtures`);
            if (groupFixturesRes.ok) {
              const groupFixturesData = await groupFixturesRes.json();
              return { groupId: g.id, fixtures: groupFixturesData };
            }
            return null;
          })
        );

        // Process successful fetches
        groupFixturesResults.forEach((result) => {
          if (result.status === 'fulfilled' && result.value) {
            groupFixturesMap.set(result.value.groupId, result.value.fixtures);
          }
        });
        setGroupFixtures(groupFixturesMap);

        // Fetch fixture states
        const statesMap = new Map<number, FixtureState>();
        const statesResults = await Promise.allSettled(
          fixturesData.map(async (f: Fixture) => {
            const stateRes = await fetch(`${API_URL}/api/fixtures/${f.id}/state`);
            if (stateRes.ok) {
              const state = await stateRes.json();
              return { fixtureId: f.id, state };
            }
            return null;
          })
        );

        // Process successful fetches
        statesResults.forEach((result) => {
          if (result.status === 'fulfilled' && result.value) {
            statesMap.set(result.value.fixtureId, result.value.state);
          }
        });
        setFixtureStates(statesMap);

        setError(null);
      } catch (err) {
        setError('Connection error');
      }
    };

    fetchData();
    const interval = setInterval(fetchData, STATUS_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  // Poll active overrides every 2 seconds
  useEffect(() => {
    const fetchOverrides = async () => {
      try {
        const response = await fetch(`${API_URL}/api/control/overrides`);
        if (response.ok) {
          const data = await response.json();
          setActiveOverrides(data.overrides || []);
        }
      } catch {
        // Ignore errors in override poll
      }
    };

    fetchOverrides();
    const interval = setInterval(fetchOverrides, OVERRIDES_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, []);

  // Remove individual fixture override
  const handleRemoveOverride = async (fixtureId: number) => {
    try {
      const response = await fetch(`${API_URL}/api/control/overrides/fixtures/${fixtureId}`, {
        method: 'DELETE',
      });
      if (response.ok) {
        setActiveOverrides(prev => prev.filter(o => o.fixture_id !== fixtureId));
      } else {
        const fixtureName = getFixtureName(fixtureId);
        setControlError(`Failed to remove override for ${fixtureName}`);
      }
    } catch (error) {
      const fixtureName = getFixtureName(fixtureId);
      setControlError(`Failed to remove override for ${fixtureName}`);
    }
  };

  // Remove all overrides
  const handleRemoveAllOverrides = async () => {
    try {
      const response = await fetch(`${API_URL}/api/control/overrides/all`, {
        method: 'DELETE',
      });
      if (response.ok) {
        setActiveOverrides([]);
      } else {
        setControlError('Failed to remove all overrides');
      }
    } catch (error) {
      setControlError('Failed to remove all overrides');
    }
  };

  // Get fixture name by ID
  const getFixtureName = (fixtureId: number): string => {
    const fixture = fixtures.find(f => f.id === fixtureId);
    return fixture?.name || `Fixture ${fixtureId}`;
  };

  // Format time remaining for override expiry
  const formatTimeRemaining = (expiresAt: number): string => {
    const now = Date.now() / 1000;
    const remaining = expiresAt - now;
    if (remaining <= 0) return 'Expiring...';
    const hours = Math.floor(remaining / 3600);
    const minutes = Math.floor((remaining % 3600) / 60);
    if (hours > 0) return `${hours}h ${minutes}m`;
    return `${minutes}m`;
  };

  // Toggle fixture on/off
  const handleFixtureToggle = async (fixtureId: number) => {
    const state = fixtureStates.get(fixtureId);
    const newBrightness = state?.is_on ? 0.0 : 1.0;
    try {
      const response = await fetch(`${API_URL}/api/control/fixtures/${fixtureId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brightness: newBrightness }),
      });
      if (!response.ok) {
        throw new Error(`Failed to toggle fixture: ${response.statusText}`);
      }
      // Optimistic update
      setFixtureStates(prev => {
        const newMap = new Map(prev);
        const existing = newMap.get(fixtureId);
        if (existing) {
          newMap.set(fixtureId, { ...existing, goal_brightness: newBrightness * BRIGHTNESS_SCALE, is_on: newBrightness > 0 });
        }
        return newMap;
      });
    } catch (err) {
      const fixtureName = getFixtureName(fixtureId);
      setControlError(`Failed to toggle ${fixtureName}`);
    }
  };

  // Control fixture brightness (debounced with race condition handling)
  const handleFixtureBrightness = useCallback((fixtureId: number, brightness: number) => {
    const key = `fixture-brightness-${fixtureId}`;

    // Increment request version for race condition handling
    const currentVersion = (requestVersionRef.current.get(key) || 0) + 1;
    requestVersionRef.current.set(key, currentVersion);

    // Optimistic UI update immediately
    setFixtureStates(prev => {
      const newMap = new Map(prev);
      const existing = newMap.get(fixtureId);
      if (existing) {
        newMap.set(fixtureId, { ...existing, goal_brightness: brightness * BRIGHTNESS_SCALE, is_on: brightness > 0 });
      }
      return newMap;
    });

    // Debounce API call
    const existingTimeout = sliderDebounceRef.current.get(key);
    if (existingTimeout) clearTimeout(existingTimeout);

    sliderDebounceRef.current.set(key, setTimeout(async () => {
      // Check if component is still mounted
      if (!mountedRef.current) return;

      // Check if this request is still the latest
      if (requestVersionRef.current.get(key) !== currentVersion) {
        return; // A newer request superseded this one
      }

      try {
        const response = await fetch(`${API_URL}/api/control/fixtures/${fixtureId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ brightness }),
        });
        if (!response.ok) {
          throw new Error(`Failed to set brightness: ${response.statusText}`);
        }
      } catch {
        if (!mountedRef.current) return;
        const fixtureName = getFixtureName(fixtureId);
        setControlError(`Failed to set brightness for ${fixtureName}`);
      }
    }, SLIDER_DEBOUNCE_MS));
  }, []);

  // Control fixture CCT (debounced with race condition handling)
  const handleFixtureCCT = useCallback((fixtureId: number, cct: number) => {
    const key = `fixture-cct-${fixtureId}`;

    // Increment request version for race condition handling
    const currentVersion = (requestVersionRef.current.get(key) || 0) + 1;
    requestVersionRef.current.set(key, currentVersion);

    // Optimistic UI update immediately
    setFixtureStates(prev => {
      const newMap = new Map(prev);
      const existing = newMap.get(fixtureId);
      if (existing) {
        newMap.set(fixtureId, { ...existing, goal_cct: cct });
      }
      return newMap;
    });

    // Debounce API call
    const existingTimeout = sliderDebounceRef.current.get(key);
    if (existingTimeout) clearTimeout(existingTimeout);

    sliderDebounceRef.current.set(key, setTimeout(async () => {
      // Check if component is still mounted
      if (!mountedRef.current) return;

      // Check if this request is still the latest
      if (requestVersionRef.current.get(key) !== currentVersion) {
        return; // A newer request superseded this one
      }

      try {
        const response = await fetch(`${API_URL}/api/control/fixtures/${fixtureId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ color_temp: cct }),
        });
        if (!response.ok) {
          throw new Error(`Failed to set CCT: ${response.statusText}`);
        }
      } catch {
        if (!mountedRef.current) return;
        const fixtureName = getFixtureName(fixtureId);
        setControlError(`Failed to set color temperature for ${fixtureName}`);
      }
    }, SLIDER_DEBOUNCE_MS));
  }, []);

  // Control group brightness (debounced with optimistic update and race condition handling)
  const handleGroupBrightness = useCallback((groupId: number, brightness: number) => {
    const key = `group-brightness-${groupId}`;

    // Increment request version for race condition handling
    const currentVersion = (requestVersionRef.current.get(key) || 0) + 1;
    requestVersionRef.current.set(key, currentVersion);

    // Optimistic UI update for all fixtures in group
    const fixturesInGroup = groupFixtures.get(groupId) || [];
    setFixtureStates(prev => {
      const newMap = new Map(prev);
      fixturesInGroup.forEach(fixture => {
        const existing = newMap.get(fixture.id);
        if (existing) {
          newMap.set(fixture.id, { ...existing, goal_brightness: brightness * BRIGHTNESS_SCALE, is_on: brightness > 0 });
        }
      });
      return newMap;
    });

    // Debounce API call
    const existingTimeout = sliderDebounceRef.current.get(key);
    if (existingTimeout) clearTimeout(existingTimeout);

    sliderDebounceRef.current.set(key, setTimeout(async () => {
      // Check if component is still mounted
      if (!mountedRef.current) return;

      // Check if this request is still the latest
      if (requestVersionRef.current.get(key) !== currentVersion) {
        return; // A newer request superseded this one
      }

      try {
        const response = await fetch(`${API_URL}/api/control/groups/${groupId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ brightness }),
        });
        if (!response.ok) {
          throw new Error(`Failed to set group brightness: ${response.statusText}`);
        }
      } catch {
        if (!mountedRef.current) return;
        const group = groups.find(g => g.id === groupId);
        setControlError(`Failed to set brightness for ${group?.name || 'group'}`);
      }
    }, SLIDER_DEBOUNCE_MS));
  }, [groupFixtures, groups]);

  // Control group CCT (debounced with optimistic update and race condition handling)
  const handleGroupCCT = useCallback((groupId: number, cct: number) => {
    const key = `group-cct-${groupId}`;

    // Increment request version for race condition handling
    const currentVersion = (requestVersionRef.current.get(key) || 0) + 1;
    requestVersionRef.current.set(key, currentVersion);

    // Optimistic UI update for all fixtures in group
    const fixturesInGroup = groupFixtures.get(groupId) || [];
    setFixtureStates(prev => {
      const newMap = new Map(prev);
      fixturesInGroup.forEach(fixture => {
        const existing = newMap.get(fixture.id);
        if (existing) {
          newMap.set(fixture.id, { ...existing, goal_cct: cct });
        }
      });
      return newMap;
    });

    // Debounce API call
    const existingTimeout = sliderDebounceRef.current.get(key);
    if (existingTimeout) clearTimeout(existingTimeout);

    sliderDebounceRef.current.set(key, setTimeout(async () => {
      // Check if component is still mounted
      if (!mountedRef.current) return;

      // Check if this request is still the latest
      if (requestVersionRef.current.get(key) !== currentVersion) {
        return; // A newer request superseded this one
      }

      try {
        const response = await fetch(`${API_URL}/api/control/groups/${groupId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ color_temp: cct }),
        });
        if (!response.ok) {
          throw new Error(`Failed to set group CCT: ${response.statusText}`);
        }
      } catch {
        if (!mountedRef.current) return;
        const group = groups.find(g => g.id === groupId);
        setControlError(`Failed to set color temperature for ${group?.name || 'group'}`);
      }
    }, SLIDER_DEBOUNCE_MS));
  }, [groupFixtures, groups]);

  // Toggle group on/off (with optimistic update)
  const handleGroupToggle = async (groupId: number, turnOn: boolean) => {
    const newBrightness = turnOn ? 1.0 : 0.0;

    // Optimistic UI update for all fixtures in group
    const fixturesInGroup = groupFixtures.get(groupId) || [];
    setFixtureStates(prev => {
      const newMap = new Map(prev);
      fixturesInGroup.forEach(fixture => {
        const existing = newMap.get(fixture.id);
        if (existing) {
          newMap.set(fixture.id, { ...existing, goal_brightness: newBrightness * BRIGHTNESS_SCALE, is_on: turnOn });
        }
      });
      return newMap;
    });

    try {
      const response = await fetch(`${API_URL}/api/control/groups/${groupId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brightness: newBrightness }),
      });
      if (!response.ok) {
        throw new Error(`Failed to toggle group: ${response.statusText}`);
      }
    } catch {
      const group = groups.find(g => g.id === groupId);
      setControlError(`Failed to toggle ${group?.name || 'group'}`);
    }
  };

  // Check if a group has any fixtures currently on
  const isGroupOn = (groupId: number): boolean => {
    const fixtures = groupFixtures.get(groupId) || [];
    return fixtures.some(f => fixtureStates.get(f.id)?.is_on);
  };

  // Get average brightness for a group (memoized)
  const groupBrightnessCache = useMemo(() => {
    const cache = new Map<number, number>();
    groupFixtures.forEach((fixtures, groupId) => {
      if (fixtures.length === 0) {
        cache.set(groupId, 0);
        return;
      }
      const total = fixtures.reduce((sum, f) => {
        const state = fixtureStates.get(f.id);
        return sum + (state ? state.goal_brightness / BRIGHTNESS_DISPLAY_SCALE : 0);
      }, 0);
      cache.set(groupId, Math.round(total / fixtures.length));
    });
    return cache;
  }, [groupFixtures, fixtureStates]);

  const getGroupBrightness = useCallback((groupId: number): number => {
    return groupBrightnessCache.get(groupId) ?? 0;
  }, [groupBrightnessCache]);

  // Handle brightness input submit with validation feedback
  const handleBrightnessInputSubmit = useCallback((type: 'fixture' | 'group', id: number, value: string) => {
    const trimmedValue = value.trim();

    // Check for empty input
    if (trimmedValue === '') {
      setValidationError('Please enter a brightness value');
      setEditingBrightness(null);
      setBrightnessInputValue('');
      return;
    }

    const brightness = parseInt(trimmedValue, 10);

    // Check for non-numeric input
    if (isNaN(brightness)) {
      setValidationError('Brightness must be a number');
      setEditingBrightness(null);
      setBrightnessInputValue('');
      return;
    }

    // Check for out of range
    if (brightness < 0 || brightness > 100) {
      setValidationError('Brightness must be between 0 and 100');
      setEditingBrightness(null);
      setBrightnessInputValue('');
      return;
    }

    if (type === 'fixture') {
      handleFixtureBrightness(id, brightness / 100);
    } else {
      handleGroupBrightness(id, brightness / 100);
    }
    setEditingBrightness(null);
    setBrightnessInputValue('');
  }, [handleFixtureBrightness, handleGroupBrightness]);

  // Get ungrouped fixtures
  const getUngroupedFixtures = (): Fixture[] => {
    const groupedFixtureIds = new Set<number>();
    groupFixtures.forEach(fixtureList => {
      fixtureList.forEach(f => groupedFixtureIds.add(f.id));
    });
    return fixtures.filter(f => !groupedFixtureIds.has(f.id));
  };

  // Toggle expand for fixture
  const toggleFixtureExpand = (fixtureId: number) => {
    setExpandedFixtures(prev => {
      const newSet = new Set(prev);
      if (newSet.has(fixtureId)) {
        newSet.delete(fixtureId);
      } else {
        newSet.add(fixtureId);
      }
      return newSet;
    });
  };

  // Toggle expand for group
  const toggleGroupExpand = (groupId: number) => {
    setExpandedGroups(prev => {
      const newSet = new Set(prev);
      if (newSet.has(groupId)) {
        newSet.delete(groupId);
      } else {
        newSet.add(groupId);
      }
      return newSet;
    });
  };

  // Kelvin to color for CCT slider
  const kelvinToColor = (kelvin: number): string => {
    const t = (kelvin - 2000) / 4500;
    const r = Math.round(255 * (1 - t * 0.3));
    const g = Math.round(200 + t * 55);
    const b = Math.round(150 + t * 105);
    return `rgb(${r}, ${g}, ${b})`;
  };

  const isHealthy = status?.hardware?.overall_healthy && status?.event_loop?.running;
  const healthPassed = status?.hardware?.health_checks?.passed || 0;
  const healthFailed = status?.hardware?.health_checks?.failed || 0;
  const healthTotal = healthPassed + healthFailed;
  const healthPercent = healthTotal > 0 ? Math.round((healthPassed / healthTotal) * 100) : 100;
  const circumference = 2 * Math.PI * 90;
  const strokeOffset = circumference - (healthPercent / 100) * circumference;

  return (
    <div className="min-h-screen bg-[#0a0a0b] text-white">
      {/* Ambient glows */}
      <div className="fixed top-[-200px] right-[-100px] w-[600px] h-[600px] rounded-full bg-amber-500 opacity-[0.08] blur-[120px] pointer-events-none" />
      <div className="fixed bottom-[-300px] left-[-200px] w-[600px] h-[600px] rounded-full bg-blue-500 opacity-[0.05] blur-[120px] pointer-events-none" />

      {/* Grid background */}
      <div className="fixed inset-0 pointer-events-none" style={{
        backgroundImage: 'linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px)',
        backgroundSize: '60px 60px'
      }} />

      {/* Main content */}
      <main className="relative z-5 px-10 py-8 max-w-[1800px] mx-auto">
        <div className="grid grid-cols-[320px_1fr_1fr] gap-5">

          {/* System Health Card */}
          <div className="row-span-2 bg-[#161619] border border-[#2a2a2f] rounded-2xl p-6 flex flex-col">
            <div className="flex justify-between items-center mb-5">
              <span className="text-[13px] font-medium uppercase tracking-wider text-[#636366]">System Health</span>
              <span className={`font-mono text-[11px] px-2.5 py-1 rounded-md border ${healthFailed > 0 ? 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20' : 'bg-green-500/15 text-green-500 border-green-500/20'}`}>
                {healthFailed > 0 ? 'DEGRADED' : 'HEALTHY'}
              </span>
            </div>
            <div className="flex-1 flex items-center justify-center py-5">
              <div className="relative w-[200px] h-[200px]">
                <svg className="-rotate-90 w-full h-full" viewBox="0 0 200 200">
                  <defs>
                    <linearGradient id="health-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                      <stop offset="0%" stopColor="#b45309"/>
                      <stop offset="100%" stopColor="#f59e0b"/>
                    </linearGradient>
                  </defs>
                  <circle cx="100" cy="100" r="90" fill="none" stroke="#2a2a2f" strokeWidth="8"/>
                  <circle
                    cx="100" cy="100" r="90"
                    fill="none"
                    stroke="url(#health-gradient)"
                    strokeWidth="8"
                    strokeLinecap="round"
                    strokeDasharray={circumference}
                    strokeDashoffset={strokeOffset}
                    className="transition-all duration-1000"
                  />
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <div className="font-mono text-[42px] font-semibold">{healthPercent}%</div>
                  <div className="text-[12px] text-[#636366] mt-1">Uptime Score</div>
                </div>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 mt-auto">
              <div className="bg-[#111113] rounded-[10px] p-3.5 text-center">
                <div className="font-mono text-xl font-medium">{formatNumber(healthPassed)}</div>
                <div className="text-[11px] text-[#636366] mt-1">Checks Passed</div>
              </div>
              <div className="bg-[#111113] rounded-[10px] p-3.5 text-center">
                <div className="font-mono text-xl font-medium">{healthFailed}</div>
                <div className="text-[11px] text-[#636366] mt-1">Checks Failed</div>
              </div>
            </div>
          </div>

          {/* LabJack Card */}
          <div className="bg-[#161619] border border-[#2a2a2f] rounded-2xl p-6">
            <div className="flex items-center gap-3 mb-5">
              <div className="w-11 h-11 rounded-xl bg-[#111113] border border-[#2a2a2f] flex items-center justify-center">
                <svg className="w-[22px] h-[22px] stroke-amber-500" fill="none" strokeWidth="1.5" viewBox="0 0 24 24">
                  <rect x="4" y="4" width="16" height="16" rx="2"/>
                  <line x1="9" y1="9" x2="9" y2="9.01"/>
                  <line x1="15" y1="9" x2="15" y2="9.01"/>
                  <line x1="9" y1="15" x2="9" y2="15.01"/>
                  <line x1="15" y1="15" x2="15" y2="15.01"/>
                </svg>
              </div>
              <div className="flex-1">
                <h3 className="text-base font-medium">LabJack</h3>
                <p className="font-mono text-[12px] text-[#636366] mt-0.5">
                  {status?.hardware?.labjack?.model || '--'} #{status?.hardware?.labjack?.serial_number || '--'}
                </p>
              </div>
              <span className={`font-mono text-[11px] px-2.5 py-1 rounded-md border ${status?.hardware?.labjack?.connected ? 'bg-green-500/15 text-green-500 border-green-500/20' : 'bg-red-500/15 text-red-500 border-red-500/20'}`}>
                {status?.hardware?.labjack?.connected ? 'CONNECTED' : 'OFFLINE'}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="text-center">
                <div className="font-mono text-2xl font-medium text-amber-500">{formatNumber(status?.hardware?.labjack?.read_count || 0)}</div>
                <div className="text-[11px] text-[#636366] mt-1">Reads</div>
              </div>
              <div className="text-center">
                <div className="font-mono text-2xl font-medium">{formatNumber(status?.hardware?.labjack?.write_count || 0)}</div>
                <div className="text-[11px] text-[#636366] mt-1">Writes</div>
              </div>
              <div className="text-center">
                <div className="font-mono text-2xl font-medium">{status?.hardware?.labjack?.error_count || 0}</div>
                <div className="text-[11px] text-[#636366] mt-1">Errors</div>
              </div>
            </div>
          </div>

          {/* OLA Card */}
          <div className="bg-[#161619] border border-[#2a2a2f] rounded-2xl p-6">
            <div className="flex items-center gap-3 mb-5">
              <div className="w-11 h-11 rounded-xl bg-[#111113] border border-[#2a2a2f] flex items-center justify-center">
                <svg className="w-[22px] h-[22px] stroke-amber-500" fill="none" strokeWidth="1.5" viewBox="0 0 24 24">
                  <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
                </svg>
              </div>
              <div className="flex-1">
                <h3 className="text-base font-medium">OLA DMX</h3>
                <p className="font-mono text-[12px] text-[#636366] mt-0.5">{status?.hardware?.ola?.max_universes || 0} universes</p>
              </div>
              <span className={`font-mono text-[11px] px-2.5 py-1 rounded-md border ${status?.hardware?.ola?.connected ? 'bg-green-500/15 text-green-500 border-green-500/20' : 'bg-red-500/15 text-red-500 border-red-500/20'}`}>
                {status?.hardware?.ola?.connected ? 'CONNECTED' : 'OFFLINE'}
              </span>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="text-center">
                <div className="font-mono text-2xl font-medium text-amber-500">{formatNumber(status?.hardware?.ola?.channel_set_count || 0)}</div>
                <div className="text-[11px] text-[#636366] mt-1">Ch Updates</div>
              </div>
              <div className="text-center">
                <div className="font-mono text-2xl font-medium">{status?.hardware?.ola?.non_zero_channels || 0}</div>
                <div className="text-[11px] text-[#636366] mt-1">Active Ch</div>
              </div>
              <div className="text-center">
                <div className="font-mono text-2xl font-medium">{status?.hardware?.ola?.error_count || 0}</div>
                <div className="text-[11px] text-[#636366] mt-1">Errors</div>
              </div>
            </div>
          </div>

          {/* Event Loop Card */}
          <div className="col-span-2 bg-[#161619] border border-[#2a2a2f] rounded-2xl p-6">
            <div className="flex justify-between items-center mb-5">
              <span className="text-[13px] font-medium uppercase tracking-wider text-[#636366]">Event Loop Performance</span>
              <span className="font-mono text-[11px] px-2.5 py-1 rounded-md bg-green-500/15 text-green-500 border border-green-500/20">
                {status?.event_loop?.frequency_hz || 30} Hz
              </span>
            </div>
            <div className="grid grid-cols-5 gap-4">
              {[
                { value: formatNumber(status?.event_loop?.iterations || 0), label: 'Iterations' },
                { value: (status?.event_loop?.avg_time_ms || 0).toFixed(2), unit: 'ms', label: 'Avg Time' },
                { value: (status?.event_loop?.min_time_ms || 0).toFixed(2), unit: 'ms', label: 'Min Time' },
                { value: (status?.event_loop?.max_time_ms || 0).toFixed(2), unit: 'ms', label: 'Max Time' },
                { value: formatUptime(status?.event_loop?.total_time_s || 0), label: 'Uptime' },
              ].map((metric, i) => (
                <div key={i} className="bg-[#111113] rounded-xl p-4 relative overflow-hidden group">
                  <div className="absolute top-0 left-0 right-0 h-0.5 bg-gradient-to-r from-amber-500 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
                  <div className="font-mono text-[28px] font-medium">
                    {metric.value}
                    {metric.unit && <span className="text-sm text-[#636366] font-normal">{metric.unit}</span>}
                  </div>
                  <div className="text-[12px] text-[#636366] mt-1.5">{metric.label}</div>
                </div>
              ))}
            </div>
          </div>

          {/* FIO Channels Card with Light Simulators */}
          <div className="bg-[#161619] border border-[#2a2a2f] rounded-2xl p-6">
            <div className="flex justify-between items-center mb-5">
              <span className="text-[13px] font-medium uppercase tracking-wider text-[#636366]">FIO Channels</span>
              <span className="font-mono text-[10px] text-[#636366]">tap • double • triple • hold</span>
            </div>
            <div className="grid grid-cols-4 gap-3">
              {[0, 1, 2, 3, 4, 5, 6, 7].map(i => {
                const isHigh = status?.hardware?.labjack?.digital_inputs?.[String(i)] === true;
                const light = lightStates[i];
                const brightness = light.brightness;

                // Scene colors for the label
                const sceneColors: Record<string, string> = {
                  off: 'text-[#636366]',
                  full: 'text-amber-400',
                  scene1: 'text-blue-400',
                  scene2: 'text-purple-400',
                  custom: 'text-[#a1a1a6]',
                };

                const sceneLabels: Record<string, string> = {
                  off: 'OFF',
                  full: 'FULL',
                  scene1: 'S1',
                  scene2: 'S2',
                  custom: `${Math.round(brightness)}%`,
                };

                return (
                  <div
                    key={i}
                    className="relative rounded-xl overflow-hidden border transition-all"
                    style={{
                      borderColor: isHigh ? 'rgb(245 158 11)' : brightness > 0 ? 'rgb(245 158 11 / 0.3)' : 'rgb(42 42 47)',
                    }}
                  >
                    {/* Light glow background */}
                    <div
                      className="absolute inset-0 transition-opacity duration-200"
                      style={{
                        background: 'linear-gradient(135deg, rgb(245 158 11), rgb(253 224 71))',
                        opacity: brightness / 100,
                      }}
                    />
                    {/* Dark overlay for readability */}
                    <div
                      className="absolute inset-0 bg-[#111113] transition-opacity duration-200"
                      style={{ opacity: 1 - (brightness / 100) * 0.85 }}
                    />
                    {/* Content */}
                    <div className="relative z-10 p-3 flex flex-col items-center">
                      {/* Channel label and state */}
                      <div className="flex items-center justify-between w-full mb-2">
                        <span className="font-mono text-[10px] text-[#636366]">FIO{i}</span>
                        <span className={`font-mono text-[9px] px-1.5 py-0.5 rounded ${isHigh ? 'bg-amber-500/30 text-amber-400' : 'bg-[#2a2a2f] text-[#636366]'}`}>
                          {isHigh ? 'HIGH' : 'LOW'}
                        </span>
                      </div>
                      {/* Brightness percentage */}
                      <div className={`font-mono text-2xl font-bold ${brightness > 50 ? 'text-[#111113]' : 'text-white'}`}>
                        {Math.round(brightness)}%
                      </div>
                      {/* Scene indicator */}
                      <div className={`font-mono text-[10px] mt-1 ${brightness > 50 ? 'text-[#111113]/70' : sceneColors[light.scene]}`}>
                        {sceneLabels[light.scene]}
                      </div>
                      {/* Mini progress bar */}
                      <div className="w-full h-1 bg-black/20 rounded-full mt-2 overflow-hidden">
                        <div
                          className="h-full bg-white rounded-full transition-all duration-200"
                          style={{ width: `${brightness}%` }}
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Lighting Control Card */}
          <div className="col-span-2 bg-[#161619] border border-[#2a2a2f] rounded-2xl p-6">
            <div className="flex justify-between items-center mb-5">
              <span className="text-[13px] font-medium uppercase tracking-wider text-[#636366]">Lighting Control</span>
              <div className="flex items-center gap-2">
                <span className="font-mono text-[11px] px-2.5 py-1 rounded-md bg-purple-500/15 text-purple-400 border border-purple-500/20">
                  {groups.length} groups
                </span>
                <span className="font-mono text-[11px] px-2.5 py-1 rounded-md bg-green-500/15 text-green-500 border border-green-500/20">
                  {fixtures.length} fixtures
                </span>
              </div>
            </div>

            {/* Control Error Toast */}
            {controlError && (
              <div className="mb-3 px-3 py-2 bg-red-500/10 border border-red-500/20 rounded-lg flex items-center gap-2">
                <svg className="w-4 h-4 stroke-red-400 flex-shrink-0" fill="none" strokeWidth="2" viewBox="0 0 24 24">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
                <span className="text-[12px] text-red-400 flex-1">{controlError}</span>
                <button
                  onClick={() => setControlError(null)}
                  className="p-1 hover:bg-red-500/20 rounded transition-colors"
                >
                  <svg className="w-3 h-3 stroke-red-400" fill="none" strokeWidth="2" viewBox="0 0 24 24">
                    <path d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            )}

            {/* Validation Error Toast */}
            {validationError && (
              <div className="mb-3 px-3 py-2 bg-yellow-500/10 border border-yellow-500/20 rounded-lg flex items-center gap-2">
                <svg className="w-4 h-4 stroke-yellow-400 flex-shrink-0" fill="none" strokeWidth="2" viewBox="0 0 24 24">
                  <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <span className="text-[12px] text-yellow-400 flex-1">{validationError}</span>
                <button
                  onClick={() => setValidationError(null)}
                  className="p-1 hover:bg-yellow-500/20 rounded transition-colors"
                >
                  <svg className="w-3 h-3 stroke-yellow-400" fill="none" strokeWidth="2" viewBox="0 0 24 24">
                    <path d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            )}

            <div className="flex flex-col gap-2 max-h-[500px] overflow-y-auto pr-1">
              {/* Groups Section */}
              {groups
                .sort((a, b) => (b.is_system ? 1 : 0) - (a.is_system ? 1 : 0) || a.name.localeCompare(b.name))
                .map(group => {
                  const isExpanded = expandedGroups.has(group.id);
                  const groupOn = isGroupOn(group.id);
                  const groupBrightness = getGroupBrightness(group.id);
                  const fixturesInGroup = groupFixtures.get(group.id) || [];

                  return (
                    <div key={`group-${group.id}`} className="bg-[#111113] rounded-xl overflow-hidden">
                      {/* Group Header */}
                      <div className="flex items-center gap-3 px-4 py-3">
                        {/* Expand button */}
                        <button
                          onClick={() => toggleGroupExpand(group.id)}
                          className="p-0.5 hover:bg-white/10 rounded transition-colors"
                        >
                          <svg
                            className={`w-4 h-4 stroke-[#636366] transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                            fill="none"
                            strokeWidth="2"
                            viewBox="0 0 24 24"
                          >
                            <path d="M9 18l6-6-6-6" />
                          </svg>
                        </button>

                        {/* Status indicator */}
                        <div
                          className={`w-2.5 h-2.5 rounded-full transition-all ${
                            groupOn ? 'bg-purple-500 shadow-[0_0_8px_rgba(168,85,247,0.4)]' : 'bg-[#3a3a3f]'
                          }`}
                        />

                        {/* Name */}
                        <span className="flex-1 text-sm font-medium truncate">{group.name}</span>

                        {/* Fixture count badge */}
                        <span className="font-mono text-[9px] text-[#636366] px-1.5 py-0.5 bg-[#1a1a1d] rounded">
                          {fixturesInGroup.length} fixtures
                        </span>

                        {group.is_system && (
                          <span className="text-[9px] px-1.5 py-0.5 bg-purple-500/20 text-purple-400 rounded">SYSTEM</span>
                        )}
                        {group.circadian_enabled && (
                          <span className="text-[9px] px-1.5 py-0.5 bg-blue-500/20 text-blue-400 rounded">CIRCADIAN</span>
                        )}

                        {/* Brightness indicator */}
                        <div className="w-[60px] h-1.5 bg-[#2a2a2f] rounded-full overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-purple-700 to-purple-500 rounded-full transition-all"
                            style={{ width: `${groupBrightness}%` }}
                          />
                        </div>

                        {/* Editable brightness percentage */}
                        {editingBrightness?.type === 'group' && editingBrightness.id === group.id ? (
                          <input
                            type="text"
                            autoFocus
                            className="font-mono text-[11px] text-[#a1a1a6] w-[40px] text-right bg-[#1a1a1d] border border-purple-500/50 rounded px-1 py-0.5 outline-none"
                            value={brightnessInputValue}
                            onChange={(e) => setBrightnessInputValue(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                handleBrightnessInputSubmit('group', group.id, brightnessInputValue);
                              } else if (e.key === 'Escape') {
                                setEditingBrightness(null);
                                setBrightnessInputValue('');
                              }
                            }}
                            onBlur={() => {
                              setEditingBrightness(null);
                              setBrightnessInputValue('');
                            }}
                          />
                        ) : (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setEditingBrightness({ type: 'group', id: group.id });
                              setBrightnessInputValue(String(groupBrightness));
                            }}
                            className="font-mono text-[11px] text-[#a1a1a6] w-[36px] text-right hover:text-white transition-colors"
                          >
                            {groupBrightness}%
                          </button>
                        )}

                        {/* On/Off Toggle */}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleGroupToggle(group.id, !groupOn);
                          }}
                          className={`w-10 h-5 rounded-full transition-all relative ${
                            groupOn ? 'bg-purple-500' : 'bg-[#3a3a3f]'
                          }`}
                        >
                          <div
                            className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-all shadow ${
                              groupOn ? 'left-5' : 'left-0.5'
                            }`}
                          />
                        </button>
                      </div>

                      {/* Expanded Group Controls and Fixtures */}
                      {isExpanded && (
                        <div className="border-t border-[#2a2a2f]">
                          {/* Group-level controls */}
                          <div className="px-4 py-3 bg-[#0d0d0f] space-y-3">
                            <div className="flex items-center gap-3">
                              <span className="text-[11px] text-[#636366] w-16">Brightness</span>
                              <input
                                type="range"
                                min={0}
                                max={100}
                                value={groupBrightness}
                                className="flex-1 h-1.5 rounded-full appearance-none bg-[#2a2a2f] cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-purple-500"
                                onChange={(e) => handleGroupBrightness(group.id, parseInt(e.target.value) / 100)}
                              />
                              <span className="font-mono text-[11px] text-[#a1a1a6] w-10 text-right">{groupBrightness}%</span>
                            </div>
                            <div className="flex items-center gap-3">
                              <span className="text-[11px] text-[#636366] w-16">CCT</span>
                              <input
                                type="range"
                                min={2700}
                                max={6500}
                                defaultValue={4000}
                                className="flex-1 h-1.5 rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white"
                                style={{ background: `linear-gradient(to right, ${kelvinToColor(2700)}, ${kelvinToColor(6500)})` }}
                                onChange={(e) => handleGroupCCT(group.id, parseInt(e.target.value))}
                              />
                            </div>
                          </div>

                          {/* Fixtures in group */}
                          {fixturesInGroup.length > 0 && (
                            <div className="px-2 py-2 space-y-1">
                              {fixturesInGroup.map(fixture => {
                                const state = fixtureStates.get(fixture.id);
                                const model = fixtureModels.get(fixture.fixture_model_id);
                                const isFixtureExpanded = expandedFixtures.has(fixture.id);
                                const brightness = state ? Math.round(state.goal_brightness / BRIGHTNESS_DISPLAY_SCALE) : 0;
                                const cct = state?.goal_cct ?? 2700;
                                const cctMin = model?.cct_min_kelvin ?? 2700;
                                const cctMax = model?.cct_max_kelvin ?? 6500;
                                const isOn = state?.is_on ?? false;

                                return (
                                  <div key={`grouped-fixture-${fixture.id}`} className="bg-[#161619] rounded-lg overflow-hidden ml-4">
                                    <div className="flex items-center gap-2 px-3 py-2">
                                      {/* Expand button */}
                                      <button
                                        onClick={() => toggleFixtureExpand(fixture.id)}
                                        className="p-0.5 hover:bg-white/10 rounded transition-colors"
                                      >
                                        <svg
                                          className={`w-3 h-3 stroke-[#636366] transition-transform ${isFixtureExpanded ? 'rotate-90' : ''}`}
                                          fill="none"
                                          strokeWidth="2"
                                          viewBox="0 0 24 24"
                                        >
                                          <path d="M9 18l6-6-6-6" />
                                        </svg>
                                      </button>

                                      {/* Status indicator */}
                                      <div
                                        className={`w-2 h-2 rounded-full transition-all ${
                                          isOn ? 'bg-amber-500 shadow-[0_0_6px_rgba(245,158,11,0.4)]' : 'bg-[#3a3a3f]'
                                        }`}
                                      />

                                      {/* Name */}
                                      <span className="flex-1 text-[12px] font-medium truncate">{fixture.name}</span>

                                      {/* DMX channel */}
                                      <span className="font-mono text-[9px] text-[#636366] px-1.5 py-0.5 bg-[#1a1a1d] rounded">
                                        CH {fixture.dmx_channel_start}
                                      </span>

                                      {/* Brightness indicator */}
                                      <div className="w-[50px] h-1 bg-[#2a2a2f] rounded-full overflow-hidden">
                                        <div
                                          className="h-full bg-gradient-to-r from-amber-700 to-amber-500 rounded-full transition-all"
                                          style={{ width: `${brightness}%` }}
                                        />
                                      </div>

                                      {/* Editable brightness percentage */}
                                      {editingBrightness?.type === 'fixture' && editingBrightness.id === fixture.id ? (
                                        <input
                                          type="text"
                                          autoFocus
                                          className="font-mono text-[10px] text-[#a1a1a6] w-[36px] text-right bg-[#1a1a1d] border border-amber-500/50 rounded px-1 py-0.5 outline-none"
                                          value={brightnessInputValue}
                                          onChange={(e) => setBrightnessInputValue(e.target.value)}
                                          onKeyDown={(e) => {
                                            if (e.key === 'Enter') {
                                              handleBrightnessInputSubmit('fixture', fixture.id, brightnessInputValue);
                                            } else if (e.key === 'Escape') {
                                              setEditingBrightness(null);
                                              setBrightnessInputValue('');
                                            }
                                          }}
                                          onBlur={() => {
                                            setEditingBrightness(null);
                                            setBrightnessInputValue('');
                                          }}
                                        />
                                      ) : (
                                        <button
                                          onClick={(e) => {
                                            e.stopPropagation();
                                            setEditingBrightness({ type: 'fixture', id: fixture.id });
                                            setBrightnessInputValue(String(brightness));
                                          }}
                                          className="font-mono text-[10px] text-[#a1a1a6] w-[30px] text-right hover:text-white transition-colors"
                                        >
                                          {brightness}%
                                        </button>
                                      )}

                                      {/* On/Off Toggle */}
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          handleFixtureToggle(fixture.id);
                                        }}
                                        className={`w-8 h-4 rounded-full transition-all relative ${
                                          isOn ? 'bg-amber-500' : 'bg-[#3a3a3f]'
                                        }`}
                                      >
                                        <div
                                          className={`absolute top-0.5 w-3 h-3 bg-white rounded-full transition-all shadow ${
                                            isOn ? 'left-4' : 'left-0.5'
                                          }`}
                                        />
                                      </button>
                                    </div>

                                    {/* Expanded fixture controls */}
                                    {isFixtureExpanded && (
                                      <div className="px-3 pb-3 pt-2 border-t border-[#2a2a2f] space-y-2">
                                        <div className="flex items-center gap-2">
                                          <span className="text-[10px] text-[#636366] w-14">Brightness</span>
                                          <input
                                            type="range"
                                            min={0}
                                            max={100}
                                            value={brightness}
                                            className="flex-1 h-1 rounded-full appearance-none bg-[#2a2a2f] cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-2.5 [&::-webkit-slider-thumb]:h-2.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-amber-500"
                                            onChange={(e) => handleFixtureBrightness(fixture.id, parseInt(e.target.value) / 100)}
                                          />
                                          <span className="font-mono text-[10px] text-[#a1a1a6] w-8 text-right">{brightness}%</span>
                                        </div>
                                        <div className="flex items-center gap-2">
                                          <span className="text-[10px] text-[#636366] w-14">CCT</span>
                                          <input
                                            type="range"
                                            min={cctMin}
                                            max={cctMax}
                                            value={cct}
                                            className="flex-1 h-1 rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-2.5 [&::-webkit-slider-thumb]:h-2.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white"
                                            style={{ background: `linear-gradient(to right, ${kelvinToColor(cctMin)}, ${kelvinToColor(cctMax)})` }}
                                            onChange={(e) => handleFixtureCCT(fixture.id, parseInt(e.target.value))}
                                          />
                                          <span className="font-mono text-[10px] text-[#a1a1a6] w-8 text-right">{cct}K</span>
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          )}

                          {fixturesInGroup.length === 0 && (
                            <div className="px-4 py-3 text-[11px] text-[#636366] italic">
                              No fixtures in this group
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}

              {/* Ungrouped Fixtures Section */}
              {(() => {
                const ungroupedFixtures = getUngroupedFixtures();
                if (ungroupedFixtures.length === 0) return null;

                return (
                  <>
                    <div className="flex items-center gap-2 mt-4 mb-2">
                      <div className="h-px flex-1 bg-[#2a2a2f]" />
                      <span className="text-[10px] uppercase tracking-wider text-[#636366]">Ungrouped Fixtures</span>
                      <div className="h-px flex-1 bg-[#2a2a2f]" />
                    </div>
                    {ungroupedFixtures.map(fixture => {
                      const state = fixtureStates.get(fixture.id);
                      const model = fixtureModels.get(fixture.fixture_model_id);
                      const isExpanded = expandedFixtures.has(fixture.id);
                      const brightness = state ? Math.round(state.goal_brightness / BRIGHTNESS_DISPLAY_SCALE) : 0;
                      const cct = state?.goal_cct ?? 2700;
                      const cctMin = model?.cct_min_kelvin ?? 2700;
                      const cctMax = model?.cct_max_kelvin ?? 6500;
                      const isOn = state?.is_on ?? false;

                      return (
                        <div key={`ungrouped-fixture-${fixture.id}`} className="bg-[#111113] rounded-xl overflow-hidden">
                          <div className="flex items-center gap-3 px-4 py-3">
                            {/* Expand button */}
                            <button
                              onClick={() => toggleFixtureExpand(fixture.id)}
                              className="p-0.5 hover:bg-white/10 rounded transition-colors"
                            >
                              <svg
                                className={`w-4 h-4 stroke-[#636366] transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                                fill="none"
                                strokeWidth="2"
                                viewBox="0 0 24 24"
                              >
                                <path d="M9 18l6-6-6-6" />
                              </svg>
                            </button>

                            {/* Status indicator */}
                            <div
                              className={`w-2.5 h-2.5 rounded-full transition-all ${
                                isOn ? 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.4)]' : 'bg-[#3a3a3f]'
                              }`}
                            />

                            {/* Name */}
                            <span className="flex-1 text-sm font-medium truncate">{fixture.name}</span>

                            {/* DMX channel */}
                            <span className="font-mono text-[10px] text-[#636366] px-2 py-0.5 bg-[#1a1a1d] rounded">
                              CH {fixture.dmx_channel_start}
                            </span>

                            {/* Brightness indicator */}
                            <div className="w-[80px] h-1.5 bg-[#2a2a2f] rounded-full overflow-hidden">
                              <div
                                className="h-full bg-gradient-to-r from-amber-700 to-amber-500 rounded-full transition-all"
                                style={{ width: `${brightness}%` }}
                              />
                            </div>

                            {/* Editable brightness percentage */}
                            {editingBrightness?.type === 'fixture' && editingBrightness.id === fixture.id ? (
                              <input
                                type="text"
                                autoFocus
                                className="font-mono text-[11px] text-[#a1a1a6] w-[40px] text-right bg-[#1a1a1d] border border-amber-500/50 rounded px-1 py-0.5 outline-none"
                                value={brightnessInputValue}
                                onChange={(e) => setBrightnessInputValue(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') {
                                    handleBrightnessInputSubmit('fixture', fixture.id, brightnessInputValue);
                                  } else if (e.key === 'Escape') {
                                    setEditingBrightness(null);
                                    setBrightnessInputValue('');
                                  }
                                }}
                                onBlur={() => {
                                  setEditingBrightness(null);
                                  setBrightnessInputValue('');
                                }}
                              />
                            ) : (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setEditingBrightness({ type: 'fixture', id: fixture.id });
                                  setBrightnessInputValue(String(brightness));
                                }}
                                className="font-mono text-[11px] text-[#a1a1a6] w-[36px] text-right hover:text-white transition-colors"
                              >
                                {brightness}%
                              </button>
                            )}

                            {/* On/Off Toggle */}
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleFixtureToggle(fixture.id);
                              }}
                              className={`w-10 h-5 rounded-full transition-all relative ${
                                isOn ? 'bg-amber-500' : 'bg-[#3a3a3f]'
                              }`}
                            >
                              <div
                                className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-all shadow ${
                                  isOn ? 'left-5' : 'left-0.5'
                                }`}
                              />
                            </button>
                          </div>

                          {/* Expanded controls */}
                          {isExpanded && (
                            <div className="px-4 pb-4 pt-2 border-t border-[#2a2a2f] space-y-3">
                              <div className="flex items-center gap-3">
                                <span className="text-[11px] text-[#636366] w-16">Brightness</span>
                                <input
                                  type="range"
                                  min={0}
                                  max={100}
                                  value={brightness}
                                  className="flex-1 h-1.5 rounded-full appearance-none bg-[#2a2a2f] cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-amber-500"
                                  onChange={(e) => handleFixtureBrightness(fixture.id, parseInt(e.target.value) / 100)}
                                />
                                <span className="font-mono text-[11px] text-[#a1a1a6] w-10 text-right">{brightness}%</span>
                              </div>
                              <div className="flex items-center gap-3">
                                <span className="text-[11px] text-[#636366] w-16">CCT</span>
                                <input
                                  type="range"
                                  min={cctMin}
                                  max={cctMax}
                                  value={cct}
                                  className="flex-1 h-1.5 rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white"
                                  style={{ background: `linear-gradient(to right, ${kelvinToColor(cctMin)}, ${kelvinToColor(cctMax)})` }}
                                  onChange={(e) => handleFixtureCCT(fixture.id, parseInt(e.target.value))}
                                />
                                <span className="font-mono text-[11px] text-[#a1a1a6] w-10 text-right">{cct}K</span>
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </>
                );
              })()}
            </div>
          </div>

          {/* Activity Card */}
          <div className="col-span-2 bg-[#161619] border border-[#2a2a2f] rounded-2xl p-6">
            <div className="flex justify-between items-center mb-5">
              <span className="text-[13px] font-medium uppercase tracking-wider text-[#636366]">Activity</span>
            </div>
            <div className="grid grid-cols-4 gap-4">
              {[
                { icon: 'M12 6v6l4 2', value: status?.lighting?.circadian?.profiles_loaded || 0, label: 'Circadian Profiles' },
                { icon: 'M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z', value: status?.lighting?.scenes?.scenes_recalled || 0, label: 'Scenes Recalled' },
                { icon: 'M7 11V7a5 5 0 0110 0v4', value: formatNumber(status?.lighting?.switches?.events_processed || 0), label: 'Switch Events' },
                { icon: 'M22 12h-4l-3 9L9 3l-3 9H2', value: formatNumber(status?.lighting?.hardware_updates || 0), label: 'HW Updates' },
              ].map((stat, i) => (
                <div key={i} className="bg-[#111113] rounded-xl p-5 text-center border border-transparent hover:border-[#2a2a2f] transition-colors">
                  <div className="w-10 h-10 mx-auto mb-3 rounded-[10px] bg-[#161619] flex items-center justify-center">
                    <svg className="w-5 h-5 stroke-[#636366]" fill="none" strokeWidth="1.5" viewBox="0 0 24 24">
                      <path d={stat.icon} />
                      {i === 0 && <circle cx="12" cy="12" r="10"/>}
                      {i === 1 && <line x1="4" y1="22" x2="4" y2="15"/>}
                      {i === 2 && <rect x="3" y="11" width="18" height="11" rx="2"/>}
                    </svg>
                  </div>
                  <div className="font-mono text-[28px] font-medium">{stat.value}</div>
                  <div className="text-[12px] text-[#636366] mt-1">{stat.label}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Active Overrides Card */}
          <div className="bg-[#161619] border border-[#2a2a2f] rounded-2xl p-6">
            <div className="flex justify-between items-center mb-5">
              <div className="flex items-center gap-3">
                <span className="text-[13px] font-medium uppercase tracking-wider text-[#636366]">Active Overrides</span>
                {activeOverrides.length > 0 && (
                  <span className="font-mono text-[11px] px-2.5 py-1 rounded-md bg-amber-500/15 text-amber-500 border border-amber-500/20">
                    {activeOverrides.length}
                  </span>
                )}
              </div>
              {activeOverrides.length > 0 && (
                <button
                  onClick={handleRemoveAllOverrides}
                  className="font-mono text-[11px] px-2.5 py-1 rounded-md bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-colors"
                >
                  Remove All
                </button>
              )}
            </div>

            {activeOverrides.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 text-center">
                <div className="w-12 h-12 rounded-xl bg-[#111113] border border-[#2a2a2f] flex items-center justify-center mb-3">
                  <svg className="w-6 h-6 stroke-[#636366]" fill="none" strokeWidth="1.5" viewBox="0 0 24 24">
                    <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                  </svg>
                </div>
                <p className="text-[13px] text-[#636366]">No active overrides</p>
                <p className="text-[11px] text-[#4a4a4f] mt-1">Circadian automation active</p>
              </div>
            ) : (
              <div className="flex flex-col gap-2">
                {activeOverrides.map(override => (
                  <div
                    key={override.fixture_id}
                    className="flex items-center gap-3 px-3 py-2.5 bg-[#111113] rounded-lg border border-[#2a2a2f] hover:border-amber-500/30 transition-colors"
                  >
                    <div className="w-2 h-2 rounded-full bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.3)]" />
                    <div className="flex-1 min-w-0">
                      <div className="text-[13px] font-medium truncate">
                        {getFixtureName(override.fixture_id)}
                      </div>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-[10px] text-[#636366]">
                          {formatTimeRemaining(override.expires_at)} remaining
                        </span>
                        <span className="text-[10px] px-1.5 py-0.5 bg-[#2a2a2f] rounded text-[#8e8e93]">
                          {override.override_source}
                        </span>
                      </div>
                    </div>
                    <button
                      onClick={() => handleRemoveOverride(override.fixture_id)}
                      className="p-1.5 rounded-md hover:bg-red-500/20 transition-colors group"
                      title="Remove override"
                    >
                      <svg className="w-4 h-4 stroke-[#636366] group-hover:stroke-red-400" fill="none" strokeWidth="1.5" viewBox="0 0 24 24">
                        <path d="M6 18L18 6M6 6l12 12"/>
                      </svg>
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-5 px-10 py-4 border-t border-[#1f1f24] flex justify-between items-center mt-5">
        <div className="flex items-center gap-4">
          <a href="/api/docs" target="_blank" className="text-xs text-[#636366] hover:text-[#a1a1a6] transition-colors">API Docs</a>
          <span className="text-[#2a2a2f]">|</span>
          <span className="text-xs text-[#4a4a4f]">Tau Lighting Control System</span>
        </div>
        <div className="font-mono text-xs text-[#636366]">
          {status?.service || 'tau-daemon'} v{status?.version || '--'}
        </div>
      </footer>
    </div>
  );
}
