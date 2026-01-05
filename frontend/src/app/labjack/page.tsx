'use client';

import { useEffect, useState, useRef } from 'react';

const API_URL = '';

// Timing constants for switch handling
const TAP_WINDOW_MS = 500;
const RAMP_INTERVAL_MS = 50;
const RAMP_STEP = 2;
const SCENE_1_BRIGHTNESS = 75;
const SCENE_2_BRIGHTNESS = 25;

interface LabJackStatus {
  connected: boolean;
  model?: string;
  serial_number?: string;
  firmware_version?: string;
  hardware_version?: string;
  read_count: number;
  write_count: number;
  error_count: number;
  digital_inputs: Record<string, boolean>;
}

interface SystemStatus {
  hardware?: {
    labjack: LabJackStatus;
    ola?: {
      connected: boolean;
    };
    overall_healthy: boolean;
  };
  event_loop?: {
    running: boolean;
  };
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

export default function LabJackPage() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [labjackStatus, setLabjackStatus] = useState<LabJackStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Light simulator state for each FIO channel
  const [lightStates, setLightStates] = useState<LightState[]>(
    Array(8).fill(null).map(() => ({ brightness: 0, lightOn: false, scene: 'off' as const }))
  );

  // Refs for tracking switch input state
  const switchRefs = useRef({
    lastState: Array(8).fill(false) as boolean[],
    pressTime: Array(8).fill(null) as (number | null)[],
    tapCount: Array(8).fill(0) as number[],
    holdInterval: Array(8).fill(null) as (ReturnType<typeof setTimeout> | null)[],
    tapTimeout: Array(8).fill(null) as (ReturnType<typeof setTimeout> | null)[],
    rampDirection: Array(8).fill(1) as number[],
  });

  const lightStatesRef = useRef(lightStates);
  lightStatesRef.current = lightStates;

