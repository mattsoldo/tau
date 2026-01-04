'use client';

import { useState, useEffect, useCallback } from 'react';
import { useToast } from '@/contexts/ToastContext';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface SystemConfig {
  labjack_mock: boolean;
  ola_mock: boolean;
  labjack_hardware_available: boolean;
  ola_hardware_available: boolean;
  config_file_path: string | null;
}

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
  const { showToast } = useToast();

  // State
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [hardware, setHardware] = useState<HardwareAvailability | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [pendingChanges, setPendingChanges] = useState<{
    labjack_mock?: boolean;
    ola_mock?: boolean;
  }>({});

  // Fetch data
  const fetchData = useCallback(async () => {
    try {
      const [configRes, hardwareRes, statusRes] = await Promise.all([
        fetch(`${API_URL}/api/config/`),
        fetch(`${API_URL}/api/config/hardware-availability`),
        fetch(`${API_URL}/status`),
      ]);

      if (!configRes.ok) throw new Error('Failed to fetch configuration');
      if (!hardwareRes.ok) throw new Error('Failed to fetch hardware availability');
      if (!statusRes.ok) throw new Error('Failed to fetch system status');

      const [configData, hardwareData, statusData] = await Promise.all([
        configRes.json(),
        hardwareRes.json(),
        statusRes.json(),
      ]);

      setConfig(configData);
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

  // Handle toggle changes
  const handleToggle = (field: 'labjack_mock' | 'ola_mock') => {
    if (!config) return;

    const currentValue = pendingChanges[field] ?? config[field];
    setPendingChanges({
      ...pendingChanges,
      [field]: !currentValue,
    });
  };

  // Check if there are unsaved changes
  const hasChanges = config && (
    (pendingChanges.labjack_mock !== undefined && pendingChanges.labjack_mock !== config.labjack_mock) ||
    (pendingChanges.ola_mock !== undefined && pendingChanges.ola_mock !== config.ola_mock)
  );

  // Get display value for a field
  const getDisplayValue = (field: 'labjack_mock' | 'ola_mock'): boolean => {
    if (!config) return true;
    return pendingChanges[field] ?? config[field];
  };

  // Save changes
  const handleSave = async () => {
    if (!hasChanges) return;

    setIsSaving(true);
    try {
      const res = await fetch(`${API_URL}/api/config/`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(pendingChanges),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to save settings');
      }

      const result = await res.json();

      showToast({
        type: 'success',
        message: 'Settings saved. Restart the daemon for changes to take effect.',
        duration: 8000,
      });

      setPendingChanges({});
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save settings');
    } finally {
      setIsSaving(false);
    }
  };

  // Discard changes
  const handleDiscard = () => {
    setPendingChanges({});
  };

  // Refresh hardware detection
  const handleRefreshHardware = async () => {
    try {
      const res = await fetch(`${API_URL}/api/config/hardware-availability`);
      if (!res.ok) throw new Error('Failed to refresh hardware');

      const data = await res.json();
      setHardware(data);

      showToast({
        type: 'info',
        message: 'Hardware detection refreshed',
        duration: 3000,
      });
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
          Configure hardware mode and system preferences
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
      {isLoading && !config ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin"></div>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Hardware Mode Section */}
          <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] overflow-hidden">
            <div className="px-6 py-4 border-b border-[#2a2a2f]">
              <h2 className="text-lg font-semibold">Hardware Mode</h2>
              <p className="text-sm text-[#636366] mt-1">
                Toggle between mock (simulated) and live (real hardware) modes
              </p>
            </div>

            <div className="p-6 space-y-6">
              {/* LabJack Toggle */}
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                      getDisplayValue('labjack_mock')
                        ? 'bg-blue-500/15 text-blue-400'
                        : 'bg-green-500/15 text-green-400'
                    }`}>
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 3v1.5M4.5 8.25H3m18 0h-1.5M4.5 12H3m18 0h-1.5m-15 3.75H3m18 0h-1.5M8.25 19.5V21M12 3v1.5m0 15V21m3.75-18v1.5m0 15V21m-9-1.5h10.5a2.25 2.25 0 002.25-2.25V6.75a2.25 2.25 0 00-2.25-2.25H6.75A2.25 2.25 0 004.5 6.75v10.5a2.25 2.25 0 002.25 2.25zm.75-12h9v9h-9v-9z" />
                      </svg>
                    </div>
                    <div>
                      <h3 className="font-medium">LabJack Interface</h3>
                      <p className="text-sm text-[#636366]">
                        {getDisplayValue('labjack_mock') ? 'Mock Mode' : 'Live Mode'} -
                        {getDisplayValue('labjack_mock')
                          ? ' Using simulated switch inputs'
                          : ' Connected to physical LabJack U3'
                        }
                      </p>
                    </div>
                  </div>
                  {hardware?.labjack_available && getDisplayValue('labjack_mock') && (
                    <div className="mt-3 ml-13 px-3 py-2 bg-amber-500/10 border border-amber-500/30 rounded-lg text-amber-400 text-sm flex items-center gap-2">
                      <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                      </svg>
                      <span>Hardware detected: {hardware.labjack_details}</span>
                    </div>
                  )}
                </div>
                <button
                  onClick={() => handleToggle('labjack_mock')}
                  className={`relative w-14 h-7 rounded-full transition-colors ${
                    getDisplayValue('labjack_mock')
                      ? 'bg-blue-500'
                      : 'bg-green-500'
                  }`}
                >
                  <span
                    className={`absolute top-1 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                      getDisplayValue('labjack_mock') ? 'left-1' : 'left-8'
                    }`}
                  />
                  <span className="sr-only">
                    {getDisplayValue('labjack_mock') ? 'Switch to Live' : 'Switch to Mock'}
                  </span>
                </button>
              </div>

              <div className="border-t border-[#2a2a2f]"></div>

              {/* OLA/DMX Toggle */}
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                      getDisplayValue('ola_mock')
                        ? 'bg-blue-500/15 text-blue-400'
                        : 'bg-green-500/15 text-green-400'
                    }`}>
                      <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
                      </svg>
                    </div>
                    <div>
                      <h3 className="font-medium">DMX / OLA Interface</h3>
                      <p className="text-sm text-[#636366]">
                        {getDisplayValue('ola_mock') ? 'Mock Mode' : 'Live Mode'} -
                        {getDisplayValue('ola_mock')
                          ? ' Using simulated DMX output'
                          : ' Connected to OLA daemon'
                        }
                      </p>
                    </div>
                  </div>
                  {hardware?.ola_available && getDisplayValue('ola_mock') && (
                    <div className="mt-3 ml-13 px-3 py-2 bg-amber-500/10 border border-amber-500/30 rounded-lg text-amber-400 text-sm flex items-center gap-2">
                      <svg className="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                      </svg>
                      <span>Hardware detected: {hardware.ola_details}</span>
                    </div>
                  )}
                </div>
                <button
                  onClick={() => handleToggle('ola_mock')}
                  className={`relative w-14 h-7 rounded-full transition-colors ${
                    getDisplayValue('ola_mock')
                      ? 'bg-blue-500'
                      : 'bg-green-500'
                  }`}
                >
                  <span
                    className={`absolute top-1 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                      getDisplayValue('ola_mock') ? 'left-1' : 'left-8'
                    }`}
                  />
                  <span className="sr-only">
                    {getDisplayValue('ola_mock') ? 'Switch to Live' : 'Switch to Mock'}
                  </span>
                </button>
              </div>
            </div>

            {/* Unsaved Changes Bar */}
            {hasChanges && (
              <div className="px-6 py-4 border-t border-amber-500/30 bg-amber-500/5 flex items-center justify-between">
                <div className="flex items-center gap-2 text-amber-400 text-sm">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                  </svg>
                  <span>You have unsaved changes. A daemon restart will be required.</span>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleDiscard}
                    className="px-4 py-2 bg-[#2a2a2f] hover:bg-[#3a3a3f] text-white text-sm rounded-lg transition-colors"
                  >
                    Discard
                  </button>
                  <button
                    onClick={handleSave}
                    disabled={isSaving}
                    className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-black text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
                  >
                    {isSaving ? 'Saving...' : 'Save Changes'}
                  </button>
                </div>
              </div>
            )}
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

          {/* Configuration File Info */}
          {config?.config_file_path && (
            <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] p-6">
              <h2 className="text-lg font-semibold mb-2">Configuration File</h2>
              <p className="text-sm text-[#636366]">
                Settings are stored in:
              </p>
              <code className="block mt-2 px-3 py-2 bg-[#0a0a0b] border border-[#2a2a2f] rounded text-sm text-amber-400 font-mono">
                {config.config_file_path}
              </code>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
