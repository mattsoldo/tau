'use client';

import { useState, useEffect, useMemo } from 'react';
import './gpio-pinout.css';

/**
 * GPIO Pin Diagram - Based on pinout.xyz design
 * https://github.com/pinout-xyz/Pinout.xyz
 *
 * Replicates the visual style of pinout.xyz with:
 * - Two-column layout (odd pins left, even pins right)
 * - Circular pin badges with physical numbers
 * - Color-coded pin types (GPIO, power, ground, I2C, SPI, etc.)
 * - Hover effects that highlight the full row
 *
 * Supports two modes:
 * - 'select': For switch configuration (click to select pins)
 * - 'monitor': For dashboard (shows live HIGH/LOW states)
 */

// Types
interface HeaderPin {
  physical: number;
  type: 'gpio' | 'power' | 'ground' | 'disabled';
  label: string;
  bcm?: number;
  disabled_reason?: string;
  in_use: boolean;
  switch_id?: number;
  switch_name?: string;
  state?: boolean | null;  // Live state for monitor mode
}

interface GPIOLayoutResponse {
  header_pins: HeaderPin[];
  ground_pins: number[];
  available_bcm_pins: number[];
}

interface GPIOStatusResponse {
  platform_available: boolean;
  is_raspberry_pi: boolean;
  pi_model?: string;
  reason?: string;
  gpio_connected: boolean;
  pins: HeaderPin[];
  read_count: number;
  error_count: number;
}

interface GPIOPinDiagramProps {
  /** Mode: 'select' for switch config, 'monitor' for dashboard */
  mode?: 'select' | 'monitor';
  /** Currently selected BCM pin (select mode only) */
  selectedBcmPin?: number | null;
  /** Callback when a pin is selected (select mode only) */
  onPinSelect?: (bcmPin: number, physicalPin: number) => void;
  /** API base URL */
  apiUrl: string;
  /** Polling interval in ms for monitor mode (default: 2000) */
  pollInterval?: number;
  /** Whether to show the header with title and link */
  showHeader?: boolean;
  /** Whether to show wiring instructions (select mode only) */
  showWiringInfo?: boolean;
  /** Whether to show statistics (monitor mode only) */
  showStats?: boolean;
  /** Compact mode - smaller size for embedding */
  compact?: boolean;
}

// Solarized color palette (matching pinout.xyz)
const COLORS = {
  purple: '#6c71c4',
  pink: '#D33682',
  green: '#859900',
  red: '#DC322F',
  yellow: '#B58900',
  blue: '#268BD2',
  cyan: '#2aa198',
  dark: '#073642',
};

// Get pin color based on type and label
const getPinColor = (pin: HeaderPin): string => {
  if (pin.type === 'ground') return COLORS.dark;
  if (pin.type === 'power') {
    return pin.label.includes('5V') ? COLORS.red : COLORS.yellow;
  }

  const label = pin.label.toLowerCase();
  if (label.includes('sda') || label.includes('scl')) return COLORS.blue;
  if (label.includes('mosi') || label.includes('miso') || label.includes('sclk') || label.includes('ce0') || label.includes('ce1')) return COLORS.pink;
  if (label.includes('tx') || label.includes('rx')) return COLORS.purple;
  if (label.includes('id_s') || label.includes('eeprom')) return COLORS.cyan;
  if (label.includes('pcm')) return COLORS.cyan;

  return COLORS.green;
};

// Get CSS class for pin type (for styling)
const getPinTypeClass = (pin: HeaderPin): string => {
  if (pin.type === 'ground') return 'type-gnd';
  if (pin.type === 'power') {
    return pin.label.includes('5V') ? 'type-pow5v' : 'type-pow3v3';
  }

  const label = pin.label.toLowerCase();
  if (label.includes('sda') || label.includes('scl')) return 'type-i2c';
  if (label.includes('mosi') || label.includes('miso') || label.includes('sclk') || label.includes('ce0') || label.includes('ce1')) return 'type-spi';
  if (label.includes('tx') || label.includes('rx')) return 'type-uart';
  if (label.includes('id_s')) return 'type-i2c';
  if (label.includes('pcm')) return 'type-pcm';

  return 'type-gpio';
};

// Format pin name for display
const formatPinName = (pin: HeaderPin): { name: string; sub?: string } => {
  if (pin.type === 'ground') return { name: 'Ground' };
  if (pin.type === 'power') {
    return { name: pin.label.includes('5V') ? '5v Power' : '3v3 Power' };
  }

  // Extract function from label like "GPIO2 (SDA)" or "GPIO14 (TX)"
  const match = pin.label.match(/GPIO(\d+)\s*\(([^)]+)\)/i);
  if (match) {
    return { name: `GPIO ${match[1]}`, sub: match[2] };
  }

  // Just GPIO number
  if (pin.bcm != null) {
    return { name: `GPIO ${pin.bcm}` };
  }

  return { name: pin.label };
};

