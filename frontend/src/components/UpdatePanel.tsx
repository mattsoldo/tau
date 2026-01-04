'use client';

import { useState, useCallback, useEffect } from 'react';
import { api, API_URL, UpdateStatusResponse, UpdateCheckResponse } from '../utils/api';

export default function UpdatePanel() {
  // State
  const [currentVersion, setCurrentVersion] = useState<string>('');
  const [availableVersion, setAvailableVersion] = useState<string | null>(null);
  const [updateAvailable, setUpdateAvailable] = useState<boolean>(false);
  const [changelog, setChangelog] = useState<string>('');
  const [commitsBehind, setCommitsBehind] = useState<number>(0);

  const [isChecking, setIsChecking] = useState<boolean>(false);
  const [isUpdating, setIsUpdating] = useState<boolean>(false);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [updateError, setUpdateError] = useState<string | null>(null);

  const [reconnectCountdown, setReconnectCountdown] = useState<number>(0);
  const [showSuccess, setShowSuccess] = useState<boolean>(false);

  // Fetch current update status on mount
  useEffect(() => {
    fetchUpdateStatus();
  }, []);

  const fetchUpdateStatus = useCallback(async () => {
    try {
      const status: UpdateStatusResponse = await api.updates.getStatus();
      setCurrentVersion(status.current_version);
      setAvailableVersion(status.available_version);
      setUpdateAvailable(status.update_available);
      setIsUpdating(status.is_updating);

      // If an update is in progress, start reconnect polling
      if (status.is_updating) {
        startReconnectPolling();
      }
    } catch (error) {
      console.error('Failed to fetch update status:', error);
    }
  }, []);

  const checkForUpdates = useCallback(async () => {
    setIsChecking(true);
    setCheckError(null);

    try {
      const result: UpdateCheckResponse = await api.updates.check();
      setCurrentVersion(result.current_version);
      setAvailableVersion(result.latest_version);
      setUpdateAvailable(result.update_available);
      setCommitsBehind(result.commits_behind);
      setChangelog(result.changelog);

      if (!result.update_available) {
        setShowSuccess(true);
        setTimeout(() => setShowSuccess(false), 3000);
      }
    } catch (error: any) {
      setCheckError(error.message || 'Failed to check for updates');
    } finally {
      setIsChecking(false);
    }
  }, []);

  const startUpdate = useCallback(async () => {
    if (!confirm('This will restart the daemon and frontend services. Continue?')) {
      return;
    }

    setIsUpdating(true);
    setUpdateError(null);

    try {
      await api.updates.start();
      // Update started, begin reconnect polling
      startReconnectPolling();
    } catch (error: any) {
      setUpdateError(error.message || 'Failed to start update');
      setIsUpdating(false);
    }
  }, []);

  const startReconnectPolling = useCallback(() => {
    setReconnectCountdown(60); // 60 seconds countdown

    const interval = setInterval(async () => {
      try {
        const response = await fetch(`${API_URL}/health`);
        if (response.ok) {
          // Daemon is back up, refresh page
          clearInterval(interval);
          window.location.reload();
        }
      } catch (e) {
        // Still down, keep polling
      }
    }, 2000);

    // Countdown timer
    const countdownInterval = setInterval(() => {
      setReconnectCountdown((prev) => {
        if (prev <= 1) {
          clearInterval(countdownInterval);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    // Cleanup on unmount
    return () => {
      clearInterval(interval);
      clearInterval(countdownInterval);
    };
  }, []);

  // Format changelog for display
  const formattedChangelog = changelog.split('\n').filter(line => line.trim());

  return (
    <div className="space-y-4">
      {/* Current Version */}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm text-[#636366]">Current Version</div>
          <div className="text-lg font-mono">{currentVersion || 'Loading...'}</div>
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

      {/* Check Error */}
      {checkError && (
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-4">
          <div className="flex items-start">
            <svg className="w-5 h-5 text-red-500 mr-2 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div>
              <div className="font-semibold text-red-400">Error Checking for Updates</div>
              <div className="text-sm text-red-300 mt-1">{checkError}</div>
            </div>
          </div>
          <button
            onClick={() => setCheckError(null)}
            className="mt-2 text-sm text-red-400 hover:text-red-300"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Update Error */}
      {updateError && (
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-4">
          <div className="flex items-start">
            <svg className="w-5 h-5 text-red-500 mr-2 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div>
              <div className="font-semibold text-red-400">Update Failed</div>
              <div className="text-sm text-red-300 mt-1">{updateError}</div>
            </div>
          </div>
          <button
            onClick={() => setUpdateError(null)}
            className="mt-2 text-sm text-red-400 hover:text-red-300"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Success Message */}
      {showSuccess && !updateAvailable && (
        <div className="bg-green-900/20 border border-green-800 rounded-lg p-4">
          <div className="flex items-center">
            <svg className="w-5 h-5 text-green-500 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <div className="text-green-400 font-semibold">System is up to date!</div>
          </div>
        </div>
      )}

      {/* Update Available */}
      {updateAvailable && !isUpdating && (
        <div className="bg-amber-900/20 border border-amber-800 rounded-lg p-4 space-y-4">
          <div className="flex items-start">
            <svg className="w-5 h-5 text-amber-500 mr-2 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div className="flex-1">
              <div className="font-semibold text-amber-400">Update Available</div>
              <div className="text-sm text-amber-300 mt-1">
                Version {availableVersion} ({commitsBehind} commit{commitsBehind !== 1 ? 's' : ''} behind)
              </div>
            </div>
          </div>

          {/* Changelog */}
          {formattedChangelog.length > 0 && (
            <div>
              <div className="text-sm font-semibold text-[#e5e5e7] mb-2">Recent Changes:</div>
              <div className="bg-[#0a0a0b] rounded border border-[#2a2a2f] p-3 max-h-64 overflow-y-auto">
                <div className="font-mono text-xs space-y-1">
                  {formattedChangelog.map((line, idx) => (
                    <div key={idx} className="text-[#b4b4b8]">
                      {line}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* Update Button */}
          <button
            onClick={startUpdate}
            className="w-full bg-amber-500 text-black font-semibold py-2 px-4 rounded-lg hover:bg-amber-600 transition-colors"
          >
            Update Now
          </button>
        </div>
      )}

      {/* Updating State */}
      {isUpdating && (
        <div className="bg-blue-900/20 border border-blue-800 rounded-lg p-4 space-y-4">
          <div className="flex items-start">
            <div className="animate-spin mr-3 flex-shrink-0">
              <svg className="w-5 h-5 text-blue-500" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            </div>
            <div className="flex-1">
              <div className="font-semibold text-blue-400">Updating System...</div>
              <div className="text-sm text-blue-300 mt-1">
                Installing updates and restarting services. This may take a few minutes.
              </div>
              {reconnectCountdown > 0 && (
                <div className="text-sm text-blue-300 mt-2">
                  Waiting for daemon to restart... ({reconnectCountdown}s)
                </div>
              )}
            </div>
          </div>

          {/* Progress Steps */}
          <div className="bg-[#0a0a0b] rounded border border-[#2a2a2f] p-3 space-y-2 text-sm">
            <div className="flex items-center text-[#b4b4b8]">
              <div className="w-4 h-4 mr-2 flex-shrink-0">⏳</div>
              <div>Pulling latest code from git</div>
            </div>
            <div className="flex items-center text-[#b4b4b8]">
              <div className="w-4 h-4 mr-2 flex-shrink-0">⏳</div>
              <div>Installing dependencies</div>
            </div>
            <div className="flex items-center text-[#b4b4b8]">
              <div className="w-4 h-4 mr-2 flex-shrink-0">⏳</div>
              <div>Running database migrations</div>
            </div>
            <div className="flex items-center text-[#b4b4b8]">
              <div className="w-4 h-4 mr-2 flex-shrink-0">⏳</div>
              <div>Building frontend</div>
            </div>
            <div className="flex items-center text-[#b4b4b8]">
              <div className="w-4 h-4 mr-2 flex-shrink-0">⏳</div>
              <div>Restarting services</div>
            </div>
          </div>

          <div className="text-xs text-[#636366]">
            The page will automatically refresh when the update is complete.
          </div>
        </div>
      )}
    </div>
  );
}
