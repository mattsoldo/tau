/**
 * Fixture utility functions for handling merged fixtures and common operations
 */

export interface Fixture {
  id: number;
  name: string;
  fixture_model_id: number;
  dmx_channel_start: number;
  secondary_dmx_channel: number | null;
}

/**
 * Filter out fixtures that have been merged into other fixtures.
 *
 * When tunable white fixtures use two DMX channels, they create two fixture records:
 * 1. A "primary" fixture with both dmx_channel_start and secondary_dmx_channel set
 * 2. A "secondary" fixture whose dmx_channel_start matches the primary's secondary_dmx_channel
 *
 * This function filters out the secondary fixtures to prevent showing duplicates in the UI.
 *
 * @param fixtures - Array of all fixtures from the API
 * @returns Array of fixtures with merged secondaries removed
 *
 * @example
 * const allFixtures = await fetch('/api/fixtures/').then(r => r.json());
 * const visibleFixtures = filterMergedFixtures(allFixtures);
 * // visibleFixtures now contains only primary fixtures (standalone + merged)
 */
export function filterMergedFixtures<T extends Fixture>(fixtures: T[]): T[] {
  // Build a set of all DMX channels that are "secondary" to other fixtures
  const mergedChannels = new Set(
    fixtures
      .filter(f => f.secondary_dmx_channel !== null)
      .map(f => f.secondary_dmx_channel)
  );

  // Filter out any fixture whose start channel is in that set
  return fixtures.filter(f => !mergedChannels.has(f.dmx_channel_start));
}

/**
 * Check if a fixture is a merged (multi-channel) fixture
 *
 * @param fixture - The fixture to check
 * @returns true if the fixture has a secondary DMX channel (is merged)
 */
export function isMergedFixture(fixture: Fixture): boolean {
  return fixture.secondary_dmx_channel !== null;
}

/**
 * Get the DMX channel range for a fixture as a string
 *
 * @param fixture - The fixture to get the channel range for
 * @returns String representation like "10" for single channel or "10+20" for merged
 */
export function getFixtureDMXRange(fixture: Fixture): string {
  if (fixture.secondary_dmx_channel) {
    return `${fixture.dmx_channel_start}+${fixture.secondary_dmx_channel}`;
  }
  return `${fixture.dmx_channel_start}`;
}
