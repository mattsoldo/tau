'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import {
  api,
  API_URL,
  SoftwareUpdateStatusResponse,
  SoftwareUpdateCheckResponse,
  SoftwareVersionHistoryEntry,
  SoftwareBackupInfo,
  SoftwareUpdateConfig,
  SoftwareReleaseInfo,
} from '../utils/api';

// Simple markdown-like rendering for release notes
function ReleaseNotes({ content }: { content: string }) {
  if (!content) return null;

  const lines = content.split('\n');
  const elements: JSX.Element[] = [];

  lines.forEach((line, idx) => {
    const trimmed = line.trim();

    // Headers
    if (trimmed.startsWith('## ')) {
      elements.push(
        <h3 key={idx} className="text-sm font-semibold text-[#e5e5e7] mt-3 mb-1">
          {trimmed.slice(3)}
        </h3>
      );
    } else if (trimmed.startsWith('# ')) {
      elements.push(
        <h2 key={idx} className="text-base font-bold text-[#e5e5e7] mt-4 mb-2">
          {trimmed.slice(2)}
        </h2>
      );
    }
    // List items
    else if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      elements.push(
        <li key={idx} className="text-sm text-[#b4b4b8] ml-4">
          {trimmed.slice(2)}
        </li>
      );
    }
    // Regular text
    else if (trimmed) {
      elements.push(
        <p key={idx} className="text-sm text-[#b4b4b8]">
          {trimmed}
        </p>
      );
    }
  });

  return <div className="space-y-1">{elements}</div>;
}