  // Handle switch input for a channel
  const handleSwitchInput = (channel: number, switchPressed: boolean) => {
    const refs = switchRefs.current;
    const wasPressed = refs.lastState[channel];

    if (switchPressed === wasPressed) return;

    if (switchPressed && !wasPressed) {
      refs.pressTime[channel] = Date.now();

      refs.holdInterval[channel] = setTimeout(() => {
        const currentState = lightStatesRef.current[channel];

        if (currentState.lightOn) {
          refs.rampDirection[channel] = -1;
        } else {
          refs.rampDirection[channel] = 1;
          setLightStates(prev => {
            const newStates = [...prev];
            newStates[channel] = { brightness: 0, lightOn: true, scene: 'custom' };
            return newStates;
          });
        }

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

    if (!switchPressed && wasPressed) {
      const pressDuration = Date.now() - (refs.pressTime[channel] || 0);

      if (refs.holdInterval[channel]) {
        clearTimeout(refs.holdInterval[channel]);
        clearInterval(refs.holdInterval[channel]);
        refs.holdInterval[channel] = null;
      }

      if (pressDuration < TAP_WINDOW_MS) {
        refs.tapCount[channel]++;

        if (refs.tapTimeout[channel]) {
          clearTimeout(refs.tapTimeout[channel]);
        }

        refs.tapTimeout[channel] = setTimeout(() => {
          const count = refs.tapCount[channel];
          refs.tapCount[channel] = 0;
          refs.tapTimeout[channel] = null;

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

  // Fast polling for digital inputs
  useEffect(() => {
    let mounted = true;

    const pollDigitalInputs = async () => {
      if (!mounted) return;

      try {
        const response = await fetch(`${API_URL}/api/labjack/status`);
        if (!response.ok) return;

        const data = await response.json();
        setLabjackStatus(data.statistics);

        const inputs = data.statistics?.digital_inputs || {};
        for (let i = 0; i < 8; i++) {
          const key = String(i);
          const isPressed = inputs[key] === true;
          handleSwitchInput(i, isPressed);
        }
      } catch {
        // Ignore errors in fast poll
      }
    };

    const interval = setInterval(pollDigitalInputs, 100);
    pollDigitalInputs();

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  // Fetch system status
  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch(`${API_URL}/status`);
        if (!response.ok) throw new Error('Status API error');
        setStatus(await response.json());
        setError(null);
      } catch {
        setError('Connection error');
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 2000);
    return () => clearInterval(interval);
  }, []);

  const labjack = labjackStatus || status?.hardware?.labjack;
  const isConnected = labjack?.connected ?? false;

  return (
    <div className="min-h-screen bg-[#0a0a0b] text-white">
      {/* Ambient glows */}
      <div className="fixed top-[-200px] left-[20%] w-[500px] h-[500px] rounded-full bg-amber-500 opacity-[0.06] blur-[120px] pointer-events-none" />
      <div className="fixed bottom-[-200px] right-[10%] w-[400px] h-[400px] rounded-full bg-blue-500 opacity-[0.04] blur-[100px] pointer-events-none" />

      {/* Grid background */}
      <div className="fixed inset-0 pointer-events-none" style={{
        backgroundImage: 'linear-gradient(rgba(255,255,255,0.015) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.015) 1px, transparent 1px)',
        backgroundSize: '40px 40px'
      }} />

      <main className="relative z-5 px-8 py-8 max-w-[1600px] mx-auto">
        {/* Page Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">LabJack Monitor</h1>
            <p className="text-sm text-[#636366] mt-1">Digital I/O interface and switch testing</p>
          </div>
          <div className={`flex items-center gap-2.5 px-4 py-2.5 rounded-xl border ${isConnected ? 'bg-green-500/10 border-green-500/30' : 'bg-red-500/10 border-red-500/30'}`}>
            <div className={`w-2.5 h-2.5 rounded-full ${isConnected ? 'bg-green-500 shadow-[0_0_10px_rgba(34,197,94,0.5)]' : 'bg-red-500 shadow-[0_0_10px_rgba(239,68,68,0.5)]'}`} />
            <span className={`font-medium text-sm ${isConnected ? 'text-green-400' : 'text-red-400'}`}>
              {isConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
        </div>

        {error && (
          <div className="mb-6 px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-xl text-red-400 text-sm">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Device Info Card */}
          <div className="bg-[#161619] border border-[#2a2a2f] rounded-2xl p-6">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-amber-500/20 to-amber-600/10 border border-amber-500/30 flex items-center justify-center">
                <svg className="w-6 h-6 stroke-amber-500" fill="none" strokeWidth="1.5" viewBox="0 0 24 24">
                  <rect x="4" y="4" width="16" height="16" rx="2"/>
                  <circle cx="9" cy="9" r="1" fill="currentColor"/>
                  <circle cx="15" cy="9" r="1" fill="currentColor"/>
                  <circle cx="9" cy="15" r="1" fill="currentColor"/>
                  <circle cx="15" cy="15" r="1" fill="currentColor"/>
                </svg>
              </div>
              <div>
                <h3 className="text-lg font-semibold">Device Information</h3>
                <p className="text-xs text-[#636366] mt-0.5">{labjack?.model || 'Unknown Model'}</p>
              </div>
            </div>

            <div className="space-y-4">
              <div className="flex justify-between items-center py-3 border-b border-[#2a2a2f]">
                <span className="text-sm text-[#8e8e93]">Serial Number</span>
                <span className="font-mono text-sm text-white">{labjack?.serial_number || '--'}</span>
              </div>
              <div className="flex justify-between items-center py-3 border-b border-[#2a2a2f]">
                <span className="text-sm text-[#8e8e93]">Model</span>
                <span className="font-mono text-sm text-white">{labjack?.model || '--'}</span>
              </div>
              <div className="flex justify-between items-center py-3 border-b border-[#2a2a2f]">
                <span className="text-sm text-[#8e8e93]">Status</span>
                <span className={`font-mono text-xs px-2 py-1 rounded ${isConnected ? 'bg-green-500/15 text-green-400' : 'bg-red-500/15 text-red-400'}`}>
                  {isConnected ? 'ONLINE' : 'OFFLINE'}
                </span>
              </div>
            </div>
          </div>

          {/* Statistics Card */}
          <div className="bg-[#161619] border border-[#2a2a2f] rounded-2xl p-6">
            <h3 className="text-sm font-medium uppercase tracking-wider text-[#636366] mb-6">I/O Statistics</h3>

            <div className="grid grid-cols-3 gap-4">
              <div className="bg-[#111113] rounded-xl p-4 text-center">
                <div className="font-mono text-3xl font-semibold text-amber-400">
                  {formatNumber(labjack?.read_count || 0)}
                </div>
                <div className="text-xs text-[#636366] mt-2">Reads</div>
              </div>
              <div className="bg-[#111113] rounded-xl p-4 text-center">
                <div className="font-mono text-3xl font-semibold text-white">
                  {formatNumber(labjack?.write_count || 0)}
                </div>
                <div className="text-xs text-[#636366] mt-2">Writes</div>
              </div>
              <div className="bg-[#111113] rounded-xl p-4 text-center">
                <div className={`font-mono text-3xl font-semibold ${(labjack?.error_count || 0) > 0 ? 'text-red-400' : 'text-white'}`}>
                  {labjack?.error_count || 0}
                </div>
                <div className="text-xs text-[#636366] mt-2">Errors</div>
              </div>
            </div>

            <div className="mt-6 pt-6 border-t border-[#2a2a2f]">
              <div className="text-xs text-[#636366] mb-3">Read/Write Ratio</div>
              <div className="h-2 bg-[#111113] rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-amber-600 to-amber-400 rounded-full"
                  style={{
                    width: `${Math.min(100, ((labjack?.read_count || 0) / ((labjack?.read_count || 0) + (labjack?.write_count || 1))) * 100)}%`
                  }}
                />
              </div>
            </div>
          </div>

          {/* Quick Status Card */}
          <div className="bg-[#161619] border border-[#2a2a2f] rounded-2xl p-6">
            <h3 className="text-sm font-medium uppercase tracking-wider text-[#636366] mb-6">System Integration</h3>

            <div className="space-y-4">
              <div className="flex items-center justify-between p-4 bg-[#111113] rounded-xl">
                <div className="flex items-center gap-3">
                  <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.4)]' : 'bg-red-500'}`} />
                  <span className="text-sm font-medium">LabJack U3-HV</span>
                </div>
                <span className={`text-xs px-2 py-1 rounded ${isConnected ? 'bg-green-500/15 text-green-400' : 'bg-red-500/15 text-red-400'}`}>
                  {isConnected ? 'Active' : 'Inactive'}
                </span>
              </div>
              <div className="flex items-center justify-between p-4 bg-[#111113] rounded-xl">
                <div className="flex items-center gap-3">
                  <div className={`w-3 h-3 rounded-full ${status?.hardware?.ola?.connected ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.4)]' : 'bg-red-500'}`} />
                  <span className="text-sm font-medium">OLA DMX Bridge</span>
                </div>
                <span className={`text-xs px-2 py-1 rounded ${status?.hardware?.ola?.connected ? 'bg-green-500/15 text-green-400' : 'bg-red-500/15 text-red-400'}`}>
                  {status?.hardware?.ola?.connected ? 'Active' : 'Inactive'}
                </span>
              </div>
              <div className="flex items-center justify-between p-4 bg-[#111113] rounded-xl">
                <div className="flex items-center gap-3">
                  <div className={`w-3 h-3 rounded-full ${status?.event_loop?.running ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.4)]' : 'bg-red-500'}`} />
                  <span className="text-sm font-medium">Event Loop</span>
                </div>
                <span className={`text-xs px-2 py-1 rounded ${status?.event_loop?.running ? 'bg-green-500/15 text-green-400' : 'bg-red-500/15 text-red-400'}`}>
                  {status?.event_loop?.running ? 'Running' : 'Stopped'}
                </span>
              </div>
            </div>
          </div>

          {/* FIO Channels - Full Width */}
          <div className="lg:col-span-3 bg-[#161619] border border-[#2a2a2f] rounded-2xl p-6">
            <div className="flex justify-between items-center mb-6">
              <div>
                <h3 className="text-lg font-semibold">FIO Digital Inputs</h3>
                <p className="text-xs text-[#636366] mt-1">8-channel digital input monitoring with switch simulator</p>
              </div>
              <div className="flex items-center gap-4 text-xs text-[#636366]">
                <span className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full bg-amber-500" /> Active
                </span>
                <span className="flex items-center gap-1.5">
                  <div className="w-2 h-2 rounded-full bg-[#3a3a3f]" /> Inactive
                </span>
                <span className="px-2 py-1 bg-[#111113] rounded text-[#8e8e93]">tap / double / triple / hold</span>
              </div>
            </div>

            <div className="grid grid-cols-4 lg:grid-cols-8 gap-4">
              {[0, 1, 2, 3, 4, 5, 6, 7].map(i => {
                const isHigh = labjack?.digital_inputs?.[String(i)] === true;
                const light = lightStates[i];
                const brightness = light.brightness;

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
                  scene1: 'Scene 1',
                  scene2: 'Scene 2',
                  custom: `${Math.round(brightness)}%`,
                };

                return (
                  <div
                    key={i}
                    className="relative rounded-2xl overflow-hidden border-2 transition-all duration-200"
                    style={{
                      borderColor: isHigh ? 'rgb(245 158 11)' : brightness > 0 ? 'rgb(245 158 11 / 0.3)' : 'rgb(42 42 47)',
                      boxShadow: isHigh ? '0 0 20px rgba(245, 158, 11, 0.2)' : 'none'
                    }}
                  >
                    {/* Light glow background */}
                    <div
                      className="absolute inset-0 transition-opacity duration-300"
                      style={{
                        background: 'linear-gradient(135deg, rgb(245 158 11), rgb(253 224 71))',
                        opacity: brightness / 100,
                      }}
                    />
                    {/* Dark overlay */}
                    <div
                      className="absolute inset-0 bg-[#111113] transition-opacity duration-300"
                      style={{ opacity: 1 - (brightness / 100) * 0.85 }}
                    />
                    {/* Content */}
                    <div className="relative z-10 p-4 flex flex-col items-center min-h-[140px]">
                      {/* Channel header */}
                      <div className="flex items-center justify-between w-full mb-3">
                        <span className="font-mono text-xs font-semibold text-[#8e8e93]">FIO{i}</span>
                        <span className={`font-mono text-[10px] px-2 py-0.5 rounded-full ${isHigh ? 'bg-amber-500/30 text-amber-400' : 'bg-[#2a2a2f] text-[#636366]'}`}>
                          {isHigh ? 'HIGH' : 'LOW'}
                        </span>
                      </div>

                      {/* Brightness display */}
                      <div className={`font-mono text-4xl font-bold my-2 ${brightness > 50 ? 'text-[#111113]' : 'text-white'}`}>
                        {Math.round(brightness)}%
                      </div>

                      {/* Scene indicator */}
                      <div className={`font-mono text-xs mt-1 ${brightness > 50 ? 'text-[#111113]/70' : sceneColors[light.scene]}`}>
                        {sceneLabels[light.scene]}
                      </div>

                      {/* Progress bar */}
                      <div className="w-full h-1.5 bg-black/20 rounded-full mt-3 overflow-hidden">
                        <div
                          className="h-full bg-white/90 rounded-full transition-all duration-200"
                          style={{ width: `${brightness}%` }}
                        />
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
