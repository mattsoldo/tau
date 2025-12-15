'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

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
  const [currentTime, setCurrentTime] = useState('');
  const [error, setError] = useState<string | null>(null);

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
        const [statusRes, fixturesRes] = await Promise.all([
          fetch(`${API_URL}/status`),
          fetch(`${API_URL}/api/fixtures/`)
        ]);

        if (!statusRes.ok) throw new Error('Status API error');

        setStatus(await statusRes.json());
        setFixtures(await fixturesRes.json());
        setError(null);
      } catch (err) {
        setError('Connection error');
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 1000);
    return () => clearInterval(interval);
  }, []);

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
      <header className="relative z-10 px-10 py-6 flex justify-between items-center border-b border-[#1f1f24] bg-[#0a0a0b]/80 backdrop-blur-xl">
        <div className="flex items-center gap-3.5">
          <div className="w-[38px] h-[38px] bg-gradient-to-br from-amber-500 to-amber-700 rounded-[10px] flex items-center justify-center shadow-[0_4px_20px_rgba(245,158,11,0.15)]">
            <svg className="w-[22px] h-[22px] fill-[#0a0a0b]" viewBox="0 0 24 24">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
          </div>
          <div className="text-[22px] font-semibold tracking-tight">
            Tau <span className="text-[#636366] font-normal">Lighting</span>
          </div>
        </div>
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2 px-4 py-2 bg-[#161619] border border-[#2a2a2f] rounded-full text-[13px] font-mono">
            <span className={`w-2 h-2 rounded-full ${isHealthy ? 'bg-green-500 shadow-[0_0_12px_#22c55e] animate-pulse' : 'bg-red-500 shadow-[0_0_12px_#ef4444]'}`} />
            <span>{error || (isHealthy ? 'All Systems Operational' : 'Issues Detected')}</span>
          </div>
          <div className="font-mono text-[13px] text-[#a1a1a6]">{currentTime}</div>
        </div>
      </header>

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

          {/* FIO Channels Card */}
          <div className="bg-[#161619] border border-[#2a2a2f] rounded-2xl p-6">
            <div className="flex justify-between items-center mb-5">
              <span className="text-[13px] font-medium uppercase tracking-wider text-[#636366]">FIO Channels</span>
            </div>
            <div className="grid grid-cols-4 gap-2">
              {[0, 1, 2, 3, 4, 5, 6, 7].map(i => {
                const isHigh = status?.hardware?.labjack?.digital_inputs?.[String(i)] === true;
                return (
                  <div key={i} className={`aspect-square rounded-[10px] flex flex-col items-center justify-center border transition-all ${isHigh ? 'bg-amber-500/15 border-amber-500' : 'bg-[#111113] border-[#2a2a2f]'}`}>
                    <span className="font-mono text-[10px] text-[#636366]">FIO{i}</span>
                    <span className={`font-mono text-[11px] font-semibold mt-1 ${isHigh ? 'text-amber-500' : 'text-[#a1a1a6]'}`}>
                      {isHigh ? 'HIGH' : 'LOW'}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Fixtures Card */}
          <div className="col-span-2 bg-[#161619] border border-[#2a2a2f] rounded-2xl p-6">
            <div className="flex justify-between items-center mb-5">
              <span className="text-[13px] font-medium uppercase tracking-wider text-[#636366]">Fixtures</span>
              <span className="font-mono text-[11px] px-2.5 py-1 rounded-md bg-green-500/15 text-green-500 border border-green-500/20">
                {fixtures.length} fixtures
              </span>
            </div>
            <div className="flex flex-col gap-2.5">
              {fixtures.map(fixture => (
                <div key={fixture.id} className="flex items-center gap-4 px-4 py-3.5 bg-[#111113] rounded-xl hover:bg-white/[0.04] transition-colors">
                  <div className="w-2.5 h-2.5 rounded-full bg-amber-500 shadow-[0_0_12px_rgba(245,158,11,0.15)]" />
                  <span className="flex-1 text-sm font-medium">{fixture.name}</span>
                  <span className="font-mono text-[12px] text-[#636366] px-2.5 py-1 bg-[#161619] rounded-md">
                    DMX {fixture.dmx_channel_start}
                  </span>
                  <div className="w-[120px] h-1.5 bg-[#2a2a2f] rounded-full overflow-hidden">
                    <div className="h-full w-0 bg-gradient-to-r from-amber-700 to-amber-500 rounded-full transition-all" />
                  </div>
                  <span className="font-mono text-[13px] text-[#a1a1a6] w-[45px] text-right">--</span>
                </div>
              ))}
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
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-5 px-10 py-5 border-t border-[#1f1f24] flex justify-between items-center mt-5">
        <div className="flex gap-6">
          <Link href="/" className="text-[13px] text-[#636366] hover:text-[#a1a1a6] transition-colors">Home</Link>
          <a href="http://localhost:8000/docs" target="_blank" className="text-[13px] text-[#636366] hover:text-[#a1a1a6] transition-colors">API Docs</a>
        </div>
        <div className="font-mono text-[12px] text-[#636366]">
          {status?.service || 'tau-daemon'} v{status?.version || '--'}
        </div>
      </footer>
    </div>
  );
}
