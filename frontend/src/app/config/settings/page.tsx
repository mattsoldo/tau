'use client';

import { useState, useEffect, useCallback } from 'react';
import UpdatePanel from '../../../components/UpdatePanel';
import SwitchConfigPanel from '../../../components/SwitchConfigPanel';

const API_URL = ''; // Use relative paths for nginx proxy

interface HardwareAvailability {
  labjack_available: boolean;
  labjack_details: string | null;
  ola_available: boolean;
  ola_details: string | null;
}

interface SystemStatus {
  hardware?: {
    labjack: {
      connected: boolean;
      model: string;
      serial_number: string;
      error_count: number;
    };
    ola: {
      connected: boolean;
      max_universes: number;
      send_errors: number;
    };
  };
}

export default function SettingsPage() {
  // State
  const [hardware, setHardware] = useState<HardwareAvailability | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch data
  const fetchData = useCallback(async () => {
    try {
      const [hardwareRes, statusRes] = await Promise.all([
        fetch(`${API_URL}/api/config/hardware-availability`),
        fetch(`${API_URL}/status`),
      ]);

      if (!hardwareRes.ok) throw new Error('Failed to fetch hardware availability');
      if (!statusRes.ok) throw new Error('Failed to fetch system status');

      const [hardwareData, statusData] = await Promise.all([
        hardwareRes.json(),
        statusRes.json(),
      ]);

      setHardware(hardwareData);
      setStatus(statusData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load settings');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    // Poll every 2 seconds for live updates
    const interval = setInterval(fetchData, 2000);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Refresh hardware detection
  const handleRefreshHardware = async () => {
    try {
      const res = await fetch(`${API_URL}/api/config/hardware-availability`);
      if (!res.ok) throw new Error('Failed to refresh hardware');

      const data = await res.json();
      setHardware(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to refresh hardware');
    }
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold">System Settings</h1>
        <p className="text-[#636366] mt-1">
          Hardware status and system configuration
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
          {/* Software Updates Section */}
          <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] overflow-hidden">
            <div className="px-6 py-4 border-b border-[#2a2a2f]">
              <h2 className="text-lg font-semibold">Software Updates</h2>
              <p className="text-sm text-[#636366] mt-1">
                Manage system software updates
              </p>
            </div>
            <div className="p-6">
              <UpdatePanel />
            </div>
          </div>

          {/* Switch Configuration Section */}
          <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] overflow-hidden">
            <div className="px-6 py-4 border-b border-[#2a2a2f]">
              <h2 className="text-lg font-semibold">Switch Configuration</h2>
              <p className="text-sm text-[#636366] mt-1">
                Configure hardware behavior for normally-open and normally-closed switches
              </p>
            </div>
            <div className="p-6">
              <SwitchConfigPanel />
            </div>
          </div>

          {/* Hardware Connection Status Section */}
          <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] overflow-hidden">
            <div className="px-6 py-4 border-b border-[#2a2a2f] flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold">Hardware Connection Status</h2>
                <p className="text-sm text-[#636366] mt-1">
                  Real-time connection status for hardware interfaces
                </p>
              </div>
              <button
                onClick={handleRefreshHardware}
                className="p-2 hover:bg-white/5 rounded-lg transition-colors text-[#a1a1a6] hover:text-white"
                title="Refresh status"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                </svg>
              </button>
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
                        <span className="text-[#636366]">Errors</span>
                        <span className={`font-mono ${status.hardware.labjack.error_count > 100 ? 'text-red-400' : 'text-green-400'}`}>
                          {status.hardware.labjack.error_count.toLocaleString()}
                        </span>
                      </div>
                      {hardware?.labjack_available && hardware.labjack_details && (
                        <div className="flex justify-between text-sm pt-2 border-t border-[#2a2a2f]">
                          <span className="text-[#636366]">Detection</span>
                          <span className="text-xs text-[#8e8e93]">{hardware.labjack_details}</span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <p className="text-sm text-red-400">Not connected</p>
                      {hardware?.labjack_available && (
                        <p className="text-xs text-[#8e8e93] mt-1">
                          Hardware detected: {hardware.labjack_details}
                        </p>
                      )}
                    </div>
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
                        <span className="text-[#636366]">Send Errors</span>
                        <span className={`font-mono ${status.hardware.ola.send_errors > 0 ? 'text-red-400' : 'text-green-400'}`}>
                          {status.hardware.ola.send_errors}
                        </span>
                      </div>
                      {hardware?.ola_available && hardware.ola_details && (
                        <div className="flex justify-between text-sm pt-2 border-t border-[#2a2a2f]">
                          <span className="text-[#636366]">Detection</span>
                          <span className="text-xs text-[#8e8e93]">{hardware.ola_details}</span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="space-y-2">
                      <p className="text-sm text-red-400">Not connected</p>
                      {hardware?.ola_available && (
                        <p className="text-xs text-[#8e8e93] mt-1">
                          Hardware detected: {hardware.ola_details}
                        </p>
                      )}
                    </div>
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