// Format date for display
function formatDate(dateString: string | null): string {
  if (!dateString) return 'N/A';
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// Format file size
function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function SoftwareUpdatePanel() {
  // State
  const [status, setStatus] = useState<SoftwareUpdateStatusResponse | null>(null);
  const [history, setHistory] = useState<SoftwareVersionHistoryEntry[]>([]);
  const [backups, setBackups] = useState<SoftwareBackupInfo[]>([]);
  const [config, setConfig] = useState<SoftwareUpdateConfig | null>(null);
  const [releases, setReleases] = useState<SoftwareReleaseInfo[]>([]);

  const [isChecking, setIsChecking] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [isRollingBack, setIsRollingBack] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const [activeTab, setActiveTab] = useState<'status' | 'history' | 'settings'>('status');
  const [updateCheckResult, setUpdateCheckResult] = useState<SoftwareUpdateCheckResponse | null>(null);

  const [reconnectCountdown, setReconnectCountdown] = useState(0);
  const reconnectPollingActive = useRef(false);
  const healthSawFailure = useRef(false);
  const fetchStatusRef = useRef<null | (() => Promise<void>)>(null);

  const clearUpdateFlags = useCallback(() => {
    localStorage.removeItem('tau_update_in_progress');
    localStorage.removeItem('tau_update_target_version');
  }, []);

  // Fetch initial data and check for updates on mount
  useEffect(() => {
    fetchStatus();
    fetchHistory();
    fetchBackups();
    fetchConfig();

    // Auto-check for updates after a short delay to not block initial render
    const checkTimer = setTimeout(() => {
      checkForUpdates();
    }, 1000);

    return () => clearTimeout(checkTimer);
  }, []);

  const fetchStatus = useCallback(async () => {
    try {
      const data = await api.softwareUpdate.getStatus();
      setStatus(data);

      const inactiveStates = ['idle', 'complete', 'failed'];
      setIsUpdating(!inactiveStates.includes(data.state));

      if (data.state === 'failed') {
        setError((data.progress as any)?.message || 'Update failed');
        clearUpdateFlags();
        return;
      }

      const targetVersion = localStorage.getItem('tau_update_target_version');
      if (
        targetVersion &&
        (data.state === 'complete' || data.state === 'idle') &&
        data.current_version === targetVersion
      ) {
        clearUpdateFlags();
        setSuccessMessage(`Updated to v${data.current_version}`);
        setTimeout(() => setSuccessMessage(null), 4000);
      }

      setError(null);
    } catch (err: any) {
      console.error('Failed to fetch status:', err);
      if (localStorage.getItem('tau_update_in_progress') === 'true') {
        startReconnectPolling();
      }
    }
  }, [clearUpdateFlags, startReconnectPolling]);

  useEffect(() => {
    fetchStatusRef.current = fetchStatus;
  }, [fetchStatus]);

  const fetchHistory = useCallback(async () => {
    try {
      const data = await api.softwareUpdate.getHistory(10);
      setHistory(data);
    } catch (err: any) {
      console.error('Failed to fetch history:', err);
    }
  }, []);

  const fetchBackups = useCallback(async () => {
    try {
      const data = await api.softwareUpdate.getBackups();
      setBackups(data);
    } catch (err: any) {
      console.error('Failed to fetch backups:', err);
    }
  }, []);

  const fetchConfig = useCallback(async () => {
    try {
      const data = await api.softwareUpdate.getConfig();
      setConfig(data);
    } catch (err: any) {
      console.error('Failed to fetch config:', err);
    }
  }, []);

  const checkForUpdates = useCallback(async () => {
    if (localStorage.getItem('tau_update_in_progress') === 'true') {
      return;
    }
    setIsChecking(true);
    setError(null);
    setUpdateCheckResult(null);

    try {
      const result = await api.softwareUpdate.check();
      setUpdateCheckResult(result);
      await fetchStatus();

      if (!result.update_available) {
        setSuccessMessage('System is up to date!');
        setTimeout(() => setSuccessMessage(null), 3000);
      }
    } catch (err: any) {
      const status = (err as any)?.status;
      const updateInProgress = localStorage.getItem('tau_update_in_progress') === 'true';
      if (updateInProgress && (status === 502 || status === 503 || status === 504)) {
        setError(null);
      } else {
        setError(err.message || 'Failed to check for updates');
      }
    } finally {
      setIsChecking(false);
    }
  }, [fetchStatus]);

  const applyUpdate = useCallback(async (version: string) => {
    if (!confirm(`This will update the system to version ${version}. The system will restart. Continue?`)) {
      return;
    }

    setIsUpdating(true);
    setError(null);

    // Mark update as in progress for other components
    localStorage.setItem('tau_update_in_progress', 'true');
    localStorage.setItem('tau_update_target_version', version);

    try {
      await api.softwareUpdate.apply(version);
      // Start status polling to show progress until restart
      await fetchStatus();
    } catch (err: any) {
      setError(err.message || 'Failed to apply update');
      setIsUpdating(false);
      // Clear flag on error
      clearUpdateFlags();
    }
  }, [clearUpdateFlags]);

  const rollback = useCallback(async (version?: string) => {
    const msg = version
      ? `This will rollback to version ${version}. Continue?`
      : 'This will rollback to the most recent backup. Continue?';

    if (!confirm(msg)) {
      return;
    }

    setIsRollingBack(true);
    setError(null);

    try {
      const result = await api.softwareUpdate.rollback(version);
      setSuccessMessage(result.message);
      await fetchStatus();
      await fetchHistory();
    } catch (err: any) {
      setError(err.message || 'Failed to rollback');
    } finally {
      setIsRollingBack(false);
    }
  }, [fetchStatus, fetchHistory]);

  const updateConfigValue = useCallback(async (key: string, value: string) => {
    try {
      const updated = await api.softwareUpdate.updateConfig(key, value);
      setConfig(updated);
      setSuccessMessage('Configuration updated');
      setTimeout(() => setSuccessMessage(null), 2000);
    } catch (err: any) {
      setError(err.message || 'Failed to update configuration');
    }
  }, []);

  const startReconnectPolling = useCallback(() => {
    if (reconnectPollingActive.current) return;
    reconnectPollingActive.current = true;
    healthSawFailure.current = false;
    setReconnectCountdown(60);

    const interval = setInterval(async () => {
      try {
        const response = await fetch(`${API_URL}/health`);
        if (!response.ok) {
          healthSawFailure.current = true;
          return;
        }
        if (healthSawFailure.current) {
          clearInterval(interval);
          clearUpdateFlags();
          window.location.reload();
          return;
        }
        if (fetchStatusRef.current) {
          await fetchStatusRef.current();
        }
      } catch {
        healthSawFailure.current = true;
      }
    }, 2000);

    const countdownInterval = setInterval(() => {
      setReconnectCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(countdownInterval);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      clearInterval(interval);
      clearInterval(countdownInterval);
      reconnectPollingActive.current = false;
    };
  }, [clearUpdateFlags, fetchStatus]);

  useEffect(() => {
    if (!isUpdating) return;
    const interval = setInterval(() => {
      fetchStatus();
    }, 2000);
    return () => clearInterval(interval);
  }, [fetchStatus, isUpdating]);

  useEffect(() => {
    if (!status) return;
    if (status.state === 'starting_services' || status.state === 'complete') {
      startReconnectPolling();
    }
  }, [startReconnectPolling, status]);

  // Render update available banner
  const renderUpdateBanner = () => {
    if (!updateCheckResult?.update_available && !status?.update_available) {
      return null;
    }

    const version = updateCheckResult?.latest_version || status?.available_version;
    const notes = updateCheckResult?.release_notes || status?.release_notes;
    const publishedAt = updateCheckResult?.published_at;

    return (
      <div className="bg-amber-900/20 border border-amber-800 rounded-lg p-4 space-y-4">
        <div className="flex items-start">
          <svg className="w-5 h-5 text-amber-500 mr-2 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <div className="flex-1">
            <div className="font-semibold text-amber-400">Update Available: v{version}</div>
            {publishedAt && (
              <div className="text-sm text-amber-300 mt-1">
                Published: {formatDate(publishedAt)}
              </div>
            )}
          </div>
        </div>

        {notes && (
          <div>
            <div className="text-sm font-semibold text-[#e5e5e7] mb-2">Release Notes:</div>
            <div className="bg-[#0a0a0b] rounded border border-[#2a2a2f] p-3 max-h-64 overflow-y-auto">
              <ReleaseNotes content={notes} />
            </div>
          </div>
        )}

        <button
          onClick={() => applyUpdate(version!)}
          disabled={isUpdating}
          className={`
            w-full py-2 px-4 rounded-lg font-semibold transition-colors
            ${isUpdating
              ? 'bg-[#2a2a2f] text-[#636366] cursor-not-allowed'
              : 'bg-amber-500 text-black hover:bg-amber-600'
            }
          `}
        >
          {isUpdating ? 'Updating...' : 'Install Update'}
        </button>
      </div>
    );
  };

  // Render updating state
  const renderUpdatingState = () => {
    if (!isUpdating) return null;

    const progress = status?.progress || {};
    const stage = (progress.stage as string) || 'preparing';
    const percent = (progress.percent as number) || 0;

    const stages = [
      { key: 'downloading', label: 'Downloading package' },
      { key: 'verifying', label: 'Verifying checksum' },
      { key: 'backing_up', label: 'Creating backup' },
      { key: 'stopping_services', label: 'Stopping services' },
      { key: 'installing', label: 'Installing update' },
      { key: 'migrating', label: 'Running migrations' },
      { key: 'starting_services', label: 'Starting services' },
      { key: 'verifying_install', label: 'Verifying installation' },
    ];

    const currentIndex = stages.findIndex(s => s.key === stage);

    return (
      <div className="bg-blue-900/20 border border-blue-800 rounded-lg p-4 space-y-4">
        <div className="flex items-start">
          <div className="animate-spin mr-3 flex-shrink-0">
            <svg className="w-5 h-5 text-blue-500" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
            </svg>
          </div>
          <div className="flex-1">
            <div className="font-semibold text-blue-400">Updating System...</div>
            <div className="text-sm text-blue-300 mt-1">
              Please do not close this page or turn off the device.
            </div>
            {reconnectCountdown > 0 && (
              <div className="text-sm text-blue-300 mt-2">
                Waiting for system to restart... ({reconnectCountdown}s)
              </div>
            )}
          </div>
        </div>

        {/* Progress stages */}
        <div className="bg-[#0a0a0b] rounded border border-[#2a2a2f] p-3 space-y-2 text-sm">
          {stages.map((s, idx) => {
            let icon = '   ';
            let textClass = 'text-[#636366]';

            if (idx < currentIndex) {
              icon = '';
              textClass = 'text-green-400';
            } else if (idx === currentIndex) {
              icon = '';
              textClass = 'text-blue-400';
            } else {
              icon = '';
            }

            return (
              <div key={s.key} className={`flex items-center ${textClass}`}>
                <span className="w-5 mr-2">{icon}</span>
                <span>{s.label}</span>
                {idx === currentIndex && percent > 0 && (
                  <span className="ml-2 text-[#636366]">({percent}%)</span>
                )}
              </div>
            );
          })}
        </div>

        <div className="text-xs text-[#636366]">
          The page will automatically refresh when the update is complete.
        </div>
      </div>
    );
  };

  // Render version history tab
  const renderHistoryTab = () => (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-[#e5e5e7]">Version History</h3>

      {history.length === 0 ? (
        <div className="text-sm text-[#636366]">No version history available.</div>
      ) : (
        <div className="space-y-2">
          {history.map((entry) => (
            <div
              key={`${entry.version}-${entry.installed_at}`}
              className={`
                p-3 rounded-lg border
                ${entry.is_current
                  ? 'bg-green-900/20 border-green-800'
                  : 'bg-[#1a1a1f] border-[#2a2a2f]'
                }
              `}
            >
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-mono font-semibold">v{entry.version}</span>
                  {entry.is_current && (
                    <span className="ml-2 text-xs text-green-400 bg-green-900/30 px-2 py-0.5 rounded">
                      Current
                    </span>
                  )}
                </div>
                {entry.can_rollback && !entry.is_current && (
                  <button
                    onClick={() => rollback(entry.version)}
                    disabled={isRollingBack}
                    className="text-sm px-3 py-1 rounded bg-[#2a2a2f] text-[#b4b4b8] hover:bg-[#3a3a3f] transition-colors disabled:opacity-50"
                  >
                    {isRollingBack ? 'Rolling back...' : 'Rollback'}
                  </button>
                )}
              </div>
              <div className="text-sm text-[#636366] mt-1">
                Installed: {formatDate(entry.installed_at)}
                {entry.uninstalled_at && (
                  <span className="ml-2">| Uninstalled: {formatDate(entry.uninstalled_at)}</span>
                )}
              </div>
              {entry.backup_path && (
                <div className="text-xs text-[#636366] mt-1">
                  Backup: {entry.backup_valid ? 'Available' : 'Expired'}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Backups section */}
      <h3 className="text-sm font-semibold text-[#e5e5e7] mt-6">Available Backups</h3>

      {backups.length === 0 ? (
        <div className="text-sm text-[#636366]">No backups available.</div>
      ) : (
        <div className="space-y-2">
          {backups.map((backup) => (
            <div
              key={backup.backup_path}
              className="p-3 rounded-lg border bg-[#1a1a1f] border-[#2a2a2f]"
            >
              <div className="flex items-center justify-between">
                <div>
                  <span className="font-mono font-semibold">v{backup.version}</span>
                  <span className="ml-2 text-sm text-[#636366]">
                    {formatSize(backup.size_bytes)}
                  </span>
                </div>
                <span className={`text-xs px-2 py-0.5 rounded ${
                  backup.valid ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'
                }`}>
                  {backup.valid ? 'Valid' : 'Invalid'}
                </span>
              </div>
              <div className="text-sm text-[#636366] mt-1">
                Created: {formatDate(backup.created_at)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  // Render settings tab
  const renderSettingsTab = () => {
    if (!config) return <div className="text-sm text-[#636366]">Loading configuration...</div>;

    const settings = [
      {
        key: 'github_repo',
        label: 'GitHub Repository',
        description: 'Repository in owner/repo format',
        type: 'text',
      },
      {
        key: 'auto_check_enabled',
        label: 'Automatic Update Checks',
        description: 'Periodically check for new versions',
        type: 'boolean',
      },
      {
        key: 'check_interval_hours',
        label: 'Check Interval (hours)',
        description: 'How often to check for updates',
        type: 'number',
      },
      {
        key: 'include_prereleases',
        label: 'Include Pre-releases',
        description: 'Show beta and RC versions',
        type: 'boolean',
      },
      {
        key: 'max_backups',
        label: 'Maximum Backups',
        description: 'Number of version backups to keep',
        type: 'number',
      },
      {
        key: 'verify_after_install',
        label: 'Verify After Install',
        description: 'Check services are running after update',
        type: 'boolean',
      },
      {
        key: 'rollback_on_service_failure',
        label: 'Auto-rollback on Failure',
        description: 'Automatically rollback if services fail to start',
        type: 'boolean',
      },
    ];

    return (
      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-[#e5e5e7]">Update Settings</h3>

        <div className="space-y-4">
          {settings.map((setting) => {
            const value = config[setting.key as keyof SoftwareUpdateConfig];

            return (
              <div key={setting.key} className="flex items-start justify-between py-2 border-b border-[#2a2a2f]">
                <div className="flex-1">
                  <div className="text-sm font-medium text-[#e5e5e7]">{setting.label}</div>
                  <div className="text-xs text-[#636366]">{setting.description}</div>
                </div>
                <div className="ml-4">
                  {setting.type === 'boolean' ? (
                    <button
                      onClick={() => updateConfigValue(setting.key, value === 'true' ? 'false' : 'true')}
                      className={`
                        w-12 h-6 rounded-full transition-colors relative
                        ${value === 'true' ? 'bg-amber-500' : 'bg-[#3a3a3f]'}
                      `}
                    >
                      <span
                        className={`
                          absolute top-1 w-4 h-4 rounded-full bg-white transition-transform
                          ${value === 'true' ? 'translate-x-6' : 'translate-x-1'}
                        `}
                      />
                    </button>
                  ) : setting.type === 'number' ? (
                    <input
                      type="number"
                      value={value}
                      onChange={(e) => updateConfigValue(setting.key, e.target.value)}
                      className="w-20 px-2 py-1 rounded bg-[#2a2a2f] border border-[#3a3a3f] text-[#e5e5e7] text-sm"
                    />
                  ) : (
                    <input
                      type="text"
                      value={value}
                      onChange={(e) => updateConfigValue(setting.key, e.target.value)}
                      placeholder="owner/repo"
                      className="w-48 px-2 py-1 rounded bg-[#2a2a2f] border border-[#3a3a3f] text-[#e5e5e7] text-sm"
                    />
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-6 p-3 rounded-lg bg-[#1a1a1f] border border-[#2a2a2f]">
          <div className="text-xs text-[#636366]">
            <strong>Backup Location:</strong> {config.backup_location}
          </div>
          <div className="text-xs text-[#636366] mt-1">
            <strong>Min Free Space:</strong> {config.min_free_space_mb} MB
          </div>
          <div className="text-xs text-[#636366] mt-1">
            <strong>Download Timeout:</strong> {config.download_timeout_seconds} seconds
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      {/* Error Alert */}
      {error && (
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-4">
          <div className="flex items-start">
            <svg className="w-5 h-5 text-red-500 mr-2 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div className="flex-1">
              <div className="font-semibold text-red-400">Error</div>
              <div className="text-sm text-red-300 mt-1">{error}</div>
            </div>
            <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* Success Alert */}
      {successMessage && (
        <div className="bg-green-900/20 border border-green-800 rounded-lg p-4">
          <div className="flex items-center">
            <svg className="w-5 h-5 text-green-500 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <div className="text-green-400 font-semibold">{successMessage}</div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-[#2a2a2f]">
        {(['status', 'history', 'settings'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`
              px-4 py-2 text-sm font-medium transition-colors
              ${activeTab === tab
                ? 'text-amber-500 border-b-2 border-amber-500'
                : 'text-[#636366] hover:text-[#b4b4b8]'
              }
            `}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      {activeTab === 'status' && (
        <div className="space-y-4">
          {/* Current Version */}
          <div className="flex items-center justify-between">
            <div>
              <div className="text-sm text-[#636366]">Current Version</div>
              <div className="text-lg font-mono font-semibold">
                v{status?.current_version || 'Loading...'}
              </div>
              {status?.installed_at && (
                <div className="text-xs text-[#636366]">
                  Installed: {formatDate(status.installed_at)}
                  {status.install_method && ` (${status.install_method})`}
                </div>
              )}
            </div>
            <button
              onClick={checkForUpdates}
              disabled={isChecking || isUpdating}
              className={`
                px-4 py-2 rounded-lg font-medium transition-colors
                ${isChecking || isUpdating
                  ? 'bg-[#2a2a2f] text-[#636366] cursor-not-allowed'
                  : 'bg-amber-500 text-black hover:bg-amber-600'
                }
              `}
            >
              {isChecking ? 'Checking...' : 'Check for Updates'}
            </button>
          </div>

          {status?.last_check_at && (
            <div className="text-xs text-[#636366]">
              Last checked: {formatDate(status.last_check_at)}
            </div>
          )}

          {/* Updating state */}
          {renderUpdatingState()}

          {/* Update available banner */}
          {!isUpdating && renderUpdateBanner()}
        </div>
      )}

      {activeTab === 'history' && renderHistoryTab()}

      {activeTab === 'settings' && renderSettingsTab()}
    </div>
  );
}
