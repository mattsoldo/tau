'use client';

import { useEffect, useState, useRef } from 'react';
import Link from 'next/link';

// Navigation menu items
const NAV_ITEMS = [
  { href: '/', label: 'Home', icon: 'M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6' },
  { href: '/dashboard', label: 'Dashboard', icon: 'M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z', active: true },
  { href: '/test', label: 'Light Test', icon: 'M12 18v-5.25m0 0a6.01 6.01 0 001.5-.189m-1.5.189a6.01 6.01 0 01-1.5-.189m3.75 7.478a12.06 12.06 0 01-4.5 0m3.75 2.383a14.406 14.406 0 01-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 10-7.517 0c.85.493 1.509 1.333 1.509 2.316V18' },
  { href: '/config', label: 'Configuration', icon: 'M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z M15 12a3 3 0 11-6 0 3 3 0 016 0z' },
];

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Timing constants (PRD Section 10.1-10.2)
const TAP_WINDOW_MS = 500;
const RAMP_INTERVAL_MS = 50;
const RAMP_STEP = 2;
const SCENE_1_BRIGHTNESS = 75;
const SCENE_2_BRIGHTNESS = 25;

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
  const [activeOverrides, setActiveOverrides] = useState<ActiveOverride[]>([]);
  const [currentTime, setCurrentTime] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [expandedFixtures, setExpandedFixtures] = useState<Set<number>>(new Set());
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set());
  const [menuOpen, setMenuOpen] = useState(false);
  const [groupFixtures, setGroupFixtures] = useState<Map<number, number[]>>(new Map());

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
    const updateTime = () => {
      setCurrentTime(new Date().toLocaleTimeString('en-US', { hour12: false }));
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
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

        // Fetch fixtures for each group
        const groupFixturesMap = new Map<number, number[]>();
        await Promise.all(
          groupsData.map(async (g: Group) => {
            try {
              const res = await fetch(`${API_URL}/api/groups/${g.id}/fixtures`);
              if (res.ok) {
                const fixtureList = await res.json();
                groupFixturesMap.set(g.id, fixtureList.map((f: { id: number }) => f.id));
              }
            } catch {
              // Ignore errors
            }
          })
        );
        setGroupFixtures(groupFixturesMap);

        // Build models map
        const modelsData = await modelsRes.json();
        const modelsMap = new Map<number, FixtureModel>();
        modelsData.forEach((m: FixtureModel) => modelsMap.set(m.id, m));
        setFixtureModels(modelsMap);

        // Fetch fixture states
        const statesMap = new Map<number, FixtureState>();
        await Promise.all(
          fixturesData.map(async (f: Fixture) => {
            try {
              const stateRes = await fetch(`${API_URL}/api/fixtures/${f.id}/state`);
              if (stateRes.ok) {
                const state = await stateRes.json();
                statesMap.set(f.id, state);
              }
            } catch {
              // Ignore individual state fetch errors
            }
          })
        );
        setFixtureStates(statesMap);

        setError(null);
      } catch (err) {
        setError('Connection error');
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 2000); // Slower poll for larger data set
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
    const interval = setInterval(fetchOverrides, 2000);
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
      }
    } catch {
      // Ignore errors
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
      }
    } catch {
      // Ignore errors
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
      await fetch(`${API_URL}/api/control/fixtures/${fixtureId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brightness: newBrightness }),
      });
      // Optimistic update
      setFixtureStates(prev => {
        const newMap = new Map(prev);
        const existing = newMap.get(fixtureId);
        if (existing) {
          newMap.set(fixtureId, { ...existing, goal_brightness: newBrightness * 1000, is_on: newBrightness > 0 });
        }
        return newMap;
      });
    } catch {
      // Ignore errors
    }
  };

  // Control fixture brightness
  const handleFixtureBrightness = async (fixtureId: number, brightness: number) => {
    try {
      await fetch(`${API_URL}/api/control/fixtures/${fixtureId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brightness }),
      });
      setFixtureStates(prev => {
        const newMap = new Map(prev);
        const existing = newMap.get(fixtureId);
        if (existing) {
          newMap.set(fixtureId, { ...existing, goal_brightness: brightness * 1000, is_on: brightness > 0 });
        }
        return newMap;
      });
    } catch {
      // Ignore errors
    }
  };

  // Control fixture CCT
  const handleFixtureCCT = async (fixtureId: number, cct: number) => {
    try {
      await fetch(`${API_URL}/api/control/fixtures/${fixtureId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ color_temp: cct }),
      });
      setFixtureStates(prev => {
        const newMap = new Map(prev);
        const existing = newMap.get(fixtureId);
        if (existing) {
          newMap.set(fixtureId, { ...existing, goal_cct: cct });
        }
        return newMap;
      });
    } catch {
      // Ignore errors
    }
  };

  // Control group brightness
  const handleGroupBrightness = async (groupId: number, brightness: number) => {
    try {
      await fetch(`${API_URL}/api/control/groups/${groupId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brightness }),
      });
    } catch {
      // Ignore errors
    }
  };

  // Control group CCT
  const handleGroupCCT = async (groupId: number, cct: number) => {
    try {
      await fetch(`${API_URL}/api/control/groups/${groupId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ color_temp: cct }),
      });
    } catch {
      // Ignore errors
    }
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

      {/* Header */}
      <header className="relative z-10 px-6 md:px-10 py-4 md:py-6 flex justify-between items-center border-b border-[#1f1f24] bg-[#0a0a0b]/80 backdrop-blur-xl">
        <div className="flex items-center gap-3.5">
          {/* Hamburger Menu Button */}
          <button
            onClick={() => setMenuOpen(!menuOpen)}
            className="p-2 rounded-lg hover:bg-white/10 transition-colors"
            aria-label="Toggle navigation menu"
          >
            <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              {menuOpen ? (
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
              )}
            </svg>
          </button>
          <Link href="/" className="flex items-center gap-3">
            <div className="w-[38px] h-[38px] bg-gradient-to-br from-amber-500 to-amber-700 rounded-[10px] flex items-center justify-center shadow-[0_4px_20px_rgba(245,158,11,0.15)]">
              <svg className="w-[22px] h-[22px] fill-[#0a0a0b]" viewBox="0 0 24 24">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
              </svg>
            </div>
            <div className="text-[22px] font-semibold tracking-tight">
              Tau <span className="text-[#636366] font-normal">Lighting</span>
            </div>
          </Link>
        </div>
        <div className="flex items-center gap-4 md:gap-6">
          <div className="hidden sm:flex items-center gap-2 px-4 py-2 bg-[#161619] border border-[#2a2a2f] rounded-full text-[13px] font-mono">
            <span className={`w-2 h-2 rounded-full ${isHealthy ? 'bg-green-500 shadow-[0_0_12px_#22c55e] animate-pulse' : 'bg-red-500 shadow-[0_0_12px_#ef4444]'}`} />
            <span>{error || (isHealthy ? 'All Systems Operational' : 'Issues Detected')}</span>
          </div>
          <div className="font-mono text-[13px] text-[#a1a1a6]">{currentTime}</div>
        </div>
      </header>

      {/* Navigation Menu Overlay */}
      {menuOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" onClick={() => setMenuOpen(false)}>
          <nav
            className="absolute left-0 top-0 bottom-0 w-72 bg-[#111113] border-r border-[#2a2a2f] shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-5 border-b border-[#2a2a2f] flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 bg-gradient-to-br from-amber-500 to-amber-700 rounded-lg flex items-center justify-center">
                  <svg className="w-5 h-5 fill-[#0a0a0b]" viewBox="0 0 24 24">
                    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
                  </svg>
                </div>
                <span className="text-lg font-semibold">Tau Lighting</span>
              </div>
              <button
                onClick={() => setMenuOpen(false)}
                className="p-2 rounded-lg hover:bg-white/10 transition-colors"
              >
                <svg className="w-5 h-5 text-[#636366]" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-4 space-y-1">
              {NAV_ITEMS.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setMenuOpen(false)}
                  className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-all ${
                    item.active
                      ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                      : 'text-[#a1a1a6] hover:text-white hover:bg-white/5'
                  }`}
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d={item.icon} />
                  </svg>
                  <span className="font-medium">{item.label}</span>
                </Link>
              ))}
            </div>
            <div className="absolute bottom-0 left-0 right-0 p-4 border-t border-[#2a2a2f]">
              <a
                href="http://localhost:8000/docs"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-3 px-4 py-3 rounded-lg text-[#636366] hover:text-white hover:bg-white/5 transition-all"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                </svg>
                <span className="font-medium">API Docs</span>
                <svg className="w-4 h-4 ml-auto" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
                </svg>
              </a>
            </div>
          </nav>
        </div>
      )}

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

            {/* Empty state */}
            {groups.length === 0 && fixtures.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-center">
                <div className="w-16 h-16 rounded-2xl bg-[#111113] border border-[#2a2a2f] flex items-center justify-center mb-4">
                  <svg className="w-8 h-8 stroke-[#636366]" fill="none" strokeWidth="1.5" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 18v-5.25m0 0a6.01 6.01 0 001.5-.189m-1.5.189a6.01 6.01 0 01-1.5-.189m3.75 7.478a12.06 12.06 0 01-4.5 0m3.75 2.383a14.406 14.406 0 01-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 10-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" />
                  </svg>
                </div>
                <p className="text-[15px] font-medium text-white mb-1">No Fixtures Configured</p>
                <p className="text-[13px] text-[#636366] mb-4">Add fixtures and groups to control your lights</p>
                <Link href="/config/fixtures" className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg text-sm transition-colors">
                  Configure Fixtures
                </Link>
              </div>
            ) : (
              <div className="flex flex-col gap-3 max-h-[500px] overflow-y-auto pr-1 custom-scrollbar">
                {/* Groups Section */}
                {groups
                  .filter(g => !g.is_system)
                  .sort((a, b) => a.name.localeCompare(b.name))
                  .map(group => {
                    const isExpanded = expandedGroups.has(group.id);
                    const fixtureIds = groupFixtures.get(group.id) || [];
                    const groupFixturesList = fixtures.filter(f => fixtureIds.includes(f.id));
                    const hasActiveFixtures = groupFixturesList.some(f => fixtureStates.get(f.id)?.is_on);

                    // Calculate average brightness for group
                    const avgBrightness = groupFixturesList.length > 0
                      ? Math.round(groupFixturesList.reduce((sum, f) => {
                          const state = fixtureStates.get(f.id);
                          return sum + (state ? state.goal_brightness / 10 : 0);
                        }, 0) / groupFixturesList.length)
                      : 0;

                    return (
                      <div
                        key={`group-${group.id}`}
                        className={`bg-[#111113] rounded-xl overflow-hidden border transition-all ${
                          hasActiveFixtures ? 'border-amber-500/30' : 'border-transparent'
                        }`}
                      >
                        <div
                          className="flex items-center gap-3 px-4 py-3.5 cursor-pointer hover:bg-white/[0.03] transition-colors"
                          onClick={() => toggleGroupExpand(group.id)}
                        >
                          <svg
                            className={`w-4 h-4 text-[#636366] transition-transform flex-shrink-0 ${isExpanded ? 'rotate-90' : ''}`}
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            viewBox="0 0 24 24"
                          >
                            <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                          </svg>
                          <div className={`w-3 h-3 rounded-full flex-shrink-0 transition-all ${
                            hasActiveFixtures
                              ? 'bg-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.5)]'
                              : 'bg-purple-500 shadow-[0_0_8px_rgba(168,85,247,0.3)]'
                          }`} />
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-[15px] font-medium text-white truncate">{group.name}</span>
                              <span className="text-[10px] text-[#636366] font-mono">{groupFixturesList.length} fixtures</span>
                            </div>
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0">
                            {group.circadian_enabled && (
                              <span className="text-[9px] px-1.5 py-0.5 bg-blue-500/20 text-blue-400 rounded font-medium">CIRCADIAN</span>
                            )}
                            <span className="font-mono text-[13px] text-[#a1a1a6] w-10 text-right">{avgBrightness}%</span>
                          </div>
                        </div>

                        {isExpanded && (
                          <div className="border-t border-[#2a2a2f]">
                            {/* Group Controls */}
                            <div className="px-4 py-3 bg-[#0d0d0f] space-y-3">
                              <div className="flex items-center gap-3">
                                <span className="text-[11px] text-[#636366] w-20 flex-shrink-0">Brightness</span>
                                <div className="flex-1 relative h-2">
                                  <input
                                    type="range"
                                    min={0}
                                    max={100}
                                    defaultValue={avgBrightness}
                                    className="w-full h-2 rounded-full appearance-none bg-[#2a2a2f] cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-amber-500 [&::-webkit-slider-thumb]:shadow-lg [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-amber-400 [&::-webkit-slider-thumb]:cursor-pointer"
                                    onChange={(e) => handleGroupBrightness(group.id, parseInt(e.target.value) / 100)}
                                  />
                                </div>
                              </div>
                              <div className="flex items-center gap-3">
                                <span className="text-[11px] text-[#636366] w-20 flex-shrink-0">CCT</span>
                                <div className="flex-1 relative h-2">
                                  <input
                                    type="range"
                                    min={2700}
                                    max={6500}
                                    defaultValue={4000}
                                    className="w-full h-2 rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white [&::-webkit-slider-thumb]:shadow-lg [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-gray-300 [&::-webkit-slider-thumb]:cursor-pointer"
                                    style={{ background: `linear-gradient(to right, ${kelvinToColor(2700)}, ${kelvinToColor(6500)})` }}
                                    onChange={(e) => handleGroupCCT(group.id, parseInt(e.target.value))}
                                  />
                                </div>
                              </div>
                            </div>

                            {/* Fixtures in Group */}
                            {groupFixturesList.length > 0 && (
                              <div className="px-3 py-2 space-y-1">
                                {groupFixturesList.map(fixture => {
                                  const state = fixtureStates.get(fixture.id);
                                  const brightness = state ? Math.round(state.goal_brightness / 10) : 0;
                                  const isOn = state?.is_on ?? false;

                                  return (
                                    <div
                                      key={`gf-${fixture.id}`}
                                      className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/[0.02] transition-colors"
                                    >
                                      <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
                                        isOn ? 'bg-amber-500 shadow-[0_0_6px_rgba(245,158,11,0.4)]' : 'bg-[#3a3a3f]'
                                      }`} />
                                      <span className="flex-1 text-[13px] text-[#a1a1a6] truncate">{fixture.name}</span>
                                      <div className="w-16 h-1 bg-[#2a2a2f] rounded-full overflow-hidden flex-shrink-0">
                                        <div
                                          className="h-full bg-gradient-to-r from-amber-700 to-amber-500 rounded-full transition-all"
                                          style={{ width: `${brightness}%` }}
                                        />
                                      </div>
                                      <span className="font-mono text-[11px] text-[#636366] w-8 text-right flex-shrink-0">
                                        {brightness}%
                                      </span>
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          handleFixtureToggle(fixture.id);
                                        }}
                                        className={`w-9 h-5 rounded-full transition-all relative flex-shrink-0 ${
                                          isOn ? 'bg-amber-500' : 'bg-[#3a3a3f]'
                                        }`}
                                      >
                                        <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-all shadow ${
                                          isOn ? 'left-[18px]' : 'left-0.5'
                                        }`} />
                                      </button>
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}

                {/* Ungrouped Fixtures Section */}
                {(() => {
                  const groupedFixtureIds = new Set<number>();
                  groupFixtures.forEach(ids => ids.forEach(id => groupedFixtureIds.add(id)));
                  const ungroupedFixtures = fixtures.filter(f => !groupedFixtureIds.has(f.id));

                  if (ungroupedFixtures.length === 0) return null;

                  return (
                    <div className="bg-[#111113] rounded-xl overflow-hidden">
                      <div
                        className="flex items-center gap-3 px-4 py-3.5 cursor-pointer hover:bg-white/[0.03] transition-colors border-b border-[#2a2a2f]"
                        onClick={() => toggleGroupExpand(-1)}
                      >
                        <svg
                          className={`w-4 h-4 text-[#636366] transition-transform flex-shrink-0 ${expandedGroups.has(-1) ? 'rotate-90' : ''}`}
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                          viewBox="0 0 24 24"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                        </svg>
                        <div className="w-3 h-3 rounded-full bg-gray-500 flex-shrink-0" />
                        <span className="flex-1 text-[15px] font-medium text-white">Ungrouped Fixtures</span>
                        <span className="text-[10px] text-[#636366] font-mono">{ungroupedFixtures.length} fixtures</span>
                      </div>

                      {expandedGroups.has(-1) && (
                        <div className="px-3 py-2 space-y-1">
                          {ungroupedFixtures.map(fixture => {
                            const state = fixtureStates.get(fixture.id);
                            const model = fixtureModels.get(fixture.fixture_model_id);
                            const isExpanded = expandedFixtures.has(fixture.id);
                            const brightness = state ? Math.round(state.goal_brightness / 10) : 0;
                            const cct = state?.goal_cct ?? 2700;
                            const cctMin = model?.cct_min_kelvin ?? 2700;
                            const cctMax = model?.cct_max_kelvin ?? 6500;
                            const isOn = state?.is_on ?? false;

                            return (
                              <div key={`fixture-${fixture.id}`} className="bg-[#0d0d0f] rounded-lg overflow-hidden">
                                <div className="flex items-center gap-3 px-3 py-2.5">
                                  <button
                                    onClick={() => toggleFixtureExpand(fixture.id)}
                                    className="p-0.5 hover:bg-white/10 rounded transition-colors flex-shrink-0"
                                  >
                                    <svg
                                      className={`w-3.5 h-3.5 text-[#636366] transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                                      fill="none"
                                      stroke="currentColor"
                                      strokeWidth="2"
                                      viewBox="0 0 24 24"
                                    >
                                      <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                                    </svg>
                                  </button>
                                  <div className={`w-2 h-2 rounded-full flex-shrink-0 transition-all ${
                                    isOn ? 'bg-amber-500 shadow-[0_0_6px_rgba(245,158,11,0.4)]' : 'bg-[#3a3a3f]'
                                  }`} />
                                  <span className="flex-1 text-[13px] font-medium text-white truncate">{fixture.name}</span>
                                  <span className="font-mono text-[9px] text-[#636366] px-1.5 py-0.5 bg-[#1a1a1d] rounded flex-shrink-0">
                                    CH {fixture.dmx_channel_start}
                                  </span>
                                  <div className="w-16 h-1 bg-[#2a2a2f] rounded-full overflow-hidden flex-shrink-0">
                                    <div
                                      className="h-full bg-gradient-to-r from-amber-700 to-amber-500 rounded-full transition-all"
                                      style={{ width: `${brightness}%` }}
                                    />
                                  </div>
                                  <span className="font-mono text-[11px] text-[#a1a1a6] w-8 text-right flex-shrink-0">
                                    {brightness}%
                                  </span>
                                  <button
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      handleFixtureToggle(fixture.id);
                                    }}
                                    className={`w-9 h-5 rounded-full transition-all relative flex-shrink-0 ${
                                      isOn ? 'bg-amber-500' : 'bg-[#3a3a3f]'
                                    }`}
                                  >
                                    <div className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-all shadow ${
                                      isOn ? 'left-[18px]' : 'left-0.5'
                                    }`} />
                                  </button>
                                </div>

                                {isExpanded && (
                                  <div className="px-3 pb-3 pt-2 border-t border-[#2a2a2f] space-y-2.5">
                                    <div className="flex items-center gap-3">
                                      <span className="text-[10px] text-[#636366] w-16 flex-shrink-0">Brightness</span>
                                      <input
                                        type="range"
                                        min={0}
                                        max={100}
                                        value={brightness}
                                        className="flex-1 h-1.5 rounded-full appearance-none bg-[#2a2a2f] cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-amber-500 [&::-webkit-slider-thumb]:cursor-pointer"
                                        onChange={(e) => handleFixtureBrightness(fixture.id, parseInt(e.target.value) / 100)}
                                      />
                                      <span className="font-mono text-[10px] text-[#a1a1a6] w-8 text-right flex-shrink-0">{brightness}%</span>
                                    </div>
                                    <div className="flex items-center gap-3">
                                      <span className="text-[10px] text-[#636366] w-16 flex-shrink-0">CCT</span>
                                      <input
                                        type="range"
                                        min={cctMin}
                                        max={cctMax}
                                        value={cct}
                                        className="flex-1 h-1.5 rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-white [&::-webkit-slider-thumb]:cursor-pointer"
                                        style={{ background: `linear-gradient(to right, ${kelvinToColor(cctMin)}, ${kelvinToColor(cctMax)})` }}
                                        onChange={(e) => handleFixtureCCT(fixture.id, parseInt(e.target.value))}
                                      />
                                      <span className="font-mono text-[10px] text-[#a1a1a6] w-10 text-right flex-shrink-0">{cct}K</span>
                                    </div>
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })()}
              </div>
            )}
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
      <footer className="relative z-5 px-10 py-5 border-t border-[#1f1f24] flex justify-between items-center mt-5">
        <div className="flex gap-6">
          <Link href="/" className="text-[13px] text-[#636366] hover:text-[#a1a1a6] transition-colors">Home</Link>
          <Link href="/test" className="text-[13px] text-[#636366] hover:text-[#a1a1a6] transition-colors">Light Test</Link>
          <Link href="/config" className="text-[13px] text-[#636366] hover:text-[#a1a1a6] transition-colors">Config</Link>
          <a href="http://localhost:8000/docs" target="_blank" className="text-[13px] text-[#636366] hover:text-[#a1a1a6] transition-colors">API Docs</a>
        </div>
        <div className="font-mono text-[12px] text-[#636366]">
          {status?.service || 'tau-daemon'} v{status?.version || '--'}
        </div>
      </footer>
    </div>
  );
}