export default function GPIOPinDiagram({
  mode = 'select',
  selectedBcmPin = null,
  onPinSelect,
  apiUrl,
  pollInterval = 2000,
  showHeader = true,
  showWiringInfo = true,
  showStats = false,
  compact = false,
}: GPIOPinDiagramProps) {
  const [layout, setLayout] = useState<GPIOLayoutResponse | null>(null);
  const [statusData, setStatusData] = useState<GPIOStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch GPIO layout (for select mode) or status (for monitor mode)
  useEffect(() => {
    const fetchData = async () => {
      try {
        if (mode === 'monitor') {
          // Use status endpoint which includes live pin states
          const res = await fetch(`${apiUrl}/api/gpio/status`);
          if (!res.ok) throw new Error('Failed to fetch GPIO status');
          const data: GPIOStatusResponse = await res.json();
          setStatusData(data);
          // Convert to layout format for compatibility
          setLayout({
            header_pins: data.pins,
            ground_pins: data.pins.filter(p => p.type === 'ground').map(p => p.physical),
            available_bcm_pins: data.pins.filter(p => p.type === 'gpio' && !p.in_use && p.bcm != null).map(p => p.bcm!),
          });
        } else {
          // Use layout endpoint for selection
          const res = await fetch(`${apiUrl}/api/gpio/layout`);
          if (!res.ok) throw new Error('Failed to fetch GPIO layout');
          const data = await res.json();
          setLayout(data);
        }
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load GPIO data');
      } finally {
        setLoading(false);
      }
    };

    fetchData();

    // Set up polling for monitor mode
    if (mode === 'monitor') {
      const interval = setInterval(fetchData, pollInterval);
      return () => clearInterval(interval);
    }
  }, [apiUrl, mode, pollInterval]);

  // Calculate nearest ground pin when a pin is selected
  const nearestGroundPhysical = useMemo(() => {
    if (!selectedBcmPin || !layout) return null;

    const selectedPin = layout.header_pins.find(p => p.bcm === selectedBcmPin);
    if (!selectedPin) return null;

    let minDistance = Infinity;
    let nearest = layout.ground_pins[0];
    for (const groundPin of layout.ground_pins) {
      const distance = Math.abs(groundPin - selectedPin.physical);
      if (distance < minDistance) {
        minDistance = distance;
        nearest = groundPin;
      }
    }
    return nearest;
  }, [selectedBcmPin, layout]);

  // Split pins into odd (left/bottom) and even (right/top) columns
  const { oddPins, evenPins } = useMemo(() => {
    if (!layout) return { oddPins: [], evenPins: [] };

    const odd: HeaderPin[] = [];
    const even: HeaderPin[] = [];

    for (const pin of layout.header_pins) {
      if (pin.physical % 2 === 1) {
        odd.push(pin);
      } else {
        even.push(pin);
      }
    }

    // Sort by physical pin number
    odd.sort((a, b) => a.physical - b.physical);
    even.sort((a, b) => a.physical - b.physical);

    return { oddPins: odd, evenPins: even };
  }, [layout]);

  const handlePinClick = (pin: HeaderPin) => {
    if (mode !== 'select') return;
    if (pin.type !== 'gpio') return;
    if (pin.in_use) return;
    if (pin.bcm == null) return;
    if (onPinSelect) onPinSelect(pin.bcm, pin.physical);
  };

  const isPinSelected = (pin: HeaderPin) => pin.bcm === selectedBcmPin;
  const isPinSelectable = (pin: HeaderPin) => mode === 'select' && pin.type === 'gpio' && !pin.in_use;
  const isSuggestedGround = (pin: HeaderPin) => pin.type === 'ground' && pin.physical === nearestGroundPhysical;

  // Get pin badge color - in monitor mode, override for pins with state
  const getPinBadgeColor = (pin: HeaderPin): string => {
    if (mode === 'monitor' && pin.type === 'gpio' && pin.state !== undefined && pin.state !== null) {
      return pin.state ? '#f59e0b' : '#22c55e'; // amber for HIGH, green for LOW
    }
    return getPinColor(pin);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="w-6 h-6 border-2 rounded-full animate-spin" style={{ borderColor: COLORS.green, borderTopColor: 'transparent' }}></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="px-4 py-3 rounded-lg text-sm" style={{ backgroundColor: `${COLORS.red}20`, color: COLORS.red }}>
        {error}
      </div>
    );
  }

  const renderPin = (pin: HeaderPin) => {
    const pinName = formatPinName(pin);
    const pinColor = getPinBadgeColor(pin);
    const pinType = getPinTypeClass(pin);
    const selected = isPinSelected(pin);
    const selectable = isPinSelectable(pin);
    const suggestedGround = isSuggestedGround(pin);

    // In monitor mode, show state for GPIO pins
    const hasState = mode === 'monitor' && pin.type === 'gpio' && pin.state !== undefined && pin.state !== null;
    const stateText = hasState ? (pin.state ? 'HIGH' : 'LOW') : null;

    // Build class list similar to pinout.xyz
    const isOverlayPower = pin.type === 'power';
    const isOverlayGround = pin.type === 'ground';

    const classes = [
      `pin-${pin.physical}`,
      pinType,
      selected ? 'active' : '',
      isOverlayGround ? 'overlay-ground' : '',
      isOverlayPower ? 'overlay-power' : '',
      suggestedGround ? 'suggested-ground' : '',
      selectable ? 'selectable' : '',
      hasState && pin.state ? 'state-high' : '',
      hasState && !pin.state ? 'state-low' : '',
      compact ? 'compact' : '',
    ].filter(Boolean).join(' ');

    // Build tooltip
    const tooltipParts = [];
    if (pin.in_use) tooltipParts.push(`Switch: ${pin.switch_name || 'unnamed'}`);
    if (stateText) tooltipParts.push(`State: ${stateText}`);
    if (pin.disabled_reason) tooltipParts.push(pin.disabled_reason);
    if (!tooltipParts.length) tooltipParts.push(pinName.name);
    const tooltip = tooltipParts.join(' | ');

    return (
      <li
        key={pin.physical}
        className={classes}
        onClick={() => handlePinClick(pin)}
      >
        <a title={tooltip}>
          <span className="default">
            {mode === 'monitor' && hasState ? (
              <>
                {pinName.name}
                <small className={pin.state ? 'state-high-text' : 'state-low-text'}> {stateText}</small>
              </>
            ) : (
              <>
                {pinName.name}
                {pinName.sub && <small> ({pinName.sub})</small>}
                {pin.in_use && <small className="in-use"> [in use]</small>}
              </>
            )}
          </span>
          <span className="pin-badge" style={{ backgroundColor: pinColor }}>{pin.physical}</span>
        </a>
      </li>
    );
  };

  // Format number with commas
  const formatNumber = (n: number) => n.toLocaleString();

  return (
    <div className={`gpio-pinout-container ${compact ? 'compact' : ''}`}>
      {/* Header with pinout.xyz link */}
      {showHeader && (
        <div className="gpio-header">
          <h4>GPIO Header</h4>
          <div className="flex items-center gap-2">
            {mode === 'monitor' && statusData?.gpio_connected && (
              <span className="status-badge connected">LIVE</span>
            )}
            <a
              href="https://pinout.xyz"
              target="_blank"
              rel="noopener noreferrer"
              className="pinout-link"
            >
              pinout.xyz
            </a>
          </div>
        </div>
      )}

      {/* GPIO Pin diagram - pinout.xyz style */}
      <div className="gpio-pins">
        <ul className="col-left">
          {oddPins.map(pin => renderPin(pin))}
        </ul>
        <ul className="col-right">
          {evenPins.map(pin => renderPin(pin))}
        </ul>
      </div>

      {/* Wiring instructions (select mode only) */}
      {showWiringInfo && mode === 'select' && selectedBcmPin && nearestGroundPhysical && (
        <div className="wiring-info">
          <strong>Wiring:</strong> Connect switch between{' '}
          <span className="pin-ref gpio">Pin {layout?.header_pins.find(p => p.bcm === selectedBcmPin)?.physical}</span>
          {' '}(GPIO{selectedBcmPin}) and{' '}
          <span className="pin-ref gnd">Pin {nearestGroundPhysical}</span>
          {' '}(GND)
        </div>
      )}

      {/* Statistics (monitor mode only) */}
      {showStats && mode === 'monitor' && statusData && (
        <div className="gpio-stats">
          <div className="stat">
            <span className="stat-value">{formatNumber(statusData.read_count)}</span>
            <span className="stat-label">Reads</span>
          </div>
          <div className="stat">
            <span className="stat-value">{statusData.error_count}</span>
            <span className="stat-label">Errors</span>
          </div>
          <div className="stat">
            <span className="stat-value">{statusData.pins.filter(p => p.in_use).length}</span>
            <span className="stat-label">Active</span>
          </div>
        </div>
      )}
    </div>
  );
}
