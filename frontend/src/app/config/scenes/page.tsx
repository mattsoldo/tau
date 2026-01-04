'use client';

import { useState, useEffect, useCallback } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// === Types ===

interface SceneValue {
  fixture_id: number;
  target_brightness: number | null;
  target_cct_kelvin: number | null;
}

interface Scene {
  id: number;
  name: string;
  scope_group_id: number | null;
  values: SceneValue[];
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

interface FixtureState {
  fixture_id: number;
  goal_brightness: number;
  goal_cct: number;
  is_on: boolean;
}

interface CaptureFormData {
  name: string;
  scope_group_id: string;
  fixture_ids: number[];
}

const emptyCaptureFormData: CaptureFormData = {
  name: '',
  scope_group_id: '',
  fixture_ids: [],
};

export default function ScenesPage() {
  // Data state
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [fixtures, setFixtures] = useState<Fixture[]>([]);
  const [fixtureStates, setFixtureStates] = useState<Map<number, FixtureState>>(new Map());
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Capture modal state
  const [isCaptureModalOpen, setIsCaptureModalOpen] = useState(false);
  const [captureFormData, setCaptureFormData] = useState<CaptureFormData>(emptyCaptureFormData);
  const [isCapturing, setIsCapturing] = useState(false);

  // Edit modal state
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [editingScene, setEditingScene] = useState<Scene | null>(null);
  const [editName, setEditName] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  // Details modal state
  const [isDetailsModalOpen, setIsDetailsModalOpen] = useState(false);
  const [viewingScene, setViewingScene] = useState<Scene | null>(null);

  // Delete confirmation state
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);

  // Recall state
  const [recallingSceneId, setRecallingSceneId] = useState<number | null>(null);

  // Sort state
  type SortColumn = 'name' | 'fixtures' | 'scope';
  type SortDirection = 'asc' | 'desc';
  const [sortColumn, setSortColumn] = useState<SortColumn>('name');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');

  // Fetch all data
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

      // Fetch fixture states
      const statesMap = new Map<number, FixtureState>();
      await Promise.all(
        fixturesData.map(async (f: Fixture) => {
          try {
            const stateRes = await fetch(`${API_URL}/api/fixtures/${f.id}/state`);
            if (stateRes.ok) {
              const state = await stateRes.json();
              statesMap.set(f.id, state);
            }
          } catch {
            // Ignore individual state fetch errors
          }
        })
      );
      setFixtureStates(statesMap);

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

  // Auto-dismiss success message
  useEffect(() => {
    if (successMessage) {
      const timer = setTimeout(() => setSuccessMessage(null), 3000);
      return () => clearTimeout(timer);
    }
  }, [successMessage]);

  // Sort scenes
  const sortedScenes = [...scenes].sort((a, b) => {
    let comparison = 0;
    switch (sortColumn) {
      case 'name':
        comparison = a.name.localeCompare(b.name);
        break;
      case 'fixtures':
        comparison = a.values.length - b.values.length;
        break;
      case 'scope':
        const aScope = a.scope_group_id ? 1 : 0;
        const bScope = b.scope_group_id ? 1 : 0;
        comparison = aScope - bScope;
        break;
    }
    return sortDirection === 'asc' ? comparison : -comparison;
  });

