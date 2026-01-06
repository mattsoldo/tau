/**
 * Shared lighting utilities and constants
 * Used across Test Controls, Scenes, and Dashboard pages
 */

export type FixtureType = 'simple_dimmable' | 'tunable_white' | 'dim_to_warm' | 'non_dimmable' | 'other';

/**
 * Convert color temperature in Kelvin to an RGB color string
 * Uses approximation algorithm for blackbody radiation
 */
export function kelvinToColor(kelvin: number): string {
  const clampedKelvin = Math.max(1000, Math.min(40000, kelvin));
  const temp = clampedKelvin / 100;
  let r: number, g: number, b: number;

  if (temp <= 66) {
    r = 255;
    if (temp <= 20) {
      g = Math.max(40, (temp - 10) * 9.7 + 56);
      b = 0;
    } else {
      g = 99.4708025861 * Math.log(temp) - 161.1195681661;
      b = temp - 10;
      b = 138.5177312231 * Math.log(b) - 305.0447927307;
    }
  } else {
    r = temp - 60;
    r = 329.698727446 * Math.pow(r, -0.1332047592);
    g = temp - 60;
    g = 288.1221695283 * Math.pow(g, -0.0755148492);
    b = 255;
  }

  r = Math.max(0, Math.min(255, r));
  g = Math.max(0, Math.min(255, g));
  b = Math.max(0, Math.min(255, b));

  return `rgb(${Math.round(r)}, ${Math.round(g)}, ${Math.round(b)})`;
}

/**
 * Labels and styling for fixture types
 */
export const fixtureTypeLabels: Record<FixtureType, { label: string; color: string }> = {
  simple_dimmable: { label: 'Dimmable', color: 'bg-blue-500/15 text-blue-400 border-blue-500/30' },
  tunable_white: { label: 'Tunable', color: 'bg-amber-500/15 text-amber-400 border-amber-500/30' },
  dim_to_warm: { label: 'Dim to Warm', color: 'bg-orange-500/15 text-orange-400 border-orange-500/30' },
  non_dimmable: { label: 'On/Off', color: 'bg-gray-500/15 text-gray-400 border-gray-500/30' },
  other: { label: 'Other', color: 'bg-purple-500/15 text-purple-400 border-purple-500/30' },
};

/**
 * Format remaining time from a Unix timestamp
 */
export function formatTimeRemaining(expiresAt: number): string {
  const now = Date.now() / 1000;
  const remaining = expiresAt - now;
  if (remaining <= 0) return 'Expiring...';
  const hours = Math.floor(remaining / 3600);
  const minutes = Math.floor((remaining % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

/**
 * Check if a fixture type supports CCT (color temperature) control
 */
export function supportsCct(fixtureType: FixtureType | undefined): boolean {
  return fixtureType === 'tunable_white';
}

/**
 * Check if a fixture type is dimmable
 */
export function isDimmable(fixtureType: FixtureType | undefined): boolean {
  return fixtureType !== 'non_dimmable';
}

/**
 * Common quick-set brightness values (as percentages)
 */
export const BRIGHTNESS_PRESETS = [0, 25, 50, 75, 100];

/**
 * Convert brightness from 0-1000 scale to 0-100 percentage
 */
export function brightnessToPercent(brightness: number): number {
  return brightness / 10;
}

/**
 * Convert brightness from 0-100 percentage to 0-1000 scale
 */
export function percentToBrightness(percent: number): number {
  return percent * 10;
}

/**
 * Convert brightness from 0-1000 scale to 0.0-1.0 API format
 */
export function brightnessToApi(brightness: number): number {
  return brightness / 1000;
}

/**
 * Convert brightness from 0.0-1.0 API format to 0-1000 scale
 */
export function apiBrightness(brightness: number): number {
  return brightness * 1000;
}
