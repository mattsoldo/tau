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
}

interface GPIOLayoutResponse {
  header_pins: HeaderPin[];
  ground_pins: number[];
  available_bcm_pins: number[];
}

interface GPIOPinDiagramProps {
  selectedBcmPin: number | null;
  onPinSelect: (bcmPin: number, physicalPin: number) => void;
  apiUrl: string;
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
  selectedBcmPin,
  onPinSelect,
  apiUrl
}: GPIOPinDiagramProps) {
  const [layout, setLayout] = useState<GPIOLayoutResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch GPIO layout
  useEffect(() => {
    const fetchLayout = async () => {
      try {
        const res = await fetch(`${apiUrl}/api/gpio/layout`);
        if (!res.ok) throw new Error('Failed to fetch GPIO layout');
        const data = await res.json();
        setLayout(data);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load GPIO layout');
      } finally {
        setLoading(false);
      }
    };

    fetchLayout();
  }, [apiUrl]);

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
    if (pin.type !== 'gpio') return;
    if (pin.in_use) return;
    if (pin.bcm == null) return;
    onPinSelect(pin.bcm, pin.physical);
  };

  const isPinSelected = (pin: HeaderPin) => pin.bcm === selectedBcmPin;
  const isPinSelectable = (pin: HeaderPin) => pin.type === 'gpio' && !pin.in_use;
  const isSuggestedGround = (pin: HeaderPin) => pin.type === 'ground' && pin.physical === nearestGroundPhysical;

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
    const pinColor = getPinColor(pin);
    const pinType = getPinTypeClass(pin);
    const selected = isPinSelected(pin);
    const selectable = isPinSelectable(pin);
    const suggestedGround = isSuggestedGround(pin);

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
    ].filter(Boolean).join(' ');

    return (
      <li
        key={pin.physical}
        className={classes}
        onClick={() => handlePinClick(pin)}
      >
        <a title={pin.in_use ? `In use by: ${pin.switch_name || 'switch'}` : pin.disabled_reason || pinName.name}>
          <span className="default">
            {pinName.name}
            {pinName.sub && <small> ({pinName.sub})</small>}
            {pin.in_use && <small className="in-use"> [in use]</small>}
          </span>
          <span className="pin-badge" style={{ backgroundColor: pinColor }}>{pin.physical}</span>
        </a>
      </li>
    );
  };

  return (
    <div className="gpio-pinout-container">
      {/* Header with pinout.xyz link */}
      <div className="gpio-header">
        <h4>GPIO Header</h4>
        <a
          href="https://pinout.xyz"
          target="_blank"
          rel="noopener noreferrer"
          className="pinout-link"
        >
          pinout.xyz
        </a>
      </div>

      {/* GPIO Pin diagram - pinout.xyz style */}
      <div className="gpio-pins">
        <ul className="col-left">
          {oddPins.map(pin => renderPin(pin))}
        </ul>
        <ul className="col-right">
          {evenPins.map(pin => renderPin(pin))}
        </ul>
      </div>

      {/* Wiring instructions */}
      {selectedBcmPin && nearestGroundPhysical && (
        <div className="wiring-info">
          <strong>Wiring:</strong> Connect switch between{' '}
          <span className="pin-ref gpio">Pin {layout?.header_pins.find(p => p.bcm === selectedBcmPin)?.physical}</span>
          {' '}(GPIO{selectedBcmPin}) and{' '}
          <span className="pin-ref gnd">Pin {nearestGroundPhysical}</span>
          {' '}(GND)
        </div>
      )}
    </div>
  );
}
