'use client';

import { BRIGHTNESS_PRESETS } from '@/utils/lighting';

export interface BrightnessSliderProps {
  /** Current goal/target brightness value (0-100 percent) */
  value: number;
  /** Optional current actual brightness for transition indicator (0-100 percent) */
  currentValue?: number;
  /** Called when the user changes the brightness */
  onChange: (value: number) => void;
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
 * Reusable brightness slider with optional transition indicator
 *
 * Shows a slider for setting brightness with:
 * - Goal value (slider thumb position)
 * - Current value (green progress bar, optional)
 * - Quick-set preset buttons (optional)
 */
export function BrightnessSlider({
  value,
  currentValue,
  onChange,
  label = 'Brightness',
  showPresets = true,
  size = 'md',
  disabled = false,
}: BrightnessSliderProps) {
  const height = size === 'sm' ? 'h-1.5' : 'h-2';
  const thumbSize = size === 'sm' ? 'w-4 h-4' : 'w-5 h-5';

  return (
    <div className={disabled ? 'opacity-50 pointer-events-none' : ''}>
      <div className="flex items-center justify-between mb-2">
        <label className={`${size === 'sm' ? 'text-xs' : 'text-sm'} text-[#a1a1a6]`}>{label}</label>
        <div className="flex items-center gap-2">
          <span className={`${size === 'sm' ? 'text-xs' : 'text-sm'} font-medium tabular-nums text-amber-400`} title="Goal">
            Goal: {Math.round(value)}%
          </span>
          {currentValue !== undefined && (
            <>
              <span className={`${size === 'sm' ? 'text-xs' : 'text-sm'} text-[#636366]`}>→</span>
              <span className={`${size === 'sm' ? 'text-xs' : 'text-sm'} font-medium tabular-nums text-green-400`} title="Current">
                Now: {Math.round(currentValue)}%
              </span>
            </>
          )}
        </div>
      </div>
      <div className={`relative ${height}`}>
        {/* Background with optional current value indicator */}
        <div className={`absolute top-0 left-0 right-0 ${height} bg-[#2a2a2f] rounded-full pointer-events-none`}>
          {currentValue !== undefined && (
            <div
              className={`${height} bg-green-500/40 rounded-full transition-all duration-100`}
              style={{ width: `${currentValue}%` }}
              title={`Current: ${Math.round(currentValue)}%`}
            />
          )}
        </div>
        <input
          type="range"
          min="0"
          max="100"
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
            [&::-webkit-slider-thumb]:bg-amber-500
            [&::-webkit-slider-thumb]:cursor-pointer
            [&::-webkit-slider-thumb]:shadow-[0_2px_8px_rgba(0,0,0,0.3)]
            [&::-webkit-slider-thumb]:border-2
            [&::-webkit-slider-thumb]:border-amber-400`}
        />
      </div>
      {showPresets && (
        <div className="flex justify-between mt-2">
          {BRIGHTNESS_PRESETS.map((preset) => (
            <button
              key={preset}
              onClick={() => onChange(preset)}
              disabled={disabled}
              className="px-3 py-1 text-xs font-medium rounded bg-[#2a2a2f] text-[#a1a1a6] hover:bg-[#3a3a3f] hover:text-white transition-colors disabled:opacity-50"
            >
              {preset}%
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default BrightnessSlider;
