'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import { filterMergedFixtures } from '@/utils/fixtures';

const API_URL = '';

// === Types ===

type FixtureType = 'simple_dimmable' | 'tunable_white' | 'dim_to_warm' | 'non_dimmable' | 'other';

interface FixtureModel {
  id: number;
  manufacturer: string;
  model: string;
  type: FixtureType;
  dmx_footprint: number;
  cct_min_kelvin: number;
  cct_max_kelvin: number;
}

interface Fixture {
  id: number;
  name: string;
  fixture_model_id: number;
  dmx_channel_start: number;
  secondary_dmx_channel: number | null;
}

interface FixtureState {
  fixture_id: number;
  goal_brightness: number;
  goal_cct: number;
  current_brightness: number;
  current_cct: number;
  is_on: boolean;
}

interface Group {
  id: number;
  name: string;
  description?: string;
  is_system?: boolean;
}

interface FixtureWithModel extends Fixture {
  model?: FixtureModel;
}

interface GroupWithFixtures extends Group {
  fixtures: FixtureWithModel[];
}

interface SceneValue {
  fixture_id: number;
  target_brightness: number | null;
  target_cct_kelvin: number | null;
}

interface Scene {
  id: number;
  name: string;
  scope_group_id?: number;
  values: SceneValue[];
}

type EditorMode = 'capture' | 'manual';

// === Helper Functions ===

const kelvinToColor = (kelvin: number): string => {
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
};

const typeLabels: Record<FixtureType, { label: string; color: string }> = {
  simple_dimmable: { label: 'Dimmable', color: 'bg-blue-500/15 text-blue-400 border-blue-500/30' },
  tunable_white: { label: 'Tunable', color: 'bg-amber-500/15 text-amber-400 border-amber-500/30' },
  dim_to_warm: { label: 'Dim to Warm', color: 'bg-orange-500/15 text-orange-400 border-orange-500/30' },
  non_dimmable: { label: 'On/Off', color: 'bg-gray-500/15 text-gray-400 border-gray-500/30' },
  other: { label: 'Other', color: 'bg-purple-500/15 text-purple-400 border-purple-500/30' },
};

