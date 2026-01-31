'use client';

import { useState, useEffect, useMemo } from 'react';

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

// Solarized-inspired color palette (matching pinout.xyz)
const SOLARIZED = {
  base03: '#002B36',  // Background darkest
  base02: '#073642',  // Background dark (ground pins)
  base01: '#586E75',  // Content secondary
  base00: '#657B83',  // Content tertiary
  base0: '#839496',   // Content default
  base1: '#93A1A1',   // Content emphasized
  base2: '#EEE8D5',   // Background light
  base3: '#FDF6E3',   // Background lightest

  // Accent colors for pin types
  yellow: '#B58900',  // 3.3V power
  orange: '#CB4B16',  // Accent
  red: '#DC322F',     // 5V power
  magenta: '#D33682', // SPI
  violet: '#6C71C4',  // UART
  blue: '#268BD2',    // I2C
  cyan: '#2AA198',    // PCM
  green: '#859900',   // GPIO
};

// Pin function to color mapping
const getPinColor = (pin: HeaderPin, isSelected: boolean, isAvailable: boolean, isSuggestedGround: boolean) => {
  if (isSelected) {
    return {
      bg: SOLARIZED.green,
      border: '#9CB400',
      text: '#FFF',
    };
  }

  if (isSuggestedGround) {
    return {
      bg: SOLARIZED.yellow,
      border: '#D4A000',
      text: SOLARIZED.base03,
    };
  }

  // Check for special function pins (I2C, SPI, UART, PCM)
  const label = pin.label.toLowerCase();

  if (pin.type === 'ground') {
    return {
      bg: SOLARIZED.base02,
      border: SOLARIZED.base01,
      text: SOLARIZED.base1,
    };
  }

  if (pin.type === 'power') {
    const is5v = label.includes('5v');
    return {
      bg: is5v ? SOLARIZED.red : SOLARIZED.yellow,
      border: is5v ? '#F04040' : '#D4A000',
      text: '#FFF',
    };
  }

  if (pin.type === 'disabled') {
    // Color by function
    if (label.includes('sda') || label.includes('scl') || label.includes('i2c')) {
      return { bg: `${SOLARIZED.blue}40`, border: SOLARIZED.blue, text: SOLARIZED.blue };
    }
    if (label.includes('mosi') || label.includes('miso') || label.includes('sclk') || label.includes('ce') || label.includes('spi')) {
      return { bg: `${SOLARIZED.magenta}40`, border: SOLARIZED.magenta, text: SOLARIZED.magenta };
    }
    if (label.includes('tx') || label.includes('rx') || label.includes('uart')) {
      return { bg: `${SOLARIZED.violet}40`, border: SOLARIZED.violet, text: SOLARIZED.violet };
    }
    if (label.includes('pcm')) {
      return { bg: `${SOLARIZED.cyan}40`, border: SOLARIZED.cyan, text: SOLARIZED.cyan };
    }
    // Default disabled (EEPROM, etc.)
    return { bg: `${SOLARIZED.base01}30`, border: SOLARIZED.base01, text: SOLARIZED.base01 };
  }

  // GPIO pins
  if (pin.type === 'gpio') {
    if (pin.in_use) {
      return {
        bg: `${SOLARIZED.base01}30`,
        border: SOLARIZED.base01,
        text: SOLARIZED.base01,
      };
    }
    // Available GPIO
    return {
      bg: `${SOLARIZED.green}25`,
      border: `${SOLARIZED.green}80`,
      text: SOLARIZED.green,
    };
  }

  return { bg: SOLARIZED.base02, border: SOLARIZED.base01, text: SOLARIZED.base0 };
};

// Legend items matching pinout.xyz style
const LEGEND_ITEMS = [
  { label: 'GPIO', color: SOLARIZED.green, description: 'Available for switch input' },
  { label: 'Selected', color: SOLARIZED.green, filled: true },
  { label: 'In Use', color: SOLARIZED.base01, description: 'Already assigned' },
  { label: 'Ground', color: SOLARIZED.base02, filled: true },
  { label: '3.3V', color: SOLARIZED.yellow, filled: true },
  { label: '5V', color: SOLARIZED.red, filled: true },
  { label: 'I2C', color: SOLARIZED.blue },
  { label: 'SPI', color: SOLARIZED.magenta },
  { label: 'UART', color: SOLARIZED.violet },
];

