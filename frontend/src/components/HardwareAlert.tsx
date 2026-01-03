'use client';

import { useEffect, useState, useRef } from 'react';
import { useToast } from '@/contexts/ToastContext';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface HardwareAlertData {
  has_alerts: boolean;
  alerts: Array<{
    type: string;
    message: string;
    hardware: string;
  }>;
  labjack_mock: boolean;
  ola_mock: boolean;
}

/**
 * HardwareAlert component - checks for hardware available in mock mode
 * and shows a toast notification with a link to settings
 */
export function HardwareAlert() {
  const { showToast } = useToast();
  const hasShownAlert = useRef(false);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    // Only check once per session
    if (hasShownAlert.current || dismissed) return;

    // Check if user has dismissed this session
    const dismissedSession = sessionStorage.getItem('hardware-alert-dismissed');
    if (dismissedSession === 'true') {
      setDismissed(true);
      return;
    }

    const checkHardwareAlerts = async () => {
      try {
        const res = await fetch(`${API_URL}/api/config/hardware-alert`);
        if (!res.ok) return;

        const data: HardwareAlertData = await res.json();

        if (data.has_alerts && data.alerts.length > 0) {
          hasShownAlert.current = true;

          // Show toast for each alert
          data.alerts.forEach((alert, index) => {
            setTimeout(() => {
              showToast({
                type: 'warning',
                message: alert.message,
                duration: 0, // Don't auto-dismiss
                action: {
                  label: 'Configure',
                  href: '/config/settings',
                },
              });
            }, index * 500); // Stagger multiple alerts
          });
        }
      } catch (err) {
        // Silently fail - this is just an optional notification
        console.debug('Hardware alert check failed:', err);
      }
    };

    // Delay check slightly to let the page load
    const timer = setTimeout(checkHardwareAlerts, 1500);
    return () => clearTimeout(timer);
  }, [showToast, dismissed]);

  // This component doesn't render anything - it just triggers toasts
  return null;
}
