'use client';

import { BrightnessSlider } from './BrightnessSlider';
import { CCTSlider } from './CCTSlider';
import { FixtureType, isDimmable, supportsCct } from '@/utils/lighting';

export interface FixtureControlsProps {
  /** Fixture type to determine available controls */
  fixtureType?: FixtureType;
  /** Current goal brightness (0-100 percent) */
  brightness: number;
  /** Current actual brightness for transition indicator (0-100 percent) */
  currentBrightness?: number;
  /** Called when brightness changes */
  onBrightnessChange: (value: number) => void;
  /** Current goal CCT (Kelvin) */
  cct?: number;
  /** Current actual CCT for transition indicator (Kelvin) */
  currentCct?: number;
  /** Called when CCT changes */
  onCctChange?: (value: number) => void;
  /** Minimum CCT value (Kelvin) */
  cctMin?: number;
  /** Maximum CCT value (Kelvin) */
  cctMax?: number;
  /** Whether to show preset buttons */
  showPresets?: boolean;
  /** Size variant */
  size?: 'sm' | 'md';
  /** Whether controls are disabled */
  disabled?: boolean;
}

/**
 * Combined fixture controls component
 *
 * Automatically shows appropriate controls based on fixture type:
 * - Simple dimmable: Brightness only
 * - Tunable white: Brightness + CCT
 * - Non-dimmable: No controls (or on/off only)
 */
export function FixtureControls({
  fixtureType,
  brightness,
  currentBrightness,
  onBrightnessChange,
  cct = 2700,
  currentCct,
  onCctChange,
  cctMin = 2700,
  cctMax = 6500,
  showPresets = false,
  size = 'sm',
  disabled = false,
}: FixtureControlsProps) {
  const canDim = isDimmable(fixtureType);
  const canTuneCct = supportsCct(fixtureType);

  if (!canDim) {
    return (
      <div className="text-xs text-[#636366] italic">
        Non-dimmable fixture (on/off only)
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <BrightnessSlider
        value={brightness}
        currentValue={currentBrightness}
        onChange={onBrightnessChange}
        showPresets={showPresets}
        size={size}
        disabled={disabled}
      />
      {canTuneCct && onCctChange && (
        <CCTSlider
          value={cct}
          currentValue={currentCct}
          onChange={onCctChange}
          min={cctMin}
          max={cctMax}
          showPresets={showPresets}
          size={size}
          disabled={disabled}
        />
      )}
    </div>
  );
}

export default FixtureControls;
