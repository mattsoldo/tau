'use client';

import { useState, useEffect, useCallback } from 'react';
import { Sun, Moon, Monitor } from 'lucide-react';
import { API_URL } from '@/utils/api';
import { useTheme } from '@/contexts/ThemeContext';
import SoftwareUpdatePanel from '../../../components/SoftwareUpdatePanel';

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

interface SystemSetting {
  id: number;
  key: string;
  value: string;
  description: string | null;
  value_type: string;
}

interface DTWSettings {
  enabled: boolean;
  min_cct: number;
  max_cct: number;
  min_brightness: number;
  curve: string;
  override_timeout: number;
}

interface DTWExampleValue {
  brightness: number;
  cct: number;
}

interface DTWCurveInfo {
  available_curves: string[];
  current_curve: string;
  example_values: DTWExampleValue[];
}

export default function SettingsPage() {
  // Theme
  const { theme, setTheme } = useTheme();

  // State
  const [hardware, setHardware] = useState<HardwareAvailability | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [settings, setSettings] = useState<SystemSetting[]>([]);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // DTW State
  const [dtwSettings, setDtwSettings] = useState<DTWSettings | null>(null);
  const [dtwCurveInfo, setDtwCurveInfo] = useState<DTWCurveInfo | null>(null);
  const [dtwSaving, setDtwSaving] = useState(false);
  const [editingMinCct, setEditingMinCct] = useState<string>('');
  const [editingMaxCct, setEditingMaxCct] = useState<string>('');

  // Fetch data
  const fetchData = useCallback(async () => {
    try {
      // Check if an update is in progress
      const updateInProgress = localStorage.getItem('tau_update_in_progress') === 'true';

      const [hardwareRes, statusRes, settingsRes, dtwRes, dtwCurvesRes] = await Promise.all([
        fetch(`${API_URL}/api/config/hardware-availability`),
        fetch(`${API_URL}/status`),
        fetch(`${API_URL}/api/config/settings`),
        fetch(`${API_URL}/api/dtw/settings`),
        fetch(`${API_URL}/api/dtw/curves`),
      ]);

      // If update is in progress and hardware/status requests fail, show friendlier message
      if (updateInProgress && (!hardwareRes.ok || !statusRes.ok)) {
        setError('Update in progress - services restarting...');
        setIsLoading(false);
        return;
      }

      if (!hardwareRes.ok) throw new Error('Failed to fetch hardware availability');
      if (!statusRes.ok) throw new Error('Failed to fetch system status');
      if (!settingsRes.ok) throw new Error('Failed to fetch system settings');

      const [hardwareData, statusData, settingsData] = await Promise.all([
        hardwareRes.json(),
        statusRes.json(),
        settingsRes.json(),
      ]);

      setHardware(hardwareData);
      setStatus(statusData);
      setSettings(settingsData);

      // DTW settings (optional - don't fail if not available)
      if (dtwRes.ok) {
        const dtwData = await dtwRes.json();
        setDtwSettings(dtwData);
      }
      if (dtwCurvesRes.ok) {
        const dtwCurvesData = await dtwCurvesRes.json();
        setDtwCurveInfo(dtwCurvesData);
      }

      setError(null);
    } catch (err) {
      // Check if update is in progress to provide better error message
      const updateInProgress = localStorage.getItem('tau_update_in_progress') === 'true';
      if (updateInProgress) {
        setError('Update in progress - services restarting...');
      } else {
        setError(err instanceof Error ? err.message : 'Failed to load settings');
      }
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

  // Start editing a setting
  const handleEditSetting = (setting: SystemSetting) => {
    setEditingKey(setting.key);
    setEditValue(setting.value);
  };

  // Save edited setting
  const handleSaveSetting = async (key: string) => {
    try {
      const res = await fetch(`${API_URL}/api/config/settings/${key}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ value: editValue }),
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Failed to update setting');
      }

      // Refresh settings
      await fetchData();
      setEditingKey(null);
      setEditValue('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save setting');
    }
  };

  // Cancel editing
  const handleCancelEdit = () => {
    setEditingKey(null);
    setEditValue('');
  };

  // Update DTW settings
  const handleUpdateDTW = async (updates: Partial<DTWSettings>) => {
    setDtwSaving(true);
    try {
      const res = await fetch(`${API_URL}/api/dtw/settings`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(updates),
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || 'Failed to update DTW settings');
      }

      // Refresh data
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update DTW settings');
    } finally {
      setDtwSaving(false);
    }
  };

  // Format value for display
  const formatValue = (value: string, type: string) => {
    if (type === 'int' || type === 'float') {
      return value;
    } else if (type === 'bool') {
      return value === 'true' || value === '1' ? 'Enabled' : 'Disabled';
    }
    return value;
  };

  // Get input type for editing
  const getInputType = (valueType: string) => {
    if (valueType === 'int' || valueType === 'float') {
      return 'number';
    } else if (valueType === 'bool') {
      return 'checkbox';
    }
    return 'text';
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
          {/* Appearance Section */}
          <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] overflow-hidden">
            <div className="px-6 py-4 border-b border-[#2a2a2f]">
              <h2 className="text-lg font-semibold">Appearance</h2>
              <p className="text-sm text-[#636366] mt-1">
                Choose your preferred color theme
              </p>
            </div>
            <div className="p-6">
              <div className="grid grid-cols-3 gap-3">
                <button
                  onClick={() => setTheme('light')}
                  className={`flex flex-col items-center gap-3 p-4 rounded-lg border-2 transition-all ${
                    theme === 'light'
                      ? 'border-amber-500 bg-amber-500/10'
                      : 'border-[#3a3a3f] hover:border-[#4a4a4f] bg-[#0f0f14]'
                  }`}
                >
                  <div className={`p-3 rounded-full ${theme === 'light' ? 'bg-amber-500/20' : 'bg-[#2a2a2f]'}`}>
                    <Sun className={`w-6 h-6 ${theme === 'light' ? 'text-amber-400' : 'text-[#8e8e93]'}`} />
                  </div>
                  <span className={`text-sm font-medium ${theme === 'light' ? 'text-amber-400' : 'text-[#a1a1a6]'}`}>
                    Light
                  </span>
                </button>

                <button
                  onClick={() => setTheme('dark')}
                  className={`flex flex-col items-center gap-3 p-4 rounded-lg border-2 transition-all ${
                    theme === 'dark'
                      ? 'border-amber-500 bg-amber-500/10'
                      : 'border-[#3a3a3f] hover:border-[#4a4a4f] bg-[#0f0f14]'
                  }`}
                >
                  <div className={`p-3 rounded-full ${theme === 'dark' ? 'bg-amber-500/20' : 'bg-[#2a2a2f]'}`}>
                    <Moon className={`w-6 h-6 ${theme === 'dark' ? 'text-amber-400' : 'text-[#8e8e93]'}`} />
                  </div>
                  <span className={`text-sm font-medium ${theme === 'dark' ? 'text-amber-400' : 'text-[#a1a1a6]'}`}>
                    Dark
                  </span>
                </button>

                <button
                  onClick={() => setTheme('system')}
                  className={`flex flex-col items-center gap-3 p-4 rounded-lg border-2 transition-all ${
                    theme === 'system'
                      ? 'border-amber-500 bg-amber-500/10'
                      : 'border-[#3a3a3f] hover:border-[#4a4a4f] bg-[#0f0f14]'
                  }`}
                >
                  <div className={`p-3 rounded-full ${theme === 'system' ? 'bg-amber-500/20' : 'bg-[#2a2a2f]'}`}>
                    <Monitor className={`w-6 h-6 ${theme === 'system' ? 'text-amber-400' : 'text-[#8e8e93]'}`} />
                  </div>
                  <span className={`text-sm font-medium ${theme === 'system' ? 'text-amber-400' : 'text-[#a1a1a6]'}`}>
                    System
                  </span>
                </button>
              </div>
            </div>
          </div>

          {/* Software Updates Section */}
          <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] overflow-hidden">
            <div className="px-6 py-4 border-b border-[#2a2a2f]">
              <h2 className="text-lg font-semibold">Software Updates</h2>
              <p className="text-sm text-[#636366] mt-1">
                Manage system software updates via GitHub Releases
              </p>
            </div>
            <div className="p-6">
              <SoftwareUpdatePanel />
            </div>
          </div>

          {/* Dim-to-Warm Settings Section */}
          {dtwSettings && (
            <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] overflow-hidden">
              <div className="px-6 py-4 border-b border-[#2a2a2f]">
                <h2 className="text-lg font-semibold">Dim-to-Warm</h2>
                <p className="text-sm text-[#636366] mt-1">
                  Automatic color temperature adjustment based on brightness for natural dimming
                </p>
              </div>
              <div className="p-6 space-y-6">
                {/* Enable/Disable Toggle */}
                <div className="flex items-center justify-between p-4 bg-[#0f0f14] rounded-lg border border-[#2a2a2f]">
                  <div>
                    <h3 className="font-medium text-white">Enable Dim-to-Warm</h3>
                    <p className="text-sm text-[#636366] mt-1">
                      Automatically adjust CCT based on brightness level
                    </p>
                  </div>
                  <button
                    onClick={() => handleUpdateDTW({ enabled: !dtwSettings.enabled })}
                    disabled={dtwSaving}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                      dtwSettings.enabled ? 'bg-amber-500' : 'bg-[#3a3a3f]'
                    } ${dtwSaving ? 'opacity-50' : ''}`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        dtwSettings.enabled ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>

                {dtwSettings.enabled && (
                  <>
                    {/* Curve Type Selector */}
                    <div className="p-4 bg-[#0f0f14] rounded-lg border border-[#2a2a2f]">
                      <div className="flex items-center justify-between mb-4">
                        <div>
                          <h3 className="font-medium text-white">Curve Type</h3>
                          <p className="text-sm text-[#636366] mt-1">
                            How CCT changes as brightness decreases
                          </p>
                        </div>
                        <select
                          value={dtwSettings.curve}
                          onChange={(e) => handleUpdateDTW({ curve: e.target.value })}
                          disabled={dtwSaving}
                          className="px-4 py-2 bg-[#1a1a1f] border border-[#3a3a3f] rounded-lg text-white focus:outline-none focus:border-amber-500"
                        >
                          {dtwCurveInfo?.available_curves.map((curve) => (
                            <option key={curve} value={curve}>
                              {curve.charAt(0).toUpperCase() + curve.slice(1)}
                            </option>
                          ))}
                        </select>
                      </div>

                      {/* Curve Description */}
                      <div className="text-sm text-[#8e8e93] mb-4">
                        {dtwSettings.curve === 'linear' && 'Even CCT change per brightness step. Simple and predictable.'}
                        {dtwSettings.curve === 'log' && 'Logarithmic curve. More CCT change at low brightness (recommended).'}
                        {dtwSettings.curve === 'square' && 'Quadratic curve. Gentle warm-up, aggressive at low end.'}
                        {dtwSettings.curve === 'incandescent' && 'Models actual filament behavior. Most natural appearance.'}
                      </div>

                      {/* Example Values */}
                      {dtwCurveInfo?.example_values && (
                        <div className="grid grid-cols-7 gap-2 text-center">
                          {dtwCurveInfo.example_values.map((ex) => (
                            <div key={ex.brightness} className="p-2 bg-[#1a1a1f] rounded">
                              <div className="text-xs text-[#636366] mb-1">{Math.round(ex.brightness * 100)}%</div>
                              <div className="text-sm font-mono text-amber-400">{ex.cct}K</div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* CCT Range */}
                    <div className="grid grid-cols-2 gap-4">
                      <div className="p-4 bg-[#0f0f14] rounded-lg border border-[#2a2a2f]">
                        <h3 className="font-medium text-white mb-2">Warm CCT (at lowest brightness)</h3>
                        <div className="flex items-center gap-2">
                          <input
                            type="number"
                            value={editingMinCct || dtwSettings.min_cct}
                            onChange={(e) => setEditingMinCct(e.target.value)}
                            onFocus={() => setEditingMinCct(String(dtwSettings.min_cct))}
                            onBlur={(e) => {
                              const val = parseInt(e.target.value);
                              if (val >= 1000 && val <= 10000 && val !== dtwSettings.min_cct) {
                                handleUpdateDTW({ min_cct: val });
                              }
                              setEditingMinCct('');
                            }}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                (e.target as HTMLInputElement).blur();
                              }
                            }}
                            min={1000}
                            max={10000}
                            step={100}
                            disabled={dtwSaving}
                            className="flex-1 px-3 py-2 bg-[#1a1a1f] border border-[#3a3a3f] rounded-lg text-white font-mono focus:outline-none focus:border-amber-500 disabled:opacity-50"
                          />
                          <span className="text-[#636366]">K</span>
                        </div>
                      </div>
                      <div className="p-4 bg-[#0f0f14] rounded-lg border border-[#2a2a2f]">
                        <h3 className="font-medium text-white mb-2">Cool CCT (at full brightness)</h3>
                        <div className="flex items-center gap-2">
                          <input
                            type="number"
                            value={editingMaxCct || dtwSettings.max_cct}
                            onChange={(e) => setEditingMaxCct(e.target.value)}
                            onFocus={() => setEditingMaxCct(String(dtwSettings.max_cct))}
                            onBlur={(e) => {
                              const val = parseInt(e.target.value);
                              if (val >= 1000 && val <= 10000 && val !== dtwSettings.max_cct) {
                                handleUpdateDTW({ max_cct: val });
                              }
                              setEditingMaxCct('');
                            }}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                (e.target as HTMLInputElement).blur();
                              }
                            }}
                            min={1000}
                            max={10000}
                            step={100}
                            disabled={dtwSaving}
                            className="flex-1 px-3 py-2 bg-[#1a1a1f] border border-[#3a3a3f] rounded-lg text-white font-mono focus:outline-none focus:border-amber-500 disabled:opacity-50"
                          />
                          <span className="text-[#636366]">K</span>
                        </div>
                      </div>
                    </div>

                    {/* Override Timeout */}
                    <div className="p-4 bg-[#0f0f14] rounded-lg border border-[#2a2a2f]">
                      <h3 className="font-medium text-white mb-2">Override Timeout</h3>
                      <p className="text-sm text-[#636366] mb-3">
                        How long manual CCT adjustments persist before returning to automatic DTW
                      </p>
                      <div className="flex items-center gap-2">
                        <input
                          type="number"
                          value={Math.round(dtwSettings.override_timeout / 3600)}
                          onChange={(e) => {
                            const hours = parseInt(e.target.value) || 0;
                            handleUpdateDTW({ override_timeout: hours * 3600 });
                          }}
                          min={1}
                          max={24}
                          className="w-24 px-3 py-2 bg-[#1a1a1f] border border-[#3a3a3f] rounded-lg text-white font-mono focus:outline-none focus:border-amber-500"
                        />
                        <span className="text-[#636366]">hours</span>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}

          {/* Global Settings Section */}
          <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] overflow-hidden">
            <div className="px-6 py-4 border-b border-[#2a2a2f]">
              <h2 className="text-lg font-semibold">Global Settings</h2>
              <p className="text-sm text-[#636366] mt-1">
                System-wide configuration values
              </p>
            </div>
            <div className="p-6">
              {settings.length === 0 ? (
                <p className="text-[#636366] text-sm">No settings configured</p>
              ) : (
                <div className="space-y-3">
                  {settings.map((setting) => (
                    <div
                      key={setting.key}
                      className="flex items-center justify-between p-4 bg-[#0f0f14] rounded-lg border border-[#2a2a2f] hover:border-[#3a3a3f] transition-colors"
                    >
                      <div className="flex-1">
                        <div className="flex items-center gap-3">
                          <h3 className="font-medium text-white">{setting.key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</h3>
                          <span className="text-xs px-2 py-0.5 bg-amber-500/10 text-amber-400 rounded border border-amber-500/30 font-mono">
                            {setting.value_type}
                          </span>
                        </div>
                        {setting.description && (
                          <p className="text-sm text-[#636366] mt-1">{setting.description}</p>
                        )}
                      </div>

                      <div className="flex items-center gap-3 ml-6">
                        {editingKey === setting.key ? (
                          <>
                            {setting.value_type === 'bool' ? (
                              <label className="flex items-center gap-2 text-sm text-[#a1a1a6]">
                                <input
                                  type="checkbox"
                                  checked={editValue === 'true' || editValue === '1'}
                                  onChange={(e) => setEditValue(e.target.checked ? 'true' : 'false')}
                                  className="h-4 w-4 rounded border border-[#3a3a3f] bg-[#1a1a1f] text-amber-500 focus:ring-amber-500/30"
                                />
                                <span>{editValue === 'true' || editValue === '1' ? 'Enabled' : 'Disabled'}</span>
                              </label>
                            ) : (
                              <input
                                type={getInputType(setting.value_type)}
                                value={editValue}
                                onChange={(e) => setEditValue(e.target.value)}
                                step={
                                  setting.value_type === 'float'
                                    ? '0.1'
                                    : setting.value_type === 'int'
                                      ? '1'
                                      : undefined
                                }
                                className="px-3 py-2 bg-[#1a1a1f] border border-[#3a3a3f] rounded-lg text-white focus:outline-none focus:border-amber-500 font-mono text-sm w-32"
                                autoFocus
                              />
                            )}
                            <button
                              onClick={() => handleSaveSetting(setting.key)}
                              className="p-2 bg-green-500/10 hover:bg-green-500/20 text-green-400 rounded-lg transition-colors"
                              title="Save"
                            >
                              <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                              </svg>
                            </button>
                            <button
                              onClick={handleCancelEdit}
                              className="p-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 rounded-lg transition-colors"
                              title="Cancel"
                            >
                              <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                              </svg>
                            </button>
                          </>
                        ) : (
                          <>
                            <span className="font-mono text-amber-400 text-sm min-w-[100px] text-right">
                              {formatValue(setting.value, setting.value_type)}
                              {setting.value_type === 'int' && setting.key.includes('ms') && ' ms'}
                            </span>
                            <button
                              onClick={() => handleEditSetting(setting)}
                              className="p-2 hover:bg-white/5 rounded-lg transition-colors text-[#a1a1a6] hover:text-white"
                              title="Edit"
                            >
                              <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
                              </svg>
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
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