export default function ScenesPage() {
  // Scene list state
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Editor state
  const [isEditing, setIsEditing] = useState(false);
  const [editingScene, setEditingScene] = useState<Scene | null>(null);
  const [sceneName, setSceneName] = useState('');
  const [editorMode, setEditorMode] = useState<EditorMode>('capture');

  // Fixture/Group data for editor
  const [fixtures, setFixtures] = useState<FixtureWithModel[]>([]);
  const [fixtureModels, setFixtureModels] = useState<FixtureModel[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [groupsWithFixtures, setGroupsWithFixtures] = useState<GroupWithFixtures[]>([]);

  // Editor values - maps fixture_id to values
  const [editorValues, setEditorValues] = useState<Map<number, { brightness: number; cct: number; included: boolean }>>(new Map());
  const [expandedGroups, setExpandedGroups] = useState<Set<number>>(new Set());

  // For live capture preview
  const [currentStates, setCurrentStates] = useState<Map<number, { brightness: number; cct: number }>>(new Map());

  // Fetch scenes
  const fetchScenes = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/scenes/`);
      if (!res.ok) throw new Error('Failed to fetch scenes');
      const data = await res.json();
      setScenes(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load scenes');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Fetch fixtures and groups for editor
  const fetchFixturesAndGroups = useCallback(async () => {
    try {
      const [fixturesRes, modelsRes, groupsRes] = await Promise.all([
        fetch(`${API_URL}/api/fixtures/`),
        fetch(`${API_URL}/api/fixtures/models`),
        fetch(`${API_URL}/api/groups/`),
      ]);

      if (!fixturesRes.ok || !modelsRes.ok || !groupsRes.ok) {
        throw new Error('Failed to fetch data');
      }

      const [fixturesData, modelsData, groupsData] = await Promise.all([
        fixturesRes.json(),
        modelsRes.json(),
        groupsRes.json(),
      ]);

      setFixtureModels(modelsData);
      setGroups(groupsData);

      // Filter out merged fixtures and add model info
      const visibleFixtures = filterMergedFixtures(fixturesData);
      const fixturesWithModels: FixtureWithModel[] = visibleFixtures.map((fixture: Fixture) => ({
        ...fixture,
        model: modelsData.find((m: FixtureModel) => m.id === fixture.fixture_model_id),
      }));
      setFixtures(fixturesWithModels);

      // Fetch fixtures for each group
      const groupsWithFixturesData: GroupWithFixtures[] = await Promise.all(
        groupsData.map(async (group: Group) => {
          try {
            const fixturesInGroupRes = await fetch(`${API_URL}/api/groups/${group.id}/fixtures`);
            if (fixturesInGroupRes.ok) {
              const fixtureIds: { id: number }[] = await fixturesInGroupRes.json();
              const groupFixtures = fixtureIds
                .map(f => fixturesWithModels.find(fw => fw.id === f.id))
                .filter((f): f is FixtureWithModel => f !== undefined);
              return { ...group, fixtures: groupFixtures };
            }
          } catch {
            // Ignore errors
          }
          return { ...group, fixtures: [] };
        })
      );

      // Sort groups: system groups first, then by name
      groupsWithFixturesData.sort((a, b) => {
        if (a.is_system && !b.is_system) return -1;
        if (!a.is_system && b.is_system) return 1;
        return a.name.localeCompare(b.name);
      });

      setGroupsWithFixtures(groupsWithFixturesData);
    } catch (err) {
      console.error('Failed to fetch fixtures/groups:', err);
    }
  }, []);

  // Fetch current fixture states for capture mode
  const fetchCurrentStates = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/scenes/current-state`);
      if (!res.ok) throw new Error('Failed to fetch current state');
      const data: SceneValue[] = await res.json();

      const statesMap = new Map<number, { brightness: number; cct: number }>();
      for (const state of data) {
        statesMap.set(state.fixture_id, {
          brightness: state.target_brightness ?? 0,
          cct: state.target_cct_kelvin ?? 2700,
        });
      }
      setCurrentStates(statesMap);

      // If in capture mode, also update editor values
      if (editorMode === 'capture') {
        setEditorValues(prev => {
          const newMap = new Map(prev);
          for (const [fixtureId, state] of statesMap) {
            const existing = newMap.get(fixtureId);
            if (existing) {
              newMap.set(fixtureId, { ...existing, brightness: state.brightness, cct: state.cct });
            }
          }
          return newMap;
        });
      }
    } catch (err) {
      console.error('Failed to fetch current states:', err);
    }
  }, [editorMode]);

  useEffect(() => {
    fetchScenes();
    fetchFixturesAndGroups();
  }, [fetchScenes, fetchFixturesAndGroups]);

  // Fetch current states periodically when editor is open in capture mode
  useEffect(() => {
    if (isEditing && editorMode === 'capture') {
      fetchCurrentStates();
      const interval = setInterval(fetchCurrentStates, 2000);
      return () => clearInterval(interval);
    }
  }, [isEditing, editorMode, fetchCurrentStates]);

  // Initialize editor values when opening editor
  const initializeEditorValues = useCallback((scene?: Scene) => {
    const newValues = new Map<number, { brightness: number; cct: number; included: boolean }>();

    for (const fixture of fixtures) {
      const defaultCct = fixture.model?.cct_min_kelvin ?? 2700;

      if (scene) {
        // Editing existing scene
        const sceneValue = scene.values.find(v => v.fixture_id === fixture.id);
        if (sceneValue) {
          newValues.set(fixture.id, {
            brightness: sceneValue.target_brightness ?? 0,
            cct: sceneValue.target_cct_kelvin ?? defaultCct,
            included: true,
          });
        } else {
          newValues.set(fixture.id, {
            brightness: 500, // 50% default
            cct: defaultCct,
            included: false,
          });
        }
      } else {
        // New scene - start with current state
        const currentState = currentStates.get(fixture.id);
        newValues.set(fixture.id, {
          brightness: currentState?.brightness ?? 500,
          cct: currentState?.cct ?? defaultCct,
          included: true, // Include all by default for new scenes
        });
      }
    }

    setEditorValues(newValues);
  }, [fixtures, currentStates]);

  // Open editor for new scene
  const handleNewScene = () => {
    setEditingScene(null);
    setSceneName('');
    setEditorMode('capture');
    fetchCurrentStates().then(() => {
      initializeEditorValues();
    });
    setIsEditing(true);
  };

  // Open editor for existing scene
  const handleEditScene = (scene: Scene) => {
    setEditingScene(scene);
    setSceneName(scene.name);
    setEditorMode('manual');
    initializeEditorValues(scene);
    setIsEditing(true);
  };

  // Close editor
  const handleCloseEditor = () => {
    setIsEditing(false);
    setEditingScene(null);
    setSceneName('');
    setEditorValues(new Map());
  };

  // Save scene
  const handleSaveScene = async () => {
    if (!sceneName.trim()) {
      alert('Please enter a scene name');
      return;
    }

    // Build values array from editor state
    const values: { fixture_id: number; target_brightness: number; target_cct_kelvin: number }[] = [];
    for (const [fixtureId, state] of editorValues) {
      if (state.included) {
        values.push({
          fixture_id: fixtureId,
          target_brightness: state.brightness,
          target_cct_kelvin: state.cct,
        });
      }
    }

    if (values.length === 0) {
      alert('Please include at least one fixture in the scene');
      return;
    }

    try {
      if (editingScene) {
        // Update existing scene
        await fetch(`${API_URL}/api/scenes/${editingScene.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: sceneName }),
        });
        await fetch(`${API_URL}/api/scenes/${editingScene.id}/values`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ values }),
        });
      } else {
        // Create new scene
        await fetch(`${API_URL}/api/scenes/with-values`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: sceneName, values }),
        });
      }

      handleCloseEditor();
      fetchScenes();
    } catch (err) {
      console.error('Failed to save scene:', err);
      alert('Failed to save scene');
    }
  };

  // Delete scene
  const handleDeleteScene = async (sceneId: number) => {
    if (!confirm('Are you sure you want to delete this scene?')) return;

    try {
      await fetch(`${API_URL}/api/scenes/${sceneId}`, { method: 'DELETE' });
      fetchScenes();
    } catch (err) {
      console.error('Failed to delete scene:', err);
    }
  };

  // Recall scene
  const handleRecallScene = async (sceneId: number) => {
    try {
      await fetch(`${API_URL}/api/scenes/recall`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scene_id: sceneId, fade_duration: 1.0 }),
      });
    } catch (err) {
      console.error('Failed to recall scene:', err);
    }
  };

  // Toggle group expansion
  const toggleGroup = (groupId: number) => {
    setExpandedGroups(prev => {
      const next = new Set(prev);
      if (next.has(groupId)) {
        next.delete(groupId);
      } else {
        next.add(groupId);
      }
      return next;
    });
  };

  // Update fixture value in editor
  const updateFixtureValue = (fixtureId: number, updates: Partial<{ brightness: number; cct: number; included: boolean }>) => {
    setEditorValues(prev => {
      const newMap = new Map(prev);
      const existing = newMap.get(fixtureId) || { brightness: 500, cct: 2700, included: true };
      newMap.set(fixtureId, { ...existing, ...updates });
      return newMap;
    });
  };

  // Toggle all fixtures in a group
  const toggleGroupFixtures = (group: GroupWithFixtures, included: boolean) => {
    setEditorValues(prev => {
      const newMap = new Map(prev);
      for (const fixture of group.fixtures) {
        const existing = newMap.get(fixture.id) || { brightness: 500, cct: 2700, included: true };
        newMap.set(fixture.id, { ...existing, included });
      }
      return newMap;
    });
  };

  // Set all fixtures in a group to same brightness
  const setGroupBrightness = (group: GroupWithFixtures, brightness: number) => {
    setEditorValues(prev => {
      const newMap = new Map(prev);
      for (const fixture of group.fixtures) {
        const existing = newMap.get(fixture.id) || { brightness: 500, cct: 2700, included: true };
        if (existing.included) {
          newMap.set(fixture.id, { ...existing, brightness });
        }
      }
      return newMap;
    });
  };

  // Set all fixtures in a group to same CCT
  const setGroupCct = (group: GroupWithFixtures, cct: number) => {
    setEditorValues(prev => {
      const newMap = new Map(prev);
      for (const fixture of group.fixtures) {
        const existing = newMap.get(fixture.id) || { brightness: 500, cct: 2700, included: true };
        if (existing.included && fixture.model?.type === 'tunable_white') {
          newMap.set(fixture.id, { ...existing, cct });
        }
      }
      return newMap;
    });
  };

  // Helper functions for editor
  const supportsCct = (fixture: FixtureWithModel): boolean => fixture.model?.type === 'tunable_white';
  const isDimmable = (fixture: FixtureWithModel): boolean => fixture.model?.type !== 'non_dimmable';

  const getGroupIncludedCount = (group: GroupWithFixtures): number => {
    return group.fixtures.filter(f => editorValues.get(f.id)?.included).length;
  };

  const getGroupAverageBrightness = (group: GroupWithFixtures): number => {
    const included = group.fixtures.filter(f => editorValues.get(f.id)?.included);
    if (included.length === 0) return 0;
    const total = included.reduce((sum, f) => sum + (editorValues.get(f.id)?.brightness ?? 0), 0);
    return total / included.length;
  };

  const getGroupAverageCct = (group: GroupWithFixtures): number | null => {
    const included = group.fixtures.filter(f => editorValues.get(f.id)?.included && f.model?.type === 'tunable_white');
    if (included.length === 0) return null;
    const total = included.reduce((sum, f) => sum + (editorValues.get(f.id)?.cct ?? 2700), 0);
    return Math.round(total / included.length);
  };

  const groupHasTunableFixtures = (group: GroupWithFixtures): boolean => {
    return group.fixtures.some(f => f.model?.type === 'tunable_white');
  };

  const getGroupCctRange = (group: GroupWithFixtures): { min: number; max: number } => {
    const tunableFixtures = group.fixtures.filter(f => f.model?.type === 'tunable_white');
    if (tunableFixtures.length === 0) return { min: 2700, max: 6500 };
    const min = Math.min(...tunableFixtures.map(f => f.model?.cct_min_kelvin ?? 2700));
    const max = Math.max(...tunableFixtures.map(f => f.model?.cct_max_kelvin ?? 6500));
    return { min, max };
  };

  // Switch editor mode
  const handleSwitchMode = (mode: EditorMode) => {
    setEditorMode(mode);
    if (mode === 'capture') {
      // Refresh from current state
      fetchCurrentStates().then(() => {
        setEditorValues(prev => {
          const newMap = new Map(prev);
          for (const [fixtureId, state] of currentStates) {
            const existing = newMap.get(fixtureId);
            if (existing) {
              newMap.set(fixtureId, { ...existing, brightness: state.brightness, cct: state.cct });
            }
          }
          return newMap;
        });
      });
    }
  };

  // Capture current state button
  const handleCaptureNow = () => {
    fetchCurrentStates().then(() => {
      setEditorValues(prev => {
        const newMap = new Map(prev);
        for (const [fixtureId, state] of currentStates) {
          const existing = newMap.get(fixtureId);
          if (existing && existing.included) {
            newMap.set(fixtureId, { ...existing, brightness: state.brightness, cct: state.cct });
          }
        }
        return newMap;
      });
    });
  };

  // === Render ===

  if (isEditing) {
    return (
      <div className="min-h-screen text-white flex">
        {/* Sidebar */}
        <aside className="w-72 bg-[#111113] border-r border-[#1f1f24] flex flex-col">
          <div className="p-4 border-b border-[#1f1f24]">
            <button
              onClick={handleCloseEditor}
              className="flex items-center gap-2 text-[#a1a1a6] hover:text-white transition-colors mb-4"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
              </svg>
              Back to Scenes
            </button>
            <h2 className="text-lg font-semibold">
              {editingScene ? 'Edit Scene' : 'Create Scene'}
            </h2>
          </div>

          <div className="p-4 border-b border-[#1f1f24]">
            <label className="block text-xs font-medium text-[#636366] uppercase tracking-wider mb-2">
              Scene Name
            </label>
            <input
              type="text"
              value={sceneName}
              onChange={(e) => setSceneName(e.target.value)}
              placeholder="Enter scene name..."
              className="w-full px-3 py-2 bg-[#1a1a1f] border border-[#2a2a2f] rounded-lg text-white placeholder-[#636366] focus:outline-none focus:border-amber-500"
            />
          </div>

          <div className="p-4 border-b border-[#1f1f24]">
            <label className="block text-xs font-medium text-[#636366] uppercase tracking-wider mb-3">
              Creation Mode
            </label>
            <div className="space-y-2">
              <button
                onClick={() => handleSwitchMode('capture')}
                className={`w-full px-4 py-3 rounded-lg text-left transition-all ${
                  editorMode === 'capture'
                    ? 'bg-amber-500/20 border border-amber-500/50 text-amber-400'
                    : 'bg-[#1a1a1f] border border-[#2a2a2f] text-[#a1a1a6] hover:border-[#3a3a3f]'
                }`}
              >
                <div className="flex items-center gap-3">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z" />
                    <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0zM18.75 10.5h.008v.008h-.008V10.5z" />
                  </svg>
                  <div>
                    <div className="font-medium">Capture Current</div>
                    <div className="text-xs opacity-70">Use live light values</div>
                  </div>
                </div>
              </button>
              <button
                onClick={() => handleSwitchMode('manual')}
                className={`w-full px-4 py-3 rounded-lg text-left transition-all ${
                  editorMode === 'manual'
                    ? 'bg-amber-500/20 border border-amber-500/50 text-amber-400'
                    : 'bg-[#1a1a1f] border border-[#2a2a2f] text-[#a1a1a6] hover:border-[#3a3a3f]'
                }`}
              >
                <div className="flex items-center gap-3">
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 6h9.75M10.5 6a1.5 1.5 0 11-3 0m3 0a1.5 1.5 0 10-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-9.75 0h9.75" />
                  </svg>
                  <div>
                    <div className="font-medium">Manual Setup</div>
                    <div className="text-xs opacity-70">Set values with sliders</div>
                  </div>
                </div>
              </button>
            </div>
          </div>

          {editorMode === 'capture' && (
            <div className="p-4 border-b border-[#1f1f24]">
              <button
                onClick={handleCaptureNow}
                className="w-full px-4 py-2.5 bg-blue-500 hover:bg-blue-600 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                </svg>
                Capture Now
              </button>
              <p className="text-xs text-[#636366] mt-2 text-center">
                Values update every 2 seconds
              </p>
            </div>
          )}

          <div className="p-4 border-b border-[#1f1f24]">
            <h3 className="text-xs font-medium text-[#636366] uppercase tracking-wider mb-3">Summary</h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-[#a1a1a6]">Fixtures Included</span>
                <span className="font-medium">
                  {[...editorValues.values()].filter(v => v.included).length}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#a1a1a6]">Fixtures Excluded</span>
                <span className="font-medium text-[#636366]">
                  {[...editorValues.values()].filter(v => !v.included).length}
                </span>
              </div>
            </div>
          </div>

          <div className="mt-auto p-4 border-t border-[#1f1f24]">
            <button
              onClick={handleSaveScene}
              className="w-full px-4 py-2.5 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors mb-2"
            >
              {editingScene ? 'Save Changes' : 'Create Scene'}
            </button>
            <button
              onClick={handleCloseEditor}
              className="w-full px-4 py-2.5 bg-[#2a2a2f] hover:bg-[#3a3a3f] text-white font-medium rounded-lg transition-colors"
            >
              Cancel
            </button>
          </div>
        </aside>

        {/* Main content - Editor */}
        <main className="flex-1 overflow-auto">
          <div className="p-8">
            <div className="mb-8">
              <h1 className="text-3xl font-bold">
                {editorMode === 'capture' ? 'Capture Scene' : 'Configure Scene'}
              </h1>
              <p className="text-[#636366] mt-1">
                {editorMode === 'capture'
                  ? 'Current light values will be used. Adjust the Test Controls page to change.'
                  : 'Use the sliders to set each fixture\'s brightness and color temperature.'
                }
              </p>
            </div>

            <div className="space-y-4">
              {groupsWithFixtures.map((group) => {
                const isExpanded = expandedGroups.has(group.id);
                const includedCount = getGroupIncludedCount(group);
                const avgBrightness = getGroupAverageBrightness(group);
                const avgCct = getGroupAverageCct(group);
                const { min: cctMin, max: cctMax } = getGroupCctRange(group);

                return (
                  <div
                    key={group.id}
                    className={`bg-[#1a1a1f] rounded-xl border transition-all ${
                      includedCount > 0 ? 'border-amber-500/30' : 'border-[#2a2a2f]'
                    }`}
                  >
                    {/* Group Header */}
                    <div className="p-5">
                      <div className="flex items-start justify-between mb-4">
                        <div className="flex items-center gap-3">
                          <button
                            onClick={() => toggleGroup(group.id)}
                            className={`w-10 h-10 rounded-lg flex items-center justify-center transition-all ${
                              includedCount > 0 ? 'bg-amber-500/20' : 'bg-[#2a2a2f]'
                            }`}
                          >
                            <svg
                              className={`w-5 h-5 transition-transform ${isExpanded ? 'rotate-90' : ''} ${
                                includedCount > 0 ? 'text-amber-400' : 'text-[#636366]'
                              }`}
                              fill="none"
                              stroke="currentColor"
                              strokeWidth="2"
                              viewBox="0 0 24 24"
                            >
                              <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                            </svg>
                          </button>
                          <div>
                            <div className="flex items-center gap-2">
                              <h3 className="font-semibold text-lg">{group.name}</h3>
                              {group.is_system && (
                                <span className="text-xs px-2 py-0.5 rounded-full bg-purple-500/15 text-purple-400 border border-purple-500/30">
                                  System
                                </span>
                              )}
                            </div>
                            <div className="flex items-center gap-3 mt-1 text-xs text-[#636366]">
                              <span>{group.fixtures.length} fixtures</span>
                              <span className={includedCount > 0 ? 'text-amber-400' : ''}>
                                {includedCount} included
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* Group include/exclude buttons */}
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => toggleGroupFixtures(group, true)}
                            className="px-3 py-1.5 text-xs font-medium rounded bg-green-500/15 text-green-400 hover:bg-green-500/25 transition-colors"
                          >
                            Include All
                          </button>
                          <button
                            onClick={() => toggleGroupFixtures(group, false)}
                            className="px-3 py-1.5 text-xs font-medium rounded bg-red-500/15 text-red-400 hover:bg-red-500/25 transition-colors"
                          >
                            Exclude All
                          </button>
                        </div>
                      </div>

                      {/* Group-level controls (only in manual mode and when fixtures are included) */}
                      {editorMode === 'manual' && includedCount > 0 && (
                        <>
                          {/* Group Brightness Slider */}
                          <div className="mb-4">
                            <div className="flex items-center justify-between mb-2">
                              <label className="text-sm text-[#a1a1a6]">Group Brightness</label>
                              <span className="text-sm font-medium tabular-nums text-amber-400">
                                {Math.round(avgBrightness / 10)}%
                              </span>
                            </div>
                            <input
                              type="range"
                              min="0"
                              max="1000"
                              value={avgBrightness}
                              onChange={(e) => setGroupBrightness(group, parseInt(e.target.value))}
                              className="w-full h-2 bg-[#2a2a2f] rounded-full appearance-none cursor-pointer
                                [&::-webkit-slider-thumb]:appearance-none
                                [&::-webkit-slider-thumb]:w-5
                                [&::-webkit-slider-thumb]:h-5
                                [&::-webkit-slider-thumb]:rounded-full
                                [&::-webkit-slider-thumb]:bg-amber-500
                                [&::-webkit-slider-thumb]:cursor-pointer
                                [&::-webkit-slider-thumb]:shadow-[0_2px_8px_rgba(0,0,0,0.3)]
                                [&::-webkit-slider-thumb]:border-2
                                [&::-webkit-slider-thumb]:border-amber-400"
                            />
                            <div className="flex justify-between mt-2">
                              {[0, 250, 500, 750, 1000].map((val) => (
                                <button
                                  key={val}
                                  onClick={() => setGroupBrightness(group, val)}
                                  className="px-3 py-1 text-xs font-medium rounded bg-[#2a2a2f] text-[#a1a1a6] hover:bg-[#3a3a3f] hover:text-white transition-colors"
                                >
                                  {val / 10}%
                                </button>
                              ))}
                            </div>
                          </div>

                          {/* Group CCT Slider */}
                          {groupHasTunableFixtures(group) && avgCct !== null && (
                            <div>
                              <div className="flex items-center justify-between mb-2">
                                <label className="text-sm text-[#a1a1a6]">Group Color Temperature</label>
                                <span className="text-sm font-medium tabular-nums" style={{ color: kelvinToColor(avgCct) }}>
                                  {avgCct}K
                                </span>
                              </div>
                              <div className="relative h-2">
                                <div
                                  className="absolute top-0 left-0 right-0 h-2 rounded-full pointer-events-none"
                                  style={{
                                    background: `linear-gradient(to right, ${kelvinToColor(cctMin)}, ${kelvinToColor(cctMax)})`,
                                  }}
                                />
                                <input
                                  type="range"
                                  min={cctMin}
                                  max={cctMax}
                                  value={avgCct}
                                  onChange={(e) => setGroupCct(group, parseInt(e.target.value))}
                                  className="relative w-full h-2 bg-transparent rounded-full appearance-none cursor-pointer
                                    [&::-webkit-slider-thumb]:appearance-none
                                    [&::-webkit-slider-thumb]:w-5
                                    [&::-webkit-slider-thumb]:h-5
                                    [&::-webkit-slider-thumb]:rounded-full
                                    [&::-webkit-slider-thumb]:bg-white
                                    [&::-webkit-slider-thumb]:border-2
                                    [&::-webkit-slider-thumb]:border-gray-600
                                    [&::-webkit-slider-thumb]:cursor-pointer
                                    [&::-webkit-slider-thumb]:shadow-[0_2px_8px_rgba(0,0,0,0.3)]"
                                />
                              </div>
                              <div className="flex justify-between mt-2">
                                {[cctMin, Math.round((cctMin + cctMax) / 2), cctMax].map((val) => (
                                  <button
                                    key={val}
                                    onClick={() => setGroupCct(group, val)}
                                    className="px-3 py-1 text-xs font-medium rounded bg-[#2a2a2f] text-[#a1a1a6] hover:bg-[#3a3a3f] hover:text-white transition-colors"
                                  >
                                    {val}K
                                  </button>
                                ))}
                              </div>
                            </div>
                          )}
                        </>
                      )}

                      {/* Capture mode preview */}
                      {editorMode === 'capture' && includedCount > 0 && (
                        <div className="bg-[#0f0f11] rounded-lg p-3 border border-[#2a2a2f]">
                          <div className="text-xs text-[#636366] mb-2">Current Values Preview</div>
                          <div className="flex items-center gap-4">
                            <div>
                              <span className="text-xs text-[#a1a1a6]">Avg Brightness:</span>
                              <span className="ml-2 text-sm font-medium text-amber-400">
                                {Math.round(avgBrightness / 10)}%
                              </span>
                            </div>
                            {avgCct !== null && (
                              <div>
                                <span className="text-xs text-[#a1a1a6]">Avg CCT:</span>
                                <span className="ml-2 text-sm font-medium" style={{ color: kelvinToColor(avgCct) }}>
                                  {avgCct}K
                                </span>
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Expanded Fixtures */}
                    {isExpanded && group.fixtures.length > 0 && (
                      <div className="border-t border-[#2a2a2f] p-5 pt-4">
                        <div className="text-xs font-medium text-[#636366] uppercase tracking-wider mb-3">
                          Fixtures in Group
                        </div>
                        <div className="space-y-3">
                          {group.fixtures.map((fixture) => {
                            const fixtureValue = editorValues.get(fixture.id) || { brightness: 500, cct: 2700, included: true };
                            const isIncluded = fixtureValue.included;
                            const canDim = isDimmable(fixture);
                            const canTuneCct = supportsCct(fixture);
                            const cctMin = fixture.model?.cct_min_kelvin ?? 2700;
                            const cctMax = fixture.model?.cct_max_kelvin ?? 6500;

                            return (
                              <div
                                key={fixture.id}
                                className={`bg-[#0f0f11] rounded-lg p-4 border transition-all ${
                                  isIncluded ? 'border-amber-500/40' : 'border-[#2a2a2f] opacity-50'
                                }`}
                              >
                                <div className="flex items-start justify-between mb-3">
                                  <div className="flex items-center gap-3">
                                    <button
                                      onClick={() => updateFixtureValue(fixture.id, { included: !isIncluded })}
                                      className={`w-8 h-8 rounded-lg flex items-center justify-center transition-all ${
                                        isIncluded ? 'bg-amber-500' : 'bg-[#2a2a2f]'
                                      }`}
                                    >
                                      {isIncluded ? (
                                        <svg className="w-4 h-4 text-black" fill="none" stroke="currentColor" strokeWidth="3" viewBox="0 0 24 24">
                                          <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                                        </svg>
                                      ) : (
                                        <svg className="w-4 h-4 text-[#636366]" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                                          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                                        </svg>
                                      )}
                                    </button>
                                    <div>
                                      <div className="flex items-center gap-2">
                                        <span className="font-medium">{fixture.name}</span>
                                        {fixture.model && (
                                          <span className={`text-xs px-1.5 py-0.5 rounded border ${typeLabels[fixture.model.type].color}`}>
                                            {typeLabels[fixture.model.type].label}
                                          </span>
                                        )}
                                      </div>
                                      <span className="text-xs text-[#636366]">DMX {fixture.dmx_channel_start}</span>
                                    </div>
                                  </div>

                                  {/* Value preview */}
                                  <div className="text-right">
                                    <div className="text-sm font-medium tabular-nums text-amber-400">
                                      {Math.round(fixtureValue.brightness / 10)}%
                                    </div>
                                    {canTuneCct && (
                                      <div className="text-xs" style={{ color: kelvinToColor(fixtureValue.cct) }}>
                                        {fixtureValue.cct}K
                                      </div>
                                    )}
                                  </div>
                                </div>

                                {/* Fixture Controls (only in manual mode and when included) */}
                                {editorMode === 'manual' && isIncluded && (
                                  <div className="space-y-3">
                                    {canDim && (
                                      <div>
                                        <div className="flex items-center justify-between mb-1">
                                          <label className="text-xs text-[#a1a1a6]">Brightness</label>
                                          <span className="text-xs font-medium tabular-nums text-amber-400">
                                            {Math.round(fixtureValue.brightness / 10)}%
                                          </span>
                                        </div>
                                        <input
                                          type="range"
                                          min="0"
                                          max="1000"
                                          value={fixtureValue.brightness}
                                          onChange={(e) => updateFixtureValue(fixture.id, { brightness: parseInt(e.target.value) })}
                                          className="w-full h-1.5 bg-[#2a2a2f] rounded-full appearance-none cursor-pointer
                                            [&::-webkit-slider-thumb]:appearance-none
                                            [&::-webkit-slider-thumb]:w-4
                                            [&::-webkit-slider-thumb]:h-4
                                            [&::-webkit-slider-thumb]:rounded-full
                                            [&::-webkit-slider-thumb]:bg-amber-500
                                            [&::-webkit-slider-thumb]:cursor-pointer
                                            [&::-webkit-slider-thumb]:shadow-[0_2px_6px_rgba(0,0,0,0.3)]
                                            [&::-webkit-slider-thumb]:border-2
                                            [&::-webkit-slider-thumb]:border-amber-400"
                                        />
                                      </div>
                                    )}

                                    {canTuneCct && (
                                      <div>
                                        <div className="flex items-center justify-between mb-1">
                                          <label className="text-xs text-[#a1a1a6]">Color Temperature</label>
                                          <span className="text-xs font-medium tabular-nums" style={{ color: kelvinToColor(fixtureValue.cct) }}>
                                            {fixtureValue.cct}K
                                          </span>
                                        </div>
                                        <div className="relative h-1.5">
                                          <div
                                            className="absolute top-0 left-0 right-0 h-1.5 rounded-full pointer-events-none"
                                            style={{
                                              background: `linear-gradient(to right, ${kelvinToColor(cctMin)}, ${kelvinToColor(cctMax)})`,
                                            }}
                                          />
                                          <input
                                            type="range"
                                            min={cctMin}
                                            max={cctMax}
                                            value={fixtureValue.cct}
                                            onChange={(e) => updateFixtureValue(fixture.id, { cct: parseInt(e.target.value) })}
                                            className="relative w-full h-1.5 bg-transparent rounded-full appearance-none cursor-pointer
                                              [&::-webkit-slider-thumb]:appearance-none
                                              [&::-webkit-slider-thumb]:w-4
                                              [&::-webkit-slider-thumb]:h-4
                                              [&::-webkit-slider-thumb]:rounded-full
                                              [&::-webkit-slider-thumb]:bg-white
                                              [&::-webkit-slider-thumb]:border-2
                                              [&::-webkit-slider-thumb]:border-gray-600
                                              [&::-webkit-slider-thumb]:cursor-pointer
                                              [&::-webkit-slider-thumb]:shadow-[0_2px_6px_rgba(0,0,0,0.3)]"
                                          />
                                        </div>
                                      </div>
                                    )}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </main>
      </div>
    );
  }

  // Scene List View
  return (
    <div className="min-h-screen text-white flex">
      {/* Sidebar */}
      <aside className="w-64 bg-[#111113] border-r border-[#1f1f24] flex flex-col">
        <div className="p-4 border-b border-[#1f1f24]">
          <h3 className="text-xs font-medium text-[#636366] uppercase tracking-wider mb-3">Actions</h3>
          <button
            onClick={handleNewScene}
            className="w-full px-4 py-2.5 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            New Scene
          </button>
        </div>

        <div className="p-4 border-b border-[#1f1f24]">
          <h3 className="text-xs font-medium text-[#636366] uppercase tracking-wider mb-3">Status</h3>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-[#a1a1a6]">Total Scenes</span>
              <span className="font-medium">{scenes.length}</span>
            </div>
          </div>
        </div>

        <div className="p-4">
          <h3 className="text-xs font-medium text-[#636366] uppercase tracking-wider mb-3">Navigation</h3>
          <div className="space-y-1">
            <Link
              href="/test"
              className="flex items-center gap-2 px-3 py-2 rounded-lg text-[#a1a1a6] hover:text-white hover:bg-[#1a1a1f] transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 6h9.75M10.5 6a1.5 1.5 0 11-3 0m3 0a1.5 1.5 0 10-3 0M3.75 6H7.5m3 12h9.75m-9.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-3.75 0H7.5m9-6h3.75m-3.75 0a1.5 1.5 0 01-3 0m3 0a1.5 1.5 0 00-3 0m-9.75 0h9.75" />
              </svg>
              Test Controls
            </Link>
            <Link
              href="/config/fixtures"
              className="flex items-center gap-2 px-3 py-2 rounded-lg text-[#a1a1a6] hover:text-white hover:bg-[#1a1a1f] transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 18v-5.25m0 0a6.01 6.01 0 001.5-.189m-1.5.189a6.01 6.01 0 01-1.5-.189m3.75 7.478a12.06 12.06 0 01-4.5 0m3.75 2.383a14.406 14.406 0 01-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 10-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" />
              </svg>
              Fixtures
            </Link>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <div className="p-8">
          <div className="mb-8">
            <h1 className="text-3xl font-bold">Scenes</h1>
            <p className="text-[#636366] mt-1">Create and manage lighting presets</p>
          </div>

          {error && (
            <div className="mb-6 px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
              {error}
            </div>
          )}

          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin"></div>
            </div>
          ) : scenes.length === 0 ? (
            <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] p-12 text-center">
              <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-[#2a2a2f] flex items-center justify-center">
                <svg className="w-8 h-8 text-[#636366]" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909m-18 3.75h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.5-11.25h.008v.008h-.008V8.25zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0z" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold mb-2">No Scenes Yet</h3>
              <p className="text-[#636366] mb-4">Create your first scene to save a lighting preset.</p>
              <button
                onClick={handleNewScene}
                className="inline-flex items-center gap-2 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                </svg>
                Create Scene
              </button>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {scenes.map((scene) => (
                <div
                  key={scene.id}
                  className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] p-5 hover:border-[#3a3a3f] transition-all group"
                >
                  <div className="flex items-start justify-between mb-4">
                    <div>
                      <h3 className="font-semibold text-lg">{scene.name}</h3>
                      <p className="text-xs text-[#636366] mt-1">
                        {scene.values.length} fixture{scene.values.length !== 1 ? 's' : ''}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={() => handleEditScene(scene)}
                        className="p-2 rounded-lg bg-[#2a2a2f] hover:bg-[#3a3a3f] transition-colors"
                        title="Edit scene"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
                        </svg>
                      </button>
                      <button
                        onClick={() => handleDeleteScene(scene.id)}
                        className="p-2 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-red-400 transition-colors"
                        title="Delete scene"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                        </svg>
                      </button>
                    </div>
                  </div>

                  {/* Preview of fixture values */}
                  {scene.values.length > 0 && (
                    <div className="flex flex-wrap gap-1 mb-4">
                      {scene.values.slice(0, 5).map((value) => (
                        <div
                          key={value.fixture_id}
                          className="w-6 h-6 rounded"
                          style={{
                            backgroundColor: value.target_cct_kelvin
                              ? kelvinToColor(value.target_cct_kelvin)
                              : '#ffa500',
                            opacity: ((value.target_brightness ?? 0) / 1000) * 0.8 + 0.2,
                          }}
                          title={`Brightness: ${Math.round((value.target_brightness ?? 0) / 10)}%${
                            value.target_cct_kelvin ? `, CCT: ${value.target_cct_kelvin}K` : ''
                          }`}
                        />
                      ))}
                      {scene.values.length > 5 && (
                        <div className="w-6 h-6 rounded bg-[#2a2a2f] flex items-center justify-center text-xs text-[#636366]">
                          +{scene.values.length - 5}
                        </div>
                      )}
                    </div>
                  )}

                  <button
                    onClick={() => handleRecallScene(scene.id)}
                    className="w-full px-4 py-2.5 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
                  >
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.985V5.653z" />
                    </svg>
                    Activate Scene
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
