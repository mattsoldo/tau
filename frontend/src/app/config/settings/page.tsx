'use client';

import { useState, useEffect, useCallback } from 'react';
import { useToast } from '@/contexts/ToastContext';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface SystemStatus {
  status: string;
  version: string;
  service: string;
  hardware?: {
    labjack: {
      connected: boolean;
      model: string;
      serial_number: string;
      read_count: number;
      write_count: number;
      error_count: number;
    };
    ola: {
      connected: boolean;
      running: boolean;
      max_universes: number;
      channel_set_count: number;
      non_zero_channels: number;
      send_errors: number;
    };
  };
}

export default function SettingsPage() {
  const { showToast } = useToast();

  // State
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch data
  const fetchData = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/status`);

      if (!res.ok) throw new Error('Failed to fetch system status');

      const data = await res.json();
      setStatus(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load settings');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    // Poll every 2 seconds
    const interval = setInterval(fetchData, 2000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Manual refresh
  const handleRefresh = async () => {
    setIsLoading(true);
    await fetchData();
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">System Status</h1>
        <p className="text-[#636366] mt-1">
          Hardware connection status and system information
        </p>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {/* Loading State */}
      {isLoading && !status ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin"></div>
        </div>
      ) : (
        <div className="space-y-6">
          {/* System Info Section */}
          <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] overflow-hidden">
            <div className="px-6 py-4 border-b border-[#2a2a2f] flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold">System Information</h2>
                <p className="text-sm text-[#636366] mt-1">
                  Daemon version and runtime status
                </p>
              </div>
              <button
                onClick={handleRefresh}
                className="p-2 hover:bg-white/5 rounded-lg transition-colors text-[#a1a1a6] hover:text-white"
                title="Refresh status"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                </svg>
              </button>
            </div>

            <div className="p-6">
              <div className="grid gap-4 md:grid-cols-3">
                <div className="p-4 rounded-lg bg-[#0a0a0b] border border-[#2a2a2f]">
                  <div className="text-sm text-[#636366] mb-1">Service</div>
                  <div className="font-mono text-lg font-medium">{status?.service || '--'}</div>
                </div>
                <div className="p-4 rounded-lg bg-[#0a0a0b] border border-[#2a2a2f]">
                  <div className="text-sm text-[#636366] mb-1">Version</div>
                  <div className="font-mono text-lg font-medium">{status?.version || '--'}</div>
                </div>
                <div className="p-4 rounded-lg bg-[#0a0a0b] border border-[#2a2a2f]">
                  <div className="text-sm text-[#636366] mb-1">Status</div>
                  <div className={`font-mono text-lg font-medium ${
                    status?.status === 'running' ? 'text-green-400' : 'text-red-400'
                  }`}>
                    {status?.status || '--'}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Hardware Connection Section */}
          <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] overflow-hidden">
            <div className="px-6 py-4 border-b border-[#2a2a2f]">
              <h2 className="text-lg font-semibold">Hardware Connection Status</h2>
              <p className="text-sm text-[#636366] mt-1">
                Real-time connection status for hardware interfaces
              </p>
            </div>

            <div className="p-6">
              <div className="grid gap-4 md:grid-cols-2">
                {/* LabJack Status */}
                <div className={`p-5 rounded-lg border transition-colors ${
                  status?.hardware?.labjack?.connected
                    ? 'bg-green-500/5 border-green-500/30'
                    : 'bg-red-500/5 border-red-500/30'
                }`}>
                  <div className="flex items-center gap-3 mb-3">
                    <div className={`w-3 h-3 rounded-full ${
                      status?.hardware?.labjack?.connected
                        ? 'bg-green-500 animate-pulse shadow-[0_0_8px_rgba(34,197,94,0.4)]'
                        : 'bg-red-500'
                    }`} />
                    <span className="font-medium text-lg">LabJack U3</span>
                  </div>
                  {status?.hardware?.labjack?.connected ? (
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span className="text-[#636366]">Model</span>
                        <span className="font-mono text-amber-400">{status.hardware.labjack.model}</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-[#636366]">Serial</span>
                        <span className="font-mono text-[#a1a1a6]">{status.hardware.labjack.serial_number}</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-[#636366]">Reads</span>
                        <span className="font-mono text-[#a1a1a6]">{status.hardware.labjack.read_count.toLocaleString()}</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-[#636366]">Errors</span>
                        <span className={`font-mono ${status.hardware.labjack.error_count > 0 ? 'text-red-400' : 'text-green-400'}`}>
                          {status.hardware.labjack.error_count}
                        </span>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-[#a1a1a6]">Not connected</p>
                  )}
                </div>

                {/* OLA Status */}
                <div className={`p-5 rounded-lg border transition-colors ${
                  status?.hardware?.ola?.connected
                    ? 'bg-green-500/5 border-green-500/30'
                    : 'bg-red-500/5 border-red-500/30'
                }`}>
                  <div className="flex items-center gap-3 mb-3">
                    <div className={`w-3 h-3 rounded-full ${
                      status?.hardware?.ola?.connected
                        ? 'bg-green-500 animate-pulse shadow-[0_0_8px_rgba(34,197,94,0.4)]'
                        : 'bg-red-500'
                    }`} />
                    <span className="font-medium text-lg">OLA / DMX</span>
                  </div>
                  {status?.hardware?.ola?.connected ? (
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span className="text-[#636366]">Universes</span>
                        <span className="font-mono text-amber-400">{status.hardware.ola.max_universes}</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-[#636366]">Active Channels</span>
                        <span className="font-mono text-[#a1a1a6]">{status.hardware.ola.non_zero_channels}</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-[#636366]">Channel Updates</span>
                        <span className="font-mono text-[#a1a1a6]">{status.hardware.ola.channel_set_count.toLocaleString()}</span>
                      </div>
                      <div className="flex justify-between text-sm">
                        <span className="text-[#636366]">Errors</span>
                        <span className={`font-mono ${status.hardware.ola.send_errors > 0 ? 'text-red-400' : 'text-green-400'}`}>
                          {status.hardware.ola.send_errors}
                        </span>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-[#a1a1a6]">Not connected</p>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