export default function GPIOPinDiagram({
  selectedBcmPin,
  onPinSelect,
  apiUrl
}: GPIOPinDiagramProps) {
  const [layout, setLayout] = useState<GPIOLayoutResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredPin, setHoveredPin] = useState<HeaderPin | null>(null);

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

  // Organize pins into left (odd) and right (even) columns
  const { leftColumn, rightColumn } = useMemo(() => {
    if (!layout) return { leftColumn: [], rightColumn: [] };

    const left: HeaderPin[] = [];
    const right: HeaderPin[] = [];

    for (const pin of layout.header_pins) {
      if (pin.physical % 2 === 1) {
        left.push(pin);
      } else {
        right.push(pin);
      }
    }

    left.sort((a, b) => a.physical - b.physical);
    right.sort((a, b) => a.physical - b.physical);

    return { leftColumn: left, rightColumn: right };
  }, [layout]);

  const handlePinClick = (pin: HeaderPin) => {
    if (pin.type !== 'gpio') return;
    if (pin.in_use) return;
    if (pin.bcm == null) return;  // Check for both null and undefined
    onPinSelect(pin.bcm, pin.physical);
  };

  const getShortLabel = (pin: HeaderPin): string => {
    if (pin.bcm != null) {  // Check for both null and undefined
      return pin.bcm.toString();
    }
    if (pin.type === 'ground') return 'GND';
    if (pin.label.includes('5V')) return '5V';
    if (pin.label.includes('3.3V') || pin.label.includes('3V')) return '3V3';
    return '';
  };

  const getFunctionLabel = (pin: HeaderPin): string | null => {
    if (pin.type !== 'disabled' && pin.type !== 'gpio') return null;

    const label = pin.label;
    // Extract the function in parentheses or after GPIO
    const match = label.match(/\(([^)]+)\)/);
    if (match) return match[1];

    // For disabled pins, show the full function
    if (pin.type === 'disabled') {
      if (label.includes('SDA')) return 'SDA';
      if (label.includes('SCL')) return 'SCL';
      if (label.includes('MOSI')) return 'MOSI';
      if (label.includes('MISO')) return 'MISO';
      if (label.includes('SCLK')) return 'SCLK';
      if (label.includes('CE0')) return 'CE0';
      if (label.includes('CE1')) return 'CE1';
      if (label.includes('TX')) return 'TX';
      if (label.includes('RX')) return 'RX';
      if (label.includes('ID_SD')) return 'ID_SD';
      if (label.includes('ID_SC')) return 'ID_SC';
    }
    return null;
  };

  const renderPin = (pin: HeaderPin, side: 'left' | 'right') => {
    const isSelected = pin.bcm === selectedBcmPin;
    const isSelectable = pin.type === 'gpio' && !pin.in_use;
    const isSuggestedGround = pin.type === 'ground' && pin.physical === nearestGroundPhysical;
    const colors = getPinColor(pin, isSelected, isSelectable, isSuggestedGround);
    const functionLabel = getFunctionLabel(pin);

    return (
      <div
        key={pin.physical}
        className={`flex items-center gap-1.5 ${side === 'left' ? 'flex-row' : 'flex-row-reverse'}`}
        onMouseEnter={() => setHoveredPin(pin)}
        onMouseLeave={() => setHoveredPin(null)}
      >
        {/* Physical pin number */}
        <span className={`
          text-[10px] w-5 text-center font-mono tabular-nums
          ${isSelected ? 'font-bold' : ''}
          ${isSuggestedGround ? 'font-bold' : ''}
        `} style={{ color: isSelected ? SOLARIZED.green : isSuggestedGround ? SOLARIZED.yellow : SOLARIZED.base01 }}>
          {pin.physical}
        </span>

        {/* Pin button - 44px minimum touch target */}
        <button
          onClick={() => handlePinClick(pin)}
          disabled={!isSelectable}
          className={`
            w-11 h-11 rounded-lg border-2 text-xs font-bold
            flex flex-col items-center justify-center gap-0.5
            transition-all duration-150
            ${isSelectable ? 'hover:scale-105 hover:shadow-lg cursor-pointer' : 'cursor-default'}
            ${isSelected ? 'ring-2 ring-offset-2 ring-offset-[#0a0a0b]' : ''}
          `}
          style={{
            backgroundColor: colors.bg,
            borderColor: colors.border,
            color: colors.text,
            ...(isSelected ? { ringColor: SOLARIZED.green } : {}),
          }}
          title={pin.in_use ? `In use by: ${pin.switch_name || `Switch #${pin.switch_id}`}` : pin.label}
        >
          <span className="leading-none">{getShortLabel(pin)}</span>
          {functionLabel && (
            <span className="text-[8px] opacity-80 leading-none">{functionLabel}</span>
          )}
        </button>

        {/* Label */}
        <span
          className={`text-[11px] truncate ${side === 'left' ? 'text-left' : 'text-right'}`}
          style={{
            color: isSelected ? SOLARIZED.green : isSuggestedGround ? SOLARIZED.yellow : SOLARIZED.base0,
            maxWidth: '70px',
            fontWeight: isSelected || isSuggestedGround ? 600 : 400,
          }}
        >
          {pin.bcm != null ? `GPIO${pin.bcm}` : pin.label.replace('GPIO', '').replace(/\(.*\)/, '').trim()}
          {isSuggestedGround && ' (use this)'}
        </span>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8" style={{ backgroundColor: SOLARIZED.base03 }}>
        <div className="w-6 h-6 border-2 rounded-full animate-spin" style={{ borderColor: SOLARIZED.green, borderTopColor: 'transparent' }}></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="px-4 py-3 rounded-lg text-sm" style={{ backgroundColor: `${SOLARIZED.red}20`, borderColor: SOLARIZED.red, color: SOLARIZED.red }}>
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h4 className="text-sm font-semibold" style={{ color: SOLARIZED.base1 }}>GPIO Header</h4>
          <a
            href="https://pinout.xyz"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] px-1.5 py-0.5 rounded hover:opacity-80 transition-opacity"
            style={{ backgroundColor: `${SOLARIZED.blue}30`, color: SOLARIZED.blue }}
          >
            pinout.xyz
          </a>
        </div>
        {selectedBcmPin && (
          <span
            className="px-2 py-1 text-xs rounded font-mono"
            style={{ backgroundColor: `${SOLARIZED.green}30`, color: SOLARIZED.green }}
          >
            GPIO{selectedBcmPin}
          </span>
        )}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-x-3 gap-y-1.5">
        {LEGEND_ITEMS.map(({ label, color, filled }) => (
          <div key={label} className="flex items-center gap-1">
            <div
              className="w-3 h-3 rounded border"
              style={{
                backgroundColor: filled ? color : `${color}30`,
                borderColor: color,
              }}
            />
            <span className="text-[10px]" style={{ color: SOLARIZED.base0 }}>{label}</span>
          </div>
        ))}
      </div>

      {/* Pin diagram container */}
      <div
        className="rounded-xl p-4 border"
        style={{ backgroundColor: SOLARIZED.base03, borderColor: SOLARIZED.base02 }}
      >
        {/* Pin 1 indicator */}
        <div className="flex items-center gap-1 mb-2 ml-6">
          <svg width="12" height="8" viewBox="0 0 12 8" fill={SOLARIZED.green}>
            <path d="M6 0L12 8H0L6 0Z" />
          </svg>
          <span className="text-[10px] font-medium" style={{ color: SOLARIZED.green }}>Pin 1</span>
        </div>

        {/* Pin grid */}
        <div className="flex gap-2 justify-center">
          {/* Left column (odd pins) */}
          <div className="flex flex-col gap-0.5">
            {leftColumn.map(pin => renderPin(pin, 'left'))}
          </div>

          {/* Center divider representing the header notch */}
          <div className="flex flex-col items-center">
            <div
              className="w-3 flex-1 rounded-sm"
              style={{ backgroundColor: SOLARIZED.base02 }}
            />
          </div>

          {/* Right column (even pins) */}
          <div className="flex flex-col gap-0.5">
            {rightColumn.map(pin => renderPin(pin, 'right'))}
          </div>
        </div>

        {/* Orientation hint */}
        <div className="flex justify-center mt-3">
          <span className="text-[10px]" style={{ color: SOLARIZED.base01 }}>
            USB / Ethernet side →
          </span>
        </div>
      </div>

      {/* Hover tooltip */}
      {hoveredPin && (
        <div
          className="px-3 py-2 rounded-lg text-xs border"
          style={{ backgroundColor: SOLARIZED.base02, borderColor: SOLARIZED.base01 }}
        >
          <div className="flex items-center gap-2">
            <span className="font-mono" style={{ color: SOLARIZED.base1 }}>
              Pin {hoveredPin.physical}
            </span>
            <span style={{ color: SOLARIZED.base01 }}>•</span>
            <span style={{ color: SOLARIZED.base0 }}>{hoveredPin.label}</span>
          </div>
          {hoveredPin.in_use && (
            <div className="mt-1" style={{ color: SOLARIZED.yellow }}>
              In use by: {hoveredPin.switch_name || `Switch #${hoveredPin.switch_id}`}
            </div>
          )}
          {hoveredPin.disabled_reason && (
            <div className="mt-1" style={{ color: SOLARIZED.orange }}>
              {hoveredPin.disabled_reason}
            </div>
          )}
          {hoveredPin.type === 'gpio' && !hoveredPin.in_use && (
            <div className="mt-1" style={{ color: SOLARIZED.green }}>
              Click to select
            </div>
          )}
        </div>
      )}

      {/* Wiring instructions */}
      {selectedBcmPin && nearestGroundPhysical && (
        <div
          className="px-4 py-3 rounded-lg border"
          style={{ backgroundColor: `${SOLARIZED.yellow}15`, borderColor: `${SOLARIZED.yellow}50` }}
        >
          <div className="flex items-start gap-2">
            <svg className="w-5 h-5 flex-shrink-0 mt-0.5" fill={SOLARIZED.yellow} viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
            </svg>
            <div>
              <div className="text-sm font-medium" style={{ color: SOLARIZED.yellow }}>Wiring</div>
              <div className="text-sm mt-1" style={{ color: SOLARIZED.base1 }}>
                Connect switch between{' '}
                <strong style={{ color: SOLARIZED.green }}>
                  Pin {layout?.header_pins.find(p => p.bcm === selectedBcmPin)?.physical}
                </strong>
                {' '}(GPIO{selectedBcmPin}) and{' '}
                <strong style={{ color: SOLARIZED.yellow }}>Pin {nearestGroundPhysical}</strong>
                {' '}(GND)
              </div>
              <div className="text-[11px] mt-1.5" style={{ color: SOLARIZED.base01 }}>
                Default: Pull-up resistor enabled (switch closed = LOW)
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
