'use client';

import { kelvinToColor } from '@/utils/lighting';

export interface CCTSliderProps {
  /** Current goal/target CCT value (Kelvin) */
  value: number;
  /** Optional current actual CCT for transition indicator (Kelvin) */
  currentValue?: number;
  /** Called when the user changes the CCT */
  onChange: (value: number) => void;
  /** Minimum CCT value (Kelvin) */
  min?: number;
  /** Maximum CCT value (Kelvin) */
  max?: number;
  /** Label to show above the slider */
  label?: string;
  /** Whether to show quick-set preset buttons */
  showPresets?: boolean;
  /** Size variant */
  size?: 'sm' | 'md';
  /** Whether this is disabled */
  disabled?: boolean;
}

/**
 * Reusable color temperature (CCT) slider with gradient background
 *
 * Shows a slider for setting CCT with:
 * - Gradient background from warm to cool
 * - Goal value (slider thumb position)
 * - Current value (green indicator line, optional)
 * - Quick-set preset buttons (optional)
 */
export function CCTSlider({
  value,
  currentValue,
  onChange,
  min = 2700,
  max = 6500,
  label = 'Color Temperature',
  showPresets = true,
  size = 'md',
  disabled = false,
}: CCTSliderProps) {
  const height = size === 'sm' ? 'h-1.5' : 'h-2';
  const thumbSize = size === 'sm' ? 'w-4 h-4' : 'w-5 h-5';
  const indicatorSize = size === 'sm' ? 'w-1 h-3' : 'w-1.5 h-4';

  // Calculate preset values: min, middle, max
  const presets = [min, Math.round((min + max) / 2), max];

  return (
    <div className={disabled ? 'opacity-50 pointer-events-none' : ''}>
      <div className="flex items-center justify-between mb-2">
        <label className={`${size === 'sm' ? 'text-xs' : 'text-sm'} text-[#a1a1a6]`}>{label}</label>
        <div className="flex items-center gap-2">
          <span className={`${size === 'sm' ? 'text-xs' : 'text-sm'} font-medium tabular-nums text-amber-400`} title="Goal">
            Goal: {value}K
          </span>
          {currentValue !== undefined && (
            <>
              <span className={`${size === 'sm' ? 'text-xs' : 'text-sm'} text-[#636366]`}>→</span>
              <span className={`${size === 'sm' ? 'text-xs' : 'text-sm'} font-medium tabular-nums text-green-400`} title="Current">
                Now: {currentValue}K
              </span>
            </>
          )}
        </div>
      </div>
      <div className={`relative ${height}`}>
        {/* Gradient background with optional current value indicator */}
        <div
          className={`absolute top-0 left-0 right-0 ${height} rounded-full pointer-events-none`}
          style={{
            background: `linear-gradient(to right, ${kelvinToColor(min)}, ${kelvinToColor(max)})`,
          }}
        >
          {currentValue !== undefined && (
            <div
              className={`absolute top-1/2 -translate-y-1/2 ${indicatorSize} bg-green-400 rounded-full shadow-lg transition-all duration-100`}
              style={{
                left: `${((currentValue - min) / (max - min)) * 100}%`,
              }}
              title={`Current: ${currentValue}K`}
            />
          )}
        </div>
        <input
          type="range"
          min={min}
          max={max}
          value={value}
          onChange={(e) => onChange(parseInt(e.target.value))}
          disabled={disabled}
          className={`absolute top-0 left-0 w-full ${height} bg-transparent rounded-full appearance-none cursor-pointer
            [&::-webkit-slider-runnable-track]:${height}
            [&::-webkit-slider-runnable-track]:rounded-full
            [&::-webkit-slider-runnable-track]:bg-transparent
            [&::-webkit-slider-thumb]:appearance-none
            [&::-webkit-slider-thumb]:${thumbSize}
            [&::-webkit-slider-thumb]:rounded-full
            [&::-webkit-slider-thumb]:bg-white
            [&::-webkit-slider-thumb]:border-2
            [&::-webkit-slider-thumb]:border-gray-600
            [&::-webkit-slider-thumb]:cursor-pointer
            [&::-webkit-slider-thumb]:shadow-[0_2px_8px_rgba(0,0,0,0.3)]`}
        />
      </div>
      {showPresets && (
        <div className="flex justify-between mt-2">
          {presets.map((preset) => (
            <button
              key={preset}
              onClick={() => onChange(preset)}
              disabled={disabled}
              className="px-3 py-1 text-xs font-medium rounded bg-[#2a2a2f] text-[#a1a1a6] hover:bg-[#3a3a3f] hover:text-white transition-colors disabled:opacity-50"
            >
              {preset}K
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default CCTSlider;
