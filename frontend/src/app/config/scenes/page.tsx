'use client';

import { useCallback, useEffect, useMemo, useState, type Dispatch, type SetStateAction } from 'react';
import { API_URL } from '@/utils/api';

interface SceneValue {
  fixture_id: number;
  target_brightness?: number;
  target_cct_kelvin?: number;
}

interface Scene {
  id: number;
  name: string;
  scope_group_id: number | null;
  values?: SceneValue[];
}

interface Group {
  id: number;
  name: string;
}

interface Fixture {
  id: number;
  name: string;
  dmx_channel_start: number;
}

interface SceneFormData {
  name: string;
  scope_group_id: string;
}

const emptyFormData: SceneFormData = {
  name: '',
  scope_group_id: '',
};

export default function ScenesPage() {
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [fixtures, setFixtures] = useState<Fixture[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [formData, setFormData] = useState<SceneFormData>(emptyFormData);
  const [includeGroupIds, setIncludeGroupIds] = useState<Set<number>>(new Set());
  const [excludeGroupIds, setExcludeGroupIds] = useState<Set<number>>(new Set());
  const [includeFixtureIds, setIncludeFixtureIds] = useState<Set<number>>(new Set());
  const [excludeFixtureIds, setExcludeFixtureIds] = useState<Set<number>>(new Set());
  const [isSaving, setIsSaving] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);

  const groupNameById = useMemo(() => {
    return groups.reduce((acc, group) => {
      acc[group.id] = group.name;
      return acc;
    }, {} as Record<number, string>);
  }, [groups]);

  const fetchData = useCallback(async () => {
    try {
      const [scenesRes, groupsRes, fixturesRes] = await Promise.all([
        fetch(`${API_URL}/api/scenes/`),
        fetch(`${API_URL}/api/groups/`),
        fetch(`${API_URL}/api/fixtures/`),
      ]);

      if (!scenesRes.ok) throw new Error('Failed to fetch scenes');
      if (!groupsRes.ok) throw new Error('Failed to fetch groups');
      if (!fixturesRes.ok) throw new Error('Failed to fetch fixtures');

      const [scenesData, groupsData, fixturesData] = await Promise.all([
        scenesRes.json(),
        groupsRes.json(),
        fixturesRes.json(),
      ]);

      setScenes(scenesData);
      setGroups(groupsData);
      setFixtures(fixturesData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const resetForm = () => {
    setFormData(emptyFormData);
    setIncludeGroupIds(new Set());
    setExcludeGroupIds(new Set());
    setIncludeFixtureIds(new Set());
    setExcludeFixtureIds(new Set());
  };

  const toggleSelection = (
    id: number,
    setter: Dispatch<SetStateAction<Set<number>>>
  ) => {
    setter((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleCaptureScene = async () => {
    if (!formData.name.trim()) {
      setError('Scene name is required');
      return;
    }

    setIsSaving(true);
    setError(null);

    try {
      const payload: Record<string, unknown> = {
        name: formData.name.trim(),
        scope_group_id: formData.scope_group_id ? parseInt(formData.scope_group_id) : null,
      };

      if (includeGroupIds.size > 0) {
        payload.include_group_ids = Array.from(includeGroupIds);
      }
      if (excludeGroupIds.size > 0) {
        payload.exclude_group_ids = Array.from(excludeGroupIds);
      }
      if (includeFixtureIds.size > 0) {
        payload.fixture_ids = Array.from(includeFixtureIds);
      }
      if (excludeFixtureIds.size > 0) {
        payload.exclude_fixture_ids = Array.from(excludeFixtureIds);
      }

      const response = await fetch(`${API_URL}/api/scenes/capture`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to capture scene');
      }

      setIsModalOpen(false);
      resetForm();
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to capture scene');
    } finally {
      setIsSaving(false);
    }
  };

  const handleRecall = async (sceneId: number) => {
    try {
      const response = await fetch(`${API_URL}/api/scenes/recall`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scene_id: sceneId }),
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to recall scene');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to recall scene');
    }
  };

  const handleDelete = async (sceneId: number) => {
    try {
      const response = await fetch(`${API_URL}/api/scenes/${sceneId}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to delete scene');
      }

      setDeleteConfirm(null);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete scene');
    }
  };

  if (isLoading) {
    return (
      <div className="p-8">
        <div className="text-[#636366]">Loading scenes...</div>
      </div>
    );
  }

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold">Scenes</h1>
          <p className="text-[#636366] mt-1">Capture and recall lighting presets</p>
        </div>
        <button
          onClick={() => {
            resetForm();
            setIsModalOpen(true);
          }}
          className="flex items-center gap-2 px-4 py-2.5 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          Capture Scene
        </button>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="mb-6 px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {scenes.length === 0 ? (
        <div className="bg-[#161619] border border-[#2a2a2f] rounded-xl p-8 text-center">
          <h3 className="text-lg font-medium mb-2">No scenes yet</h3>
          <p className="text-[#636366] mb-4">Capture the current lighting state to create your first scene.</p>
          <button
            onClick={() => {
              resetForm();
              setIsModalOpen(true);
            }}
            className="inline-flex items-center gap-2 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors"
          >
            Capture Scene
          </button>
        </div>
      ) : (
        <div className="bg-[#161619] border border-[#2a2a2f] rounded-xl overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[#2a2a2f]">
                <th className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Name</th>
                <th className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Scope</th>
                <th className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Fixtures</th>
                <th className="px-6 py-4 text-right text-xs font-medium text-[#636366] uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#2a2a2f]">
              {scenes.map((scene) => (
                <tr key={scene.id} className="hover:bg-white/[0.02] transition-colors">
                  <td className="px-6 py-4">
                    <div className="font-medium">{scene.name}</div>
                  </td>
                  <td className="px-6 py-4">
                    <span className="text-sm text-[#a1a1a6]">
                      {scene.scope_group_id ? groupNameById[scene.scope_group_id] || `Group ${scene.scope_group_id}` : 'Global'}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <span className="text-sm text-[#a1a1a6]">{scene.values?.length || 0}</span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => handleRecall(scene.id)}
                        className="px-3 py-1.5 text-xs bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 rounded-lg transition-colors"
                      >
                        Recall
                      </button>
                      {deleteConfirm === scene.id ? (
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleDelete(scene.id)}
                            className="px-2 py-1 text-xs bg-red-500/20 text-red-400 hover:bg-red-500/30 rounded transition-colors"
                          >
                            Confirm
                          </button>
                          <button
                            onClick={() => setDeleteConfirm(null)}
                            className="px-2 py-1 text-xs bg-white/10 text-[#a1a1a6] hover:bg-white/20 rounded transition-colors"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setDeleteConfirm(scene.id)}
                          className="p-2 text-[#636366] hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                          </svg>
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Capture Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-[#161619] rounded-xl border border-[#2a2a2f] w-full max-w-3xl mx-4 max-h-[90vh] overflow-hidden">
            <div className="px-6 py-4 border-b border-[#2a2a2f]">
              <h2 className="text-lg font-semibold">Capture Scene</h2>
              <p className="text-sm text-[#636366]">Snapshot the current lighting state.</p>
            </div>

            <div className="p-6 space-y-6 overflow-y-auto max-h-[70vh]">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Scene Name</label>
                  <input
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="e.g., Movie Night"
                    className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white placeholder:text-[#636366] focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Scope Group (Optional)</label>
                  <select
                    value={formData.scope_group_id}
                    onChange={(e) => setFormData({ ...formData, scope_group_id: e.target.value })}
                    className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                  >
                    <option value="">Global</option>
                    {groups.map((group) => (
                      <option key={group.id} value={group.id}>
                        {group.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-6">
                <div className="space-y-4">
                  <div>
                    <h3 className="text-sm font-medium text-white mb-2">Include Groups</h3>
                    <p className="text-xs text-[#636366] mb-2">If empty, all fixtures are included.</p>
                    {groups.length === 0 ? (
                      <p className="text-xs text-amber-400">No groups available.</p>
                    ) : (
                      <div className="space-y-2">
                        {groups.map((group) => (
                          <label
                            key={`include-group-${group.id}`}
                            className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer border transition-colors ${
                              includeGroupIds.has(group.id)
                                ? 'bg-amber-500/10 border-amber-500/30'
                                : 'bg-[#111113] border-[#2a2a2f] hover:border-[#3a3a3f]'
                            }`}
                          >
                            <input
                              type="checkbox"
                              checked={includeGroupIds.has(group.id)}
                              onChange={() => toggleSelection(group.id, setIncludeGroupIds)}
                              className="w-4 h-4 rounded border-[#3a3a3f] bg-[#111113] text-amber-500 focus:ring-amber-500/30 focus:ring-offset-0"
                            />
                            <span className="text-sm">{group.name}</span>
                          </label>
                        ))}
                      </div>
                    )}
                  </div>

                  <div>
                    <h3 className="text-sm font-medium text-white mb-2">Exclude Groups</h3>
                    <p className="text-xs text-[#636366] mb-2">Excluded groups override included selections.</p>
                    {groups.length === 0 ? (
                      <p className="text-xs text-amber-400">No groups available.</p>
                    ) : (
                      <div className="space-y-2">
                        {groups.map((group) => (
                          <label
                            key={`exclude-group-${group.id}`}
                            className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer border transition-colors ${
                              excludeGroupIds.has(group.id)
                                ? 'bg-red-500/10 border-red-500/30'
                                : 'bg-[#111113] border-[#2a2a2f] hover:border-[#3a3a3f]'
                            }`}
                          >
                            <input
                              type="checkbox"
                              checked={excludeGroupIds.has(group.id)}
                              onChange={() => toggleSelection(group.id, setExcludeGroupIds)}
                              className="w-4 h-4 rounded border-[#3a3a3f] bg-[#111113] text-red-400 focus:ring-red-400/30 focus:ring-offset-0"
                            />
                            <span className="text-sm">{group.name}</span>
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                <div className="space-y-4">
                  <div>
                    <h3 className="text-sm font-medium text-white mb-2">Include Fixtures</h3>
                    <p className="text-xs text-[#636366] mb-2">Add specific fixtures even if no groups are selected.</p>
                    {fixtures.length === 0 ? (
                      <p className="text-xs text-amber-400">No fixtures available.</p>
                    ) : (
                      <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                        {fixtures.map((fixture) => (
                          <label
                            key={`include-fixture-${fixture.id}`}
                            className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer border transition-colors ${
                              includeFixtureIds.has(fixture.id)
                                ? 'bg-amber-500/10 border-amber-500/30'
                                : 'bg-[#111113] border-[#2a2a2f] hover:border-[#3a3a3f]'
                            }`}
                          >
                            <input
                              type="checkbox"
                              checked={includeFixtureIds.has(fixture.id)}
                              onChange={() => toggleSelection(fixture.id, setIncludeFixtureIds)}
                              className="w-4 h-4 rounded border-[#3a3a3f] bg-[#111113] text-amber-500 focus:ring-amber-500/30 focus:ring-offset-0"
                            />
                            <div className="flex-1">
                              <div className="text-sm">{fixture.name}</div>
                              <div className="text-xs text-[#636366]">DMX {fixture.dmx_channel_start}</div>
                            </div>
                          </label>
                        ))}
                      </div>
                    )}
                  </div>

                  <div>
                    <h3 className="text-sm font-medium text-white mb-2">Exclude Fixtures</h3>
                    <p className="text-xs text-[#636366] mb-2">Excluded fixtures are never affected by the scene.</p>
                    {fixtures.length === 0 ? (
                      <p className="text-xs text-amber-400">No fixtures available.</p>
                    ) : (
                      <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                        {fixtures.map((fixture) => (
                          <label
                            key={`exclude-fixture-${fixture.id}`}
                            className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer border transition-colors ${
                              excludeFixtureIds.has(fixture.id)
                                ? 'bg-red-500/10 border-red-500/30'
                                : 'bg-[#111113] border-[#2a2a2f] hover:border-[#3a3a3f]'
                            }`}
                          >
                            <input
                              type="checkbox"
                              checked={excludeFixtureIds.has(fixture.id)}
                              onChange={() => toggleSelection(fixture.id, setExcludeFixtureIds)}
                              className="w-4 h-4 rounded border-[#3a3a3f] bg-[#111113] text-red-400 focus:ring-red-400/30 focus:ring-offset-0"
                            />
                            <div className="flex-1">
                              <div className="text-sm">{fixture.name}</div>
                              <div className="text-xs text-[#636366]">DMX {fixture.dmx_channel_start}</div>
                            </div>
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-[#2a2a2f] bg-[#161619]">
              <button
                onClick={() => {
                  setIsModalOpen(false);
                  resetForm();
                }}
                className="px-4 py-2.5 text-[#a1a1a6] hover:text-white hover:bg-white/10 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCaptureScene}
                disabled={isSaving}
                className="px-4 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-500/50 disabled:cursor-not-allowed text-black font-medium rounded-lg transition-colors"
              >
                {isSaving ? 'Capturing...' : 'Capture Scene'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
