'use client';

// Solarized color palette (matching GPIOPinDiagram)
const SOLARIZED = {
  base03: '#002B36',
  base02: '#073642',
  base01: '#586E75',
  base0: '#839496',
  base1: '#93A1A1',
  green: '#859900',
  yellow: '#B58900',
};

// PCB green color
const PCB_GREEN = '#1a472a';
const PCB_GREEN_LIGHT = '#2a5a3a';

interface BoardOrientationProps {
  selectedPhysicalPin?: number | null;
  piModel?: string | null;
}

/**
 * Simplified Raspberry Pi board illustration showing GPIO header orientation.
 * Uses Solarized color scheme to match pinout.xyz style.
 */
export default function BoardOrientation({
  selectedPhysicalPin,
  piModel
}: BoardOrientationProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold" style={{ color: SOLARIZED.base1 }}>Board Orientation</h4>
        {piModel && (
          <span className="text-xs" style={{ color: SOLARIZED.base01 }}>{piModel}</span>
        )}
      </div>

      {/* Board illustration */}
      <div
        className="rounded-xl p-4 border"
        style={{ backgroundColor: SOLARIZED.base03, borderColor: SOLARIZED.base02 }}
      >
        <svg
          viewBox="0 0 200 130"
          className="w-full max-w-[280px] mx-auto"
          style={{ minHeight: '160px' }}
        >
          {/* PCB Board */}
          <rect
            x="10"
            y="10"
            width="180"
            height="110"
            rx="4"
            fill={PCB_GREEN}
            stroke={PCB_GREEN_LIGHT}
            strokeWidth="1"
          />

          {/* Board edge detail */}
          <rect
            x="12"
            y="12"
            width="176"
            height="106"
            rx="3"
            fill="none"
            stroke={PCB_GREEN_LIGHT}
            strokeWidth="0.5"
          />

          {/* GPIO Header (top left) */}
          <rect
            x="20"
            y="18"
            width="45"
            height="70"
            rx="2"
            fill={selectedPhysicalPin ? '#3b5a2a' : '#2a472a'}
            stroke={selectedPhysicalPin ? SOLARIZED.green : '#3a6a4a'}
            strokeWidth={selectedPhysicalPin ? '2' : '1'}
          />

          {/* GPIO pin dots */}
          {Array.from({ length: 20 }, (_, row) => (
            <g key={row}>
              {/* Left column (odd pins) */}
              <circle
                cx="32"
                cy={22 + row * 3.2}
                r="1.3"
                fill={
                  selectedPhysicalPin === row * 2 + 1
                    ? SOLARIZED.green
                    : SOLARIZED.base01
                }
              />
              {/* Right column (even pins) */}
              <circle
                cx="52"
                cy={22 + row * 3.2}
                r="1.3"
                fill={
                  selectedPhysicalPin === row * 2 + 2
                    ? SOLARIZED.green
                    : SOLARIZED.base01
                }
              />
            </g>
          ))}

          {/* GPIO Label */}
          <text
            x="42"
            y="98"
            textAnchor="middle"
            fill={SOLARIZED.green}
            fontSize="6"
            fontFamily="monospace"
            fontWeight="500"
          >
            GPIO
          </text>

          {/* USB Ports (right side) */}
          <rect x="168" y="25" width="22" height="20" rx="2" fill={SOLARIZED.base02} stroke={SOLARIZED.base01} strokeWidth="0.5" />
          <rect x="168" y="50" width="22" height="20" rx="2" fill={SOLARIZED.base02} stroke={SOLARIZED.base01} strokeWidth="0.5" />
          <text x="179" y="38" textAnchor="middle" fill={SOLARIZED.base01} fontSize="5" fontFamily="monospace">USB</text>
          <text x="179" y="63" textAnchor="middle" fill={SOLARIZED.base01} fontSize="5" fontFamily="monospace">USB</text>

          {/* Ethernet Port */}
          <rect x="168" y="78" width="22" height="28" rx="2" fill={SOLARIZED.base02} stroke={SOLARIZED.base01} strokeWidth="0.5" />
          <text x="179" y="95" textAnchor="middle" fill={SOLARIZED.base01} fontSize="5" fontFamily="monospace">ETH</text>

          {/* Power/USB-C Port */}
          <rect x="20" y="104" width="18" height="8" rx="2" fill={SOLARIZED.base02} stroke={SOLARIZED.base01} strokeWidth="0.5" />
          <text x="29" y="110" textAnchor="middle" fill={SOLARIZED.base01} fontSize="4" fontFamily="monospace">PWR</text>

          {/* HDMI Ports */}
          <rect x="50" y="104" width="14" height="8" rx="1" fill={SOLARIZED.base02} stroke={SOLARIZED.base01} strokeWidth="0.5" />
          <rect x="70" y="104" width="14" height="8" rx="1" fill={SOLARIZED.base02} stroke={SOLARIZED.base01} strokeWidth="0.5" />

          {/* SD Card slot */}
          <rect x="110" y="108" width="20" height="4" rx="1" fill={SOLARIZED.base02} stroke={SOLARIZED.base01} strokeWidth="0.5" />
          <text x="120" y="105" textAnchor="middle" fill={SOLARIZED.base01} fontSize="4" fontFamily="monospace">SD</text>

          {/* Pi branding */}
          <text
            x="100"
            y="50"
            textAnchor="middle"
            fill={PCB_GREEN_LIGHT}
            fontSize="9"
            fontWeight="bold"
            fontFamily="system-ui, sans-serif"
          >
            Raspberry Pi
          </text>
          <text
            x="100"
            y="62"
            textAnchor="middle"
            fill={PCB_GREEN_LIGHT}
            fontSize="6"
            fontFamily="monospace"
          >
            {piModel?.includes('5') ? 'Model 5' : piModel?.includes('4') ? 'Model 4' : ''}
          </text>

          {/* Pin 1 indicator */}
          <path
            d="M 18 16 L 22 10 L 26 16"
            fill="none"
            stroke={SOLARIZED.green}
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <text
            x="22"
            y="8"
            textAnchor="middle"
            fill={SOLARIZED.green}
            fontSize="5"
            fontFamily="monospace"
            fontWeight="500"
          >
            Pin 1
          </text>

          {/* Orientation label */}
          <text
            x="179"
            y="16"
            textAnchor="end"
            fill={SOLARIZED.base01}
            fontSize="5"
            fontFamily="system-ui, sans-serif"
          >
            USB/ETH →
          </text>
        </svg>
      </div>

      {/* Instructions */}
      <div className="text-xs space-y-1" style={{ color: SOLARIZED.base01 }}>
        <p>
          <span style={{ color: SOLARIZED.green }}>●</span> GPIO header is at top-left (highlighted when pin selected)
        </p>
        <p>
          Pin 1 is marked with arrow. Odd pins on left, even on right.
        </p>
      </div>
    </div>
  );
}