  const handleSort = (column: SortColumn) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection('asc');
    }
  };

  const SortIndicator = ({ column }: { column: SortColumn }) => {
    if (sortColumn !== column) return null;
    return (
      <span className="ml-1 text-amber-400">
        {sortDirection === 'asc' ? '↑' : '↓'}
      </span>
    );
  };

  // Get group name by ID
  const getGroupName = (groupId: number | null): string => {
    if (!groupId) return 'Global';
    const group = groups.find(g => g.id === groupId);
    return group?.name || 'Unknown';
  };

  // Get fixture name by ID
  const getFixtureName = (fixtureId: number): string => {
    const fixture = fixtures.find(f => f.id === fixtureId);
    return fixture?.name || `Fixture ${fixtureId}`;
  };

  // Open capture modal
  const openCaptureModal = () => {
    setCaptureFormData({
      ...emptyCaptureFormData,
      fixture_ids: fixtures.map(f => f.id), // Select all by default
    });
    setIsCaptureModalOpen(true);
  };

  // Toggle fixture selection for capture
  const toggleFixtureForCapture = (fixtureId: number) => {
    setCaptureFormData(prev => {
      const newIds = prev.fixture_ids.includes(fixtureId)
        ? prev.fixture_ids.filter(id => id !== fixtureId)
        : [...prev.fixture_ids, fixtureId];
      return { ...prev, fixture_ids: newIds };
    });
  };

  // Select/deselect all fixtures
  const toggleAllFixtures = () => {
    setCaptureFormData(prev => {
      if (prev.fixture_ids.length === fixtures.length) {
        return { ...prev, fixture_ids: [] };
      } else {
        return { ...prev, fixture_ids: fixtures.map(f => f.id) };
      }
    });
  };

  // Handle capture scene
  const handleCaptureScene = async () => {
    if (!captureFormData.name.trim()) {
      setError('Scene name is required');
      return;
    }

    if (captureFormData.fixture_ids.length === 0) {
      setError('Please select at least one fixture');
      return;
    }

    setIsCapturing(true);
    try {
      const payload = {
        name: captureFormData.name.trim(),
        fixture_ids: captureFormData.fixture_ids,
        scope_group_id: captureFormData.scope_group_id
          ? parseInt(captureFormData.scope_group_id)
          : null,
      };

      const res = await fetch(`${API_URL}/api/scenes/capture`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to capture scene');
      }

      setIsCaptureModalOpen(false);
      setSuccessMessage('Scene captured successfully');
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to capture scene');
    } finally {
      setIsCapturing(false);
    }
  };

  // Open edit modal
  const openEditModal = (scene: Scene) => {
    setEditingScene(scene);
    setEditName(scene.name);
    setIsEditModalOpen(true);
  };

  // Handle save edit
  const handleSaveEdit = async () => {
    if (!editingScene || !editName.trim()) {
      setError('Scene name is required');
      return;
    }

    setIsSaving(true);
    try {
      const res = await fetch(`${API_URL}/api/scenes/${editingScene.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: editName.trim() }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to update scene');
      }

      setIsEditModalOpen(false);
      setSuccessMessage('Scene updated successfully');
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update scene');
    } finally {
      setIsSaving(false);
    }
  };

  // Open details modal
  const openDetailsModal = (scene: Scene) => {
    setViewingScene(scene);
    setIsDetailsModalOpen(true);
  };

  // Handle delete scene
  const handleDeleteScene = async (sceneId: number) => {
    try {
      const res = await fetch(`${API_URL}/api/scenes/${sceneId}`, {
        method: 'DELETE',
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to delete scene');
      }

      setDeleteConfirm(null);
      setSuccessMessage('Scene deleted successfully');
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete scene');
    }
  };

  // Handle recall scene
  const handleRecallScene = async (sceneId: number) => {
    setRecallingSceneId(sceneId);
    try {
      const res = await fetch(`${API_URL}/api/scenes/recall`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scene_id: sceneId, fade_duration: 0 }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to recall scene');
      }

      setSuccessMessage('Scene recalled successfully');
      // Refresh fixture states after recall
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to recall scene');
    } finally {
      setRecallingSceneId(null);
    }
  };

  // Format brightness value
  const formatBrightness = (value: number | null): string => {
    if (value === null) return '—';
    return `${Math.round(value / 10)}%`;
  };

  // Format CCT value
  const formatCCT = (value: number | null): string => {
    if (value === null) return '—';
    return `${value}K`;
  };

  // Kelvin to color for display
  const kelvinToColor = (kelvin: number): string => {
    const t = (kelvin - 2000) / 4500;
    const r = Math.round(255 * (1 - t * 0.3));
    const g = Math.round(200 + t * 55);
    const b = Math.round(150 + t * 105);
    return `rgb(${r}, ${g}, ${b})`;
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Scenes</h1>
          <p className="text-[#636366] mt-1">Save and recall lighting presets</p>
        </div>
        <button
          onClick={openCaptureModal}
          className="px-4 py-2.5 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors flex items-center gap-2"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0zM18.75 10.5h.008v.008h-.008V10.5z" />
          </svg>
          Capture Scene
        </button>
      </div>

      {/* Success Banner */}
      {successMessage && (
        <div className="px-4 py-3 bg-green-500/10 border border-green-500/30 rounded-lg text-green-400 text-sm flex items-center justify-between">
          <div className="flex items-center gap-2">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{successMessage}</span>
          </div>
          <button onClick={() => setSuccessMessage(null)} className="text-green-400 hover:text-green-300">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {/* Error Banner */}
      {error && (
        <div className="px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {/* Loading State */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin"></div>
        </div>
      ) : scenes.length === 0 ? (
        <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] p-12 text-center">
          <div className="w-16 h-16 mx-auto mb-4 text-[#636366]">
            <svg fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 01-1.125-1.125M3.375 19.5h1.5C5.496 19.5 6 18.996 6 18.375m-3.75 0V5.625m0 12.75v-1.5c0-.621.504-1.125 1.125-1.125m18.375 2.625V5.625m0 12.75c0 .621-.504 1.125-1.125 1.125m1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125m0 3.75h-1.5A1.125 1.125 0 0118 18.375M20.625 4.5H3.375m17.25 0c.621 0 1.125.504 1.125 1.125M20.625 4.5h-1.5C18.504 4.5 18 5.004 18 5.625m3.75 0v1.5c0 .621-.504 1.125-1.125 1.125M3.375 4.5c-.621 0-1.125.504-1.125 1.125M3.375 4.5h1.5C5.496 4.5 6 5.004 6 5.625m-3.75 0v1.5c0 .621.504 1.125 1.125 1.125m0 0h1.5m-1.5 0c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125m1.5-3.75C5.496 8.25 6 7.746 6 7.125v-1.5M4.875 8.25C5.496 8.25 6 8.754 6 9.375v1.5m0-5.25v5.25m0-5.25C6 5.004 6.504 4.5 7.125 4.5h9.75c.621 0 1.125.504 1.125 1.125m1.125 2.625h1.5m-1.5 0A1.125 1.125 0 0118 7.125v-1.5m1.125 2.625c-.621 0-1.125.504-1.125 1.125v1.5m2.625-2.625c.621 0 1.125.504 1.125 1.125v1.5c0 .621-.504 1.125-1.125 1.125M18 5.625v5.25M7.125 12h9.75m-9.75 0A1.125 1.125 0 016 10.875M7.125 12C6.504 12 6 12.504 6 13.125m0-2.25C6 11.496 5.496 12 4.875 12M18 10.875c0 .621-.504 1.125-1.125 1.125M18 10.875c0 .621.504 1.125 1.125 1.125m-2.25 0c.621 0 1.125.504 1.125 1.125m-12 5.25v-5.25m0 5.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125m-12 0v-1.5c0-.621-.504-1.125-1.125-1.125M18 18.375v-5.25m0 5.25v-1.5c0-.621.504-1.125 1.125-1.125M18 13.125v1.5c0 .621.504 1.125 1.125 1.125M18 13.125c0-.621.504-1.125 1.125-1.125M6 13.125v1.5c0 .621-.504 1.125-1.125 1.125M6 13.125C6 12.504 5.496 12 4.875 12m-1.5 0h1.5m14.25 0h1.5" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold mb-2">No Scenes Configured</h3>
          <p className="text-[#636366] mb-4">Capture your current lighting setup as a scene to quickly recall it later.</p>
          <button
            onClick={openCaptureModal}
            className="inline-flex items-center gap-2 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0zM18.75 10.5h.008v.008h-.008V10.5z" />
            </svg>
            Capture First Scene
          </button>
        </div>
      ) : (
        /* Scenes Table */
        <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[#2a2a2f]">
                <th
                  className="text-left px-4 py-3 text-sm font-medium text-[#a1a1a6] cursor-pointer hover:text-white"
                  onClick={() => handleSort('name')}
                >
                  Name <SortIndicator column="name" />
                </th>
                <th
                  className="text-left px-4 py-3 text-sm font-medium text-[#a1a1a6] cursor-pointer hover:text-white"
                  onClick={() => handleSort('fixtures')}
                >
                  Fixtures <SortIndicator column="fixtures" />
                </th>
                <th
                  className="text-left px-4 py-3 text-sm font-medium text-[#a1a1a6] cursor-pointer hover:text-white"
                  onClick={() => handleSort('scope')}
                >
                  Scope <SortIndicator column="scope" />
                </th>
                <th className="text-right px-4 py-3 text-sm font-medium text-[#a1a1a6]">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedScenes.map((scene) => (
                <tr
                  key={scene.id}
                  className="border-b border-[#2a2a2f] last:border-b-0 hover:bg-white/[0.02]"
                >
                  <td className="px-4 py-3">
                    <span className="font-medium">{scene.name}</span>
                  </td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => openDetailsModal(scene)}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-[#2a2a2f] hover:bg-[#3a3a3f] rounded-md text-sm transition-colors"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 18v-5.25m0 0a6.01 6.01 0 001.5-.189m-1.5.189a6.01 6.01 0 01-1.5-.189m3.75 7.478a12.06 12.06 0 01-4.5 0m3.75 2.383a14.406 14.406 0 01-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 10-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" />
                      </svg>
                      {scene.values.length} fixture{scene.values.length !== 1 ? 's' : ''}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    {scene.scope_group_id ? (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-purple-500/15 text-purple-400 border border-purple-500/30 rounded-full text-xs font-medium">
                        <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                          <path d="M2.25 7.125C2.25 6.504 2.754 6 3.375 6h6c.621 0 1.125.504 1.125 1.125v3.75c0 .621-.504 1.125-1.125 1.125h-6a1.125 1.125 0 01-1.125-1.125v-3.75z" />
                        </svg>
                        {getGroupName(scene.scope_group_id)}
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-blue-500/15 text-blue-400 border border-blue-500/30 rounded-full text-xs font-medium">
                        <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                          <path d="M12 2.25c-5.385 0-9.75 4.365-9.75 9.75s4.365 9.75 9.75 9.75 9.75-4.365 9.75-9.75S17.385 2.25 12 2.25z" />
                        </svg>
                        Global
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      {/* Recall Button */}
                      <button
                        onClick={() => handleRecallScene(scene.id)}
                        disabled={recallingSceneId === scene.id}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-amber-500/15 hover:bg-amber-500/25 text-amber-400 border border-amber-500/30 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
                        title="Recall Scene"
                      >
                        {recallingSceneId === scene.id ? (
                          <>
                            <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin"></div>
                            Recalling...
                          </>
                        ) : (
                          <>
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.985V5.653z" />
                            </svg>
                            Recall
                          </>
                        )}
                      </button>
                      {/* Edit Button */}
                      <button
                        onClick={() => openEditModal(scene)}
                        className="p-2 hover:bg-white/5 rounded-lg transition-colors text-[#a1a1a6] hover:text-white"
                        title="Edit"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
                        </svg>
                      </button>
                      {/* Delete Button */}
                      {deleteConfirm === scene.id ? (
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleDeleteScene(scene.id)}
                            className="px-2 py-1 bg-red-500 hover:bg-red-600 text-white text-xs rounded transition-colors"
                          >
                            Confirm
                          </button>
                          <button
                            onClick={() => setDeleteConfirm(null)}
                            className="px-2 py-1 bg-[#2a2a2f] hover:bg-[#3a3a3f] text-white text-xs rounded transition-colors"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setDeleteConfirm(scene.id)}
                          className="p-2 hover:bg-red-500/10 rounded-lg transition-colors text-[#a1a1a6] hover:text-red-400"
                          title="Delete"
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

      {/* Capture Scene Modal */}
      {isCaptureModalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] w-full max-w-lg mx-4 overflow-hidden">
            <div className="px-6 py-4 border-b border-[#2a2a2f]">
              <h2 className="text-lg font-semibold">Capture Scene</h2>
              <p className="text-sm text-[#636366]">Save current fixture states as a new scene</p>
            </div>
            <div className="p-6 space-y-4 max-h-[60vh] overflow-y-auto">
              {/* Scene Name */}
              <div>
                <label className="block text-sm font-medium text-[#a1a1a6] mb-1.5">
                  Scene Name <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={captureFormData.name}
                  onChange={(e) => setCaptureFormData({ ...captureFormData, name: e.target.value })}
                  placeholder="e.g., Movie Night"
                  className="w-full px-3 py-2 bg-[#0a0a0b] border border-[#2a2a2f] rounded-lg text-white placeholder:text-[#636366] focus:outline-none focus:border-amber-500"
                />
              </div>

              {/* Scope Group */}
              <div>
                <label className="block text-sm font-medium text-[#a1a1a6] mb-1.5">
                  Scope (Optional)
                </label>
                <select
                  value={captureFormData.scope_group_id}
                  onChange={(e) => setCaptureFormData({ ...captureFormData, scope_group_id: e.target.value })}
                  className="w-full px-3 py-2 bg-[#0a0a0b] border border-[#2a2a2f] rounded-lg text-white focus:outline-none focus:border-amber-500"
                >
                  <option value="">Global (available everywhere)</option>
                  {groups.map((group) => (
                    <option key={group.id} value={group.id}>
                      {group.name}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-[#636366] mt-1">
                  Optionally limit this scene to a specific group
                </p>
              </div>

              {/* Fixture Selection */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="block text-sm font-medium text-[#a1a1a6]">
                    Fixtures to Capture <span className="text-red-400">*</span>
                  </label>
                  <button
                    type="button"
                    onClick={toggleAllFixtures}
                    className="text-xs text-amber-400 hover:text-amber-300"
                  >
                    {captureFormData.fixture_ids.length === fixtures.length ? 'Deselect All' : 'Select All'}
                  </button>
                </div>
                {fixtures.length === 0 ? (
                  <p className="text-center text-[#636366] py-4">No fixtures available</p>
                ) : (
                  <div className="space-y-2 max-h-48 overflow-y-auto">
                    {fixtures.map((fixture) => {
                      const state = fixtureStates.get(fixture.id);
                      const brightness = state ? Math.round(state.goal_brightness / 10) : 0;
                      const cct = state?.goal_cct || 2700;
                      const isSelected = captureFormData.fixture_ids.includes(fixture.id);

                      return (
                        <label
                          key={fixture.id}
                          className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-colors ${
                            isSelected
                              ? 'bg-amber-500/10 border border-amber-500/30'
                              : 'bg-[#0a0a0b] border border-[#2a2a2f] hover:border-[#3a3a3f]'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleFixtureForCapture(fixture.id)}
                            className="w-4 h-4 rounded border-[#3a3a3f] bg-[#0a0a0b] text-amber-500 focus:ring-amber-500 focus:ring-offset-0"
                          />
                          <div className="flex-1 min-w-0">
                            <div className="font-medium truncate">{fixture.name}</div>
                            <div className="flex items-center gap-3 text-xs text-[#636366] mt-0.5">
                              <span>Brightness: {brightness}%</span>
                              <span
                                className="flex items-center gap-1"
                                style={{ color: kelvinToColor(cct) }}
                              >
                                <span
                                  className="w-2 h-2 rounded-full"
                                  style={{ backgroundColor: kelvinToColor(cct) }}
                                />
                                {cct}K
                              </span>
                            </div>
                          </div>
                        </label>
                      );
                    })}
                  </div>
                )}
                <p className="text-xs text-[#636366] mt-2">
                  {captureFormData.fixture_ids.length} fixture{captureFormData.fixture_ids.length !== 1 ? 's' : ''} selected
                </p>
              </div>
            </div>
            <div className="px-6 py-4 border-t border-[#2a2a2f] flex justify-end gap-3">
              <button
                onClick={() => setIsCaptureModalOpen(false)}
                className="px-4 py-2 bg-[#2a2a2f] hover:bg-[#3a3a3f] text-white rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleCaptureScene}
                disabled={isCapturing}
                className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
              >
                {isCapturing ? (
                  <>
                    <div className="w-4 h-4 border-2 border-black border-t-transparent rounded-full animate-spin"></div>
                    Capturing...
                  </>
                ) : (
                  <>
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z" />
                    </svg>
                    Capture Scene
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Scene Modal */}
      {isEditModalOpen && editingScene && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] w-full max-w-md mx-4 overflow-hidden">
            <div className="px-6 py-4 border-b border-[#2a2a2f]">
              <h2 className="text-lg font-semibold">Edit Scene</h2>
            </div>
            <div className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-[#a1a1a6] mb-1.5">
                  Scene Name <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  placeholder="e.g., Movie Night"
                  className="w-full px-3 py-2 bg-[#0a0a0b] border border-[#2a2a2f] rounded-lg text-white placeholder:text-[#636366] focus:outline-none focus:border-amber-500"
                />
              </div>
            </div>
            <div className="px-6 py-4 border-t border-[#2a2a2f] flex justify-end gap-3">
              <button
                onClick={() => setIsEditModalOpen(false)}
                className="px-4 py-2 bg-[#2a2a2f] hover:bg-[#3a3a3f] text-white rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveEdit}
                disabled={isSaving}
                className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors disabled:opacity-50"
              >
                {isSaving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Scene Details Modal */}
      {isDetailsModalOpen && viewingScene && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] w-full max-w-lg mx-4 overflow-hidden">
            <div className="px-6 py-4 border-b border-[#2a2a2f] flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold">{viewingScene.name}</h2>
                <p className="text-sm text-[#636366]">
                  {viewingScene.values.length} fixture{viewingScene.values.length !== 1 ? 's' : ''} • {getGroupName(viewingScene.scope_group_id)}
                </p>
              </div>
              <button
                onClick={() => setIsDetailsModalOpen(false)}
                className="p-2 hover:bg-white/5 rounded-lg transition-colors text-[#a1a1a6] hover:text-white"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="p-6 max-h-96 overflow-y-auto">
              {viewingScene.values.length === 0 ? (
                <p className="text-center text-[#636366] py-4">No fixture values stored in this scene</p>
              ) : (
                <div className="space-y-2">
                  {viewingScene.values.map((value) => (
                    <div
                      key={value.fixture_id}
                      className="flex items-center justify-between p-3 bg-[#0a0a0b] border border-[#2a2a2f] rounded-lg"
                    >
                      <div className="flex items-center gap-3">
                        <div
                          className="w-2.5 h-2.5 rounded-full"
                          style={{
                            backgroundColor: value.target_brightness && value.target_brightness > 0
                              ? '#f59e0b'
                              : '#3a3a3f',
                            boxShadow: value.target_brightness && value.target_brightness > 0
                              ? '0 0 8px rgba(245, 158, 11, 0.4)'
                              : 'none',
                          }}
                        />
                        <span className="font-medium">{getFixtureName(value.fixture_id)}</span>
                      </div>
                      <div className="flex items-center gap-4 text-sm">
                        <div className="flex items-center gap-1.5">
                          <svg className="w-4 h-4 text-[#636366]" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z" />
                          </svg>
                          <span className="font-mono text-[#a1a1a6]">{formatBrightness(value.target_brightness)}</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <div
                            className="w-4 h-4 rounded-full"
                            style={{
                              backgroundColor: value.target_cct_kelvin
                                ? kelvinToColor(value.target_cct_kelvin)
                                : '#636366',
                            }}
                          />
                          <span className="font-mono text-[#a1a1a6]">{formatCCT(value.target_cct_kelvin)}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="px-6 py-4 border-t border-[#2a2a2f] flex justify-between">
              <button
                onClick={() => {
                  setIsDetailsModalOpen(false);
                  handleRecallScene(viewingScene.id);
                }}
                disabled={recallingSceneId === viewingScene.id}
                className="inline-flex items-center gap-2 px-4 py-2 bg-amber-500/15 hover:bg-amber-500/25 text-amber-400 border border-amber-500/30 rounded-lg font-medium transition-colors disabled:opacity-50"
              >
                {recallingSceneId === viewingScene.id ? (
                  <>
                    <div className="w-4 h-4 border-2 border-amber-400 border-t-transparent rounded-full animate-spin"></div>
                    Recalling...
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 5.653c0-.856.917-1.398 1.667-.986l11.54 6.348a1.125 1.125 0 010 1.971l-11.54 6.347a1.125 1.125 0 01-1.667-.985V5.653z" />
                    </svg>
                    Recall Scene
                  </>
                )}
              </button>
              <button
                onClick={() => setIsDetailsModalOpen(false)}
                className="px-4 py-2 bg-[#2a2a2f] hover:bg-[#3a3a3f] text-white rounded-lg transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
