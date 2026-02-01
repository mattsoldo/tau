'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import Link from 'next/link';
import { Menu, X, Sun, Moon, Monitor, LayoutDashboard, Settings, Cpu, Radio, Plus, GripVertical, Pencil, Check, Power, PowerOff } from 'lucide-react';
import { useTheme } from '@/contexts/ThemeContext';
import { LightGroup } from '@/components/mobile/LightGroup';
import { SceneCard } from '@/components/mobile/SceneCard';
import { SceneCaptureModal } from '@/components/mobile/SceneCaptureModal';
import { filterMergedFixtures } from '@/utils/fixtures';
import { useWebSocket, FixtureStateChangedEvent, GroupStateChangedEvent } from '@/hooks/useWebSocket';
import { API_URL } from '@/utils/api';

// === Types ===

interface FixtureModel {
  id: number;
  manufacturer: string;
  model: string;
  type: string;
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
  display_order?: number | null;
  // Sleep Mode Lock Settings
  sleep_lock_enabled?: boolean;
  sleep_lock_start_time?: string | null;
  sleep_lock_end_time?: string | null;
  sleep_lock_unlock_duration_minutes?: number | null;
  sleep_lock_active?: boolean | null;
}

interface Scene {
  id: number;
  name: string;
  scope_group_id: number | null;
  scene_type?: 'toggle' | 'idempotent';
  display_order?: number | null;
}

interface FixtureWithState extends Fixture {
  model?: FixtureModel;
  state?: FixtureState;
}

interface GroupWithFixtures extends Group {
  fixtures: FixtureWithState[];
}

// === Constants ===
const BRIGHTNESS_SCALE = 1000;

// Scene icons based on name
const getSceneIcon = (name: string): 'sun' | 'moon' | 'sunset' | 'coffee' | 'sparkles' | 'lightbulb' => {
  const lowerName = name.toLowerCase();
  if (lowerName.includes('bright') || lowerName.includes('day')) return 'sun';
  if (lowerName.includes('night') || lowerName.includes('movie') || lowerName.includes('dim')) return 'moon';
  if (lowerName.includes('relax') || lowerName.includes('evening') || lowerName.includes('warm')) return 'sunset';
  if (lowerName.includes('morning') || lowerName.includes('wake')) return 'coffee';
  if (lowerName.includes('party') || lowerName.includes('fun')) return 'sparkles';
  return 'lightbulb';
};

export default function HomePage() {
  const [groupsWithFixtures, setGroupsWithFixtures] = useState<GroupWithFixtures[]>([]);
  const [scenes, setScenes] = useState<Scene[]>([]);
  const [activeSceneId, setActiveSceneId] = useState<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [streetAddress, setStreetAddress] = useState<string>('');
  const [captureModalOpen, setCaptureModalOpen] = useState(false);
  const [captureGroupId, setCaptureGroupId] = useState<number | null>(null);
  const [captureGroupName, setCaptureGroupName] = useState<string | undefined>(undefined);
  const [isEditMode, setIsEditMode] = useState(false);
  const [draggedGroupId, setDraggedGroupId] = useState<number | null>(null);
  const [draggedSceneId, setDraggedSceneId] = useState<number | null>(null);

  // Track pending API requests to avoid WebSocket race conditions
  const pendingRequestsRef = useRef<Set<string>>(new Set());

  // Theme - must be called before any early returns
  const { theme, setTheme } = useTheme();

  // WebSocket handlers
  const handleFixtureStateChanged = useCallback((event: FixtureStateChangedEvent) => {
    const key = `fixture-${event.fixture_id}`;
    if (pendingRequestsRef.current.has(key)) return;

    setGroupsWithFixtures(prev => {
      let hasChanges = false;
      const updated = prev.map(group => ({
        ...group,
        fixtures: group.fixtures.map(f => {
          if (f.id !== event.fixture_id || !f.state) return f;
          const newBrightness = event.brightness * BRIGHTNESS_SCALE;
          const newCct = event.color_temp ?? f.state.goal_cct;
          const newIsOn = event.brightness > 0;
          if (f.state.goal_brightness === newBrightness && f.state.goal_cct === newCct && f.state.is_on === newIsOn) {
            return f;
          }
          hasChanges = true;
          return { ...f, state: { ...f.state, goal_brightness: newBrightness, goal_cct: newCct, is_on: newIsOn } };
        }),
      }));
      return hasChanges ? updated : prev;
    });
  }, []);

  const handleGroupStateChanged = useCallback((event: GroupStateChangedEvent) => {
    const key = `group-${event.group_id}`;
    if (pendingRequestsRef.current.has(key)) return;

    setGroupsWithFixtures(prev => {
      let hasChanges = false;
      const updated = prev.map(group => {
        if (group.id !== event.group_id) return group;
        const updatedFixtures = group.fixtures.map(f => {
          if (!f.state) return f;
          const newBrightness = event.brightness * BRIGHTNESS_SCALE;
          const newCct = event.color_temp ?? f.state.goal_cct;
          const newIsOn = event.brightness > 0;
          if (f.state.goal_brightness === newBrightness && f.state.goal_cct === newCct && f.state.is_on === newIsOn) {
            return f;
          }
          hasChanges = true;
          return { ...f, state: { ...f.state, goal_brightness: newBrightness, goal_cct: newCct, is_on: newIsOn } };
        });
        return { ...group, fixtures: updatedFixtures };
      });
      return hasChanges ? updated : prev;
    });
  }, []);

  useWebSocket({
    onFixtureStateChanged: handleFixtureStateChanged,
    onGroupStateChanged: handleGroupStateChanged,
  });

  // Fetch all data
  const fetchData = useCallback(async () => {
    try {
      const [fixturesRes, modelsRes, groupsRes, scenesRes, settingsRes] = await Promise.all([
        fetch(`${API_URL}/api/fixtures/`),
        fetch(`${API_URL}/api/fixtures/models`),
        fetch(`${API_URL}/api/groups/`),
        fetch(`${API_URL}/api/scenes/`),
        fetch(`${API_URL}/api/config/settings/street_address`),
      ]);

      // Fetch street address setting
      if (settingsRes.ok) {
        const settingData = await settingsRes.json();
        setStreetAddress(settingData.value || '');
      }

      if (!fixturesRes.ok || !modelsRes.ok || !groupsRes.ok) {
        throw new Error('Failed to fetch data');
      }

      const [fixturesData, modelsData, groupsData] = await Promise.all([
        fixturesRes.json(),
        modelsRes.json(),
        groupsRes.json(),
      ]);

      let scenesData: Scene[] = [];
      if (scenesRes.ok) {
        scenesData = await scenesRes.json();
      }
      setScenes(scenesData);

      // Filter out merged fixtures
      const visibleFixtures = filterMergedFixtures(fixturesData);

      // Fetch state for all visible fixtures
      const fixturesWithState: FixtureWithState[] = await Promise.all(
        visibleFixtures.map(async (fixture: Fixture) => {
          const model = modelsData.find((m: FixtureModel) => m.id === fixture.fixture_model_id);
          let state: FixtureState | undefined;

          try {
            const stateRes = await fetch(`${API_URL}/api/fixtures/${fixture.id}/state`);
            if (stateRes.ok) {
              const fetchedState = await stateRes.json();
              state = {
                fixture_id: fixture.id,
                goal_brightness: fetchedState.goal_brightness ?? 0,
                goal_cct: fetchedState.goal_cct ?? 2700,
                current_brightness: fetchedState.current_brightness ?? 0,
                current_cct: fetchedState.current_cct ?? 2700,
                is_on: (fetchedState.current_brightness ?? 0) > 0,
              };
            }
          } catch {
            // State might not exist yet
          }

          return { ...fixture, model, state };
        })
      );

      // Build groups with fixtures
      const groupsWithFixturesData: GroupWithFixtures[] = await Promise.all(
        groupsData.map(async (group: Group) => {
          try {
            const fixturesInGroupRes = await fetch(`${API_URL}/api/groups/${group.id}/fixtures`);
            if (fixturesInGroupRes.ok) {
              const fixtureIds: { id: number }[] = await fixturesInGroupRes.json();
              const fixtures = fixtureIds
                .map(f => fixturesWithState.find(fw => fw.id === f.id))
                .filter((f): f is FixtureWithState => f !== undefined);
              return { ...group, fixtures };
            }
          } catch {
            // Ignore errors
          }
          return { ...group, fixtures: [] };
        })
      );

      // Filter out empty groups and system groups, sort by display_order (nulls last), then by name
      const filteredGroups = groupsWithFixturesData
        .filter(g => g.fixtures.length > 0 && !g.is_system)
        .sort((a, b) => {
          // Both have display_order: sort by it
          if (a.display_order != null && b.display_order != null) {
            return a.display_order - b.display_order;
          }
          // Only a has display_order: a comes first
          if (a.display_order != null) return -1;
          // Only b has display_order: b comes first
          if (b.display_order != null) return 1;
          // Neither has display_order: sort by name
          return a.name.localeCompare(b.name);
        });

      setGroupsWithFixtures(filteredGroups);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000); // Poll every 5s for state sync
    return () => clearInterval(interval);
  }, [fetchData]);

  // Control functions - send immediately, no debounce for responsive slider
  // Note: API expects brightness as 0.0-1.0, but UI uses 0-100 for percentage display
  const sendFixtureControl = useCallback(async (fixtureId: number, brightness: number) => {
    const key = `fixture-${fixtureId}`;
    pendingRequestsRef.current.add(key);

    try {
      // Convert 0-100 to 0.0-1.0 for API, use instant transition for responsiveness
      await fetch(`${API_URL}/api/control/fixtures/${fixtureId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          brightness: brightness / 100,
          transition_duration: 0,
        }),
      });
    } catch (err) {
      console.error('Fixture control error:', err);
    } finally {
      // Small delay before clearing pending flag to avoid WebSocket race
      setTimeout(() => pendingRequestsRef.current.delete(key), 100);
    }
  }, []);

  const sendGroupControl = useCallback(async (groupId: number, brightness: number) => {
    const key = `group-${groupId}`;
    pendingRequestsRef.current.add(key);

    try {
      // Convert 0-100 to 0.0-1.0 for API, use instant transition for responsiveness
      await fetch(`${API_URL}/api/control/groups/${groupId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          brightness: brightness / 100,
          transition_duration: 0,
        }),
      });
    } catch (err) {
      console.error('Group control error:', err);
    } finally {
      // Small delay before clearing pending flag to avoid WebSocket race
      setTimeout(() => pendingRequestsRef.current.delete(key), 100);
    }
  }, []);

  // All On / All Off handlers - use dedicated endpoints for simultaneous control
  const handleAllOn = useCallback(async () => {
    // Update local state immediately for responsiveness
    setGroupsWithFixtures(prev =>
      prev.map(g => ({
        ...g,
        fixtures: g.fixtures.map(f => ({
          ...f,
          state: f.state ? { ...f.state, is_on: true, goal_brightness: 1000 } : f.state,
        })),
      }))
    );

    // Single API call to turn on all fixtures simultaneously
    try {
      await fetch(`${API_URL}/api/control/all-on`, { method: 'POST' });
    } catch (error) {
      console.error('Failed to turn all on:', error);
    }
  }, []);

  const handleAllOff = useCallback(async () => {
    // Update local state immediately for responsiveness
    setGroupsWithFixtures(prev =>
      prev.map(g => ({
        ...g,
        fixtures: g.fixtures.map(f => ({
          ...f,
          state: f.state ? { ...f.state, is_on: false, goal_brightness: 0 } : f.state,
        })),
      }))
    );

    // Single API call to turn off all fixtures simultaneously
    try {
      await fetch(`${API_URL}/api/control/all-off`, { method: 'POST' });
    } catch (error) {
      console.error('Failed to turn all off:', error);
    }
  }, []);

  const activateScene = useCallback(async (sceneId: number) => {
    setActiveSceneId(sceneId);
    try {
      // Use recall endpoint which handles toggle behavior
      const response = await fetch(`${API_URL}/api/scenes/recall`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scene_id: sceneId, fade_duration: 0.5 }),
      });

      if (response.ok) {
        const result = await response.json();
        // If toggle scene was turned off, clear the active scene indicator
        if (result.toggled_off) {
          setActiveSceneId(null);
        }
      }

      // Refresh data after scene activation
      setTimeout(fetchData, 200);
    } catch (err) {
      console.error('Scene activation error:', err);
    }
  }, [fetchData]);

  // Open capture modal for global scene
  const openGlobalCapture = useCallback(() => {
    setCaptureGroupId(null);
    setCaptureGroupName(undefined);
    setCaptureModalOpen(true);
  }, []);

  // Open capture modal for room-specific scene
  const openRoomCapture = useCallback((groupId: number, groupName: string) => {
    setCaptureGroupId(groupId);
    setCaptureGroupName(groupName);
    setCaptureModalOpen(true);
  }, []);

  // Capture scene
  const captureScene = useCallback(async (name: string, isToggle: boolean) => {
    try {
      const body: {
        name: string;
        scene_type: 'toggle' | 'idempotent';
        scope_group_id?: number;
        include_group_ids?: number[];
      } = {
        name,
        scene_type: isToggle ? 'toggle' : 'idempotent',
      };

      // If capturing for a specific room, set the scope
      if (captureGroupId !== null) {
        body.scope_group_id = captureGroupId;
        body.include_group_ids = [captureGroupId];
      }

      const response = await fetch(`${API_URL}/api/scenes/capture`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (response.ok) {
        // Refresh scenes list
        fetchData();
      } else {
        console.error('Failed to capture scene');
      }
    } catch (err) {
      console.error('Scene capture error:', err);
    }
  }, [captureGroupId, fetchData]);

  // Reorder groups
  const reorderGroups = useCallback(async (newOrder: number[]) => {
    try {
      const response = await fetch(`${API_URL}/api/groups/reorder`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ group_ids: newOrder }),
      });

      if (response.ok) {
        // Update local order based on response
        const updatedGroups = await response.json();
        setGroupsWithFixtures(prev => {
          const groupMap = new Map(prev.map(g => [g.id, g]));
          return updatedGroups
            .map((g: Group) => groupMap.get(g.id))
            .filter((g: GroupWithFixtures | undefined): g is GroupWithFixtures => g !== undefined && g.fixtures.length > 0 && !g.is_system);
        });
      }
    } catch (err) {
      console.error('Failed to reorder groups:', err);
    }
  }, []);

  // Reorder scenes
  const reorderScenes = useCallback(async (newOrder: number[]) => {
    try {
      const response = await fetch(`${API_URL}/api/scenes/reorder`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scene_ids: newOrder }),
      });

      if (response.ok) {
        // Update local order based on response
        const updatedScenes = await response.json();
        setScenes(updatedScenes);
      }
    } catch (err) {
      console.error('Failed to reorder scenes:', err);
    }
  }, []);

  // Handle group drag and drop
  const handleGroupDragStart = useCallback((e: React.DragEvent, groupId: number) => {
    setDraggedGroupId(groupId);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', groupId.toString());
  }, []);

  const handleGroupDragOver = useCallback((e: React.DragEvent, targetGroupId: number) => {
    e.preventDefault();
    if (draggedGroupId === null || draggedGroupId === targetGroupId) return;

    setGroupsWithFixtures(prev => {
      const draggedIndex = prev.findIndex(g => g.id === draggedGroupId);
      const targetIndex = prev.findIndex(g => g.id === targetGroupId);
      if (draggedIndex === -1 || targetIndex === -1) return prev;

      const newOrder = [...prev];
      const [removed] = newOrder.splice(draggedIndex, 1);
      newOrder.splice(targetIndex, 0, removed);
      return newOrder;
    });
  }, [draggedGroupId]);

  const handleGroupDragEnd = useCallback(() => {
    if (draggedGroupId !== null) {
      // Save the new order to the backend
      const newOrder = groupsWithFixtures.map(g => g.id);
      reorderGroups(newOrder);
    }
    setDraggedGroupId(null);
  }, [draggedGroupId, groupsWithFixtures, reorderGroups]);

  // Handle scene drag and drop
  const handleSceneDragStart = useCallback((e: React.DragEvent, sceneId: number) => {
    setDraggedSceneId(sceneId);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', sceneId.toString());
  }, []);

  const handleSceneDragOver = useCallback((e: React.DragEvent, targetSceneId: number) => {
    e.preventDefault();
    if (draggedSceneId === null || draggedSceneId === targetSceneId) return;

    setScenes(prev => {
      const draggedIndex = prev.findIndex(s => s.id === draggedSceneId);
      const targetIndex = prev.findIndex(s => s.id === targetSceneId);
      if (draggedIndex === -1 || targetIndex === -1) return prev;

      const newOrder = [...prev];
      const [removed] = newOrder.splice(draggedIndex, 1);
      newOrder.splice(targetIndex, 0, removed);
      return newOrder;
    });
  }, [draggedSceneId]);

  const handleSceneDragEnd = useCallback(() => {
    if (draggedSceneId !== null) {
      // Save the new order to the backend - only global scenes
      const globalSceneIds = scenes.filter(s => s.scope_group_id === null).map(s => s.id);
      reorderScenes(globalSceneIds);
    }
    setDraggedSceneId(null);
  }, [draggedSceneId, scenes, reorderScenes]);

  // Calculate group average brightness
  const getGroupBrightness = (group: GroupWithFixtures): number => {
    const onFixtures = group.fixtures.filter(f => f.state?.is_on);
    if (onFixtures.length === 0) return 0;
    const total = onFixtures.reduce((sum, f) => sum + (f.state?.goal_brightness ?? 0), 0);
    return Math.round(total / onFixtures.length / 10); // Convert from 0-1000 to 0-100
  };

  const isGroupOn = (group: GroupWithFixtures): boolean => {
    return group.fixtures.some(f => f.state?.is_on);
  };

  // Group toggle handler
  const handleGroupToggle = useCallback((group: GroupWithFixtures) => {
    const isOn = isGroupOn(group);
    const newBrightness = isOn ? 0 : 100;

    // Update local state immediately for responsiveness
    setGroupsWithFixtures(prev =>
      prev.map(g => {
        if (g.id !== group.id) return g;
        return {
          ...g,
          fixtures: g.fixtures.map(f => ({
            ...f,
            state: f.state ? { ...f.state, is_on: !isOn, goal_brightness: newBrightness * 10 } : f.state,
          })),
        };
      })
    );

    sendGroupControl(group.id, newBrightness);
  }, [sendGroupControl]);

  // Group brightness change handler
  const handleGroupBrightnessChange = useCallback((group: GroupWithFixtures, brightness: number) => {
    // Update local state immediately
    setGroupsWithFixtures(prev =>
      prev.map(g => {
        if (g.id !== group.id) return g;
        return {
          ...g,
          fixtures: g.fixtures.map(f => ({
            ...f,
            state: f.state ? { ...f.state, is_on: brightness > 0, goal_brightness: brightness * 10 } : f.state,
          })),
        };
      })
    );

    sendGroupControl(group.id, brightness);
  }, [sendGroupControl]);

  // Fixture toggle handler
  const handleFixtureToggle = useCallback((groupId: number, fixtureId: number) => {
    setGroupsWithFixtures(prev =>
      prev.map(g => {
        if (g.id !== groupId) return g;
        return {
          ...g,
          fixtures: g.fixtures.map(f => {
            if (f.id !== fixtureId || !f.state) return f;
            const newIsOn = !f.state.is_on;
            const newBrightness = newIsOn ? 1000 : 0;
            sendFixtureControl(fixtureId, newIsOn ? 100 : 0);
            return { ...f, state: { ...f.state, is_on: newIsOn, goal_brightness: newBrightness } };
          }),
        };
      })
    );
  }, [sendFixtureControl]);

  // Fixture brightness change handler
  const handleFixtureBrightnessChange = useCallback((groupId: number, fixtureId: number, brightness: number) => {
    setGroupsWithFixtures(prev =>
      prev.map(g => {
        if (g.id !== groupId) return g;
        return {
          ...g,
          fixtures: g.fixtures.map(f => {
            if (f.id !== fixtureId || !f.state) return f;
            return { ...f, state: { ...f.state, is_on: brightness > 0, goal_brightness: brightness * 10 } };
          }),
        };
      })
    );

    sendFixtureControl(fixtureId, brightness);
  }, [sendFixtureControl]);

  // Get scenes for a specific group (only group-scoped scenes, not global)
  const getScenesForGroup = (groupId: number): Scene[] => {
    return scenes.filter(s => s.scope_group_id === groupId);
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100 dark:from-[#0a0a0b] dark:to-[#0f0f14] flex items-center justify-center">
        <div className="text-gray-500 dark:text-gray-400">Loading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100 dark:from-[#0a0a0b] dark:to-[#0f0f14] flex items-center justify-center">
        <div className="text-red-500">{error}</div>
      </div>
    );
  }

  // Global scenes (not scoped to any group)
  const globalScenes = scenes.filter(s => s.scope_group_id === null);

  const navItems = [
    { href: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { href: '/labjack', label: 'LabJack Monitor', icon: Cpu },
    { href: '/config', label: 'Configuration', icon: Settings },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-50 to-gray-100 dark:from-[#0a0a0b] dark:to-[#0f0f14]">
      {/* Mobile: Slide-out menu overlay */}
      {menuOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setMenuOpen(false)}
        />
      )}

      {/* Mobile: Slide-out menu */}
      <div
        className={`fixed top-0 right-0 h-full w-72 bg-white dark:bg-[#1a1a1f] shadow-2xl z-50 transform transition-transform duration-300 ease-in-out lg:hidden ${
          menuOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <div className="p-5">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Menu</h2>
            <button
              onClick={() => setMenuOpen(false)}
              className="w-10 h-10 rounded-full bg-gray-100 dark:bg-[#2a2a2f] flex items-center justify-center hover:bg-gray-200 dark:hover:bg-[#3a3a3f] transition-colors"
            >
              <X className="w-5 h-5 text-gray-600 dark:text-gray-400" />
            </button>
          </div>
          <nav className="space-y-2">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => setMenuOpen(false)}
                className="flex items-center gap-3 px-4 py-3 rounded-xl text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-[#2a2a2f] transition-colors"
              >
                <item.icon className="w-5 h-5 text-gray-500 dark:text-gray-400" />
                <span className="font-medium">{item.label}</span>
              </Link>
            ))}
          </nav>
          <div className="mt-6 pt-6 border-t border-gray-100 dark:border-[#2a2a2f]">
            <a
              href="/ola/"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-3 px-4 py-3 rounded-xl text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-[#2a2a2f] transition-colors"
            >
              <Radio className="w-5 h-5 text-gray-500 dark:text-gray-400" />
              <span className="font-medium">OLA Dashboard</span>
              <svg className="w-4 h-4 text-gray-400 ml-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
          </div>

          {/* Theme Toggle */}
          <div className="mt-6 pt-6 border-t border-gray-100 dark:border-[#2a2a2f]">
            <p className="px-4 text-sm font-medium text-gray-500 dark:text-gray-400 mb-3">Appearance</p>
            <div className="flex gap-2 px-4">
              <button
                onClick={() => setTheme('light')}
                className={`flex-1 flex flex-col items-center gap-1 py-3 px-2 rounded-xl transition-colors ${
                  theme === 'light'
                    ? 'bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-400'
                    : 'bg-gray-100 dark:bg-[#2a2a2f] text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-[#3a3a3f]'
                }`}
              >
                <Sun className="w-5 h-5" />
                <span className="text-xs font-medium">Light</span>
              </button>
              <button
                onClick={() => setTheme('dark')}
                className={`flex-1 flex flex-col items-center gap-1 py-3 px-2 rounded-xl transition-colors ${
                  theme === 'dark'
                    ? 'bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-400'
                    : 'bg-gray-100 dark:bg-[#2a2a2f] text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-[#3a3a3f]'
                }`}
              >
                <Moon className="w-5 h-5" />
                <span className="text-xs font-medium">Dark</span>
              </button>
              <button
                onClick={() => setTheme('system')}
                className={`flex-1 flex flex-col items-center gap-1 py-3 px-2 rounded-xl transition-colors ${
                  theme === 'system'
                    ? 'bg-amber-100 dark:bg-amber-500/20 text-amber-600 dark:text-amber-400'
                    : 'bg-gray-100 dark:bg-[#2a2a2f] text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-[#3a3a3f]'
                }`}
              >
                <Monitor className="w-5 h-5" />
                <span className="text-xs font-medium">Auto</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Container - mobile: centered card, desktop: full width */}
      <div className="max-w-md mx-auto bg-white dark:bg-[#0f0f14] min-h-screen shadow-xl lg:max-w-none lg:shadow-none">
        {/* Header */}
        <div className="bg-gradient-to-r from-amber-500 to-orange-500 text-white p-5 lg:px-8">
          <div className="flex items-center justify-between lg:max-w-7xl lg:mx-auto">
            <div className="flex items-center gap-2">
              <Sun className="w-6 h-6" />
              <h1 className="text-xl font-semibold">
                tau lighting{streetAddress && <span className="font-normal text-white/90">@{streetAddress}</span>}
              </h1>
            </div>

            {/* Mobile: hamburger menu */}
            <button
              onClick={() => setMenuOpen(true)}
              className="w-10 h-10 rounded-full bg-white/20 flex items-center justify-center hover:bg-white/30 transition-colors active:scale-95 lg:hidden"
            >
              <Menu className="w-5 h-5" />
            </button>

            {/* Desktop: inline navigation */}
            <nav className="hidden lg:flex items-center gap-1">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-white/80 hover:text-white hover:bg-white/10 transition-colors"
                >
                  <item.icon className="w-4 h-4" />
                  <span className="text-sm font-medium">{item.label}</span>
                </Link>
              ))}
              <a
                href="/ola/"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-white/80 hover:text-white hover:bg-white/10 transition-colors"
              >
                <Radio className="w-4 h-4" />
                <span className="text-sm font-medium">OLA</span>
              </a>
            </nav>
          </div>
        </div>

        {/* Quick Actions Bar */}
        <div className="bg-white dark:bg-[#1a1a1f] border-b border-gray-100 dark:border-[#2a2a2f] px-5 py-3 lg:px-8">
          <div className="lg:max-w-7xl lg:mx-auto flex items-center gap-3">
            <button
              onClick={handleAllOn}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-400 hover:bg-amber-100 dark:hover:bg-amber-500/20 transition-colors text-sm font-medium"
            >
              <Power className="w-4 h-4" />
              All On
            </button>
            <button
              onClick={handleAllOff}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-100 dark:bg-[#2a2a2f] text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-[#3a3a3f] transition-colors text-sm font-medium"
            >
              <PowerOff className="w-4 h-4" />
              All Off
            </button>
          </div>
        </div>

        {/* Content - mobile: stacked, desktop: two columns */}
        <div className="p-5 lg:px-8 lg:py-8">
          <div className="lg:max-w-7xl lg:mx-auto lg:flex lg:gap-8">

            {/* Left column: Light Groups (sliders) */}
            <div className="lg:flex-1 lg:min-w-0">
              {/* Mobile only: Scenes at top */}
              <section className="mb-6 lg:hidden">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Scenes</h2>
                  <button
                    onClick={openGlobalCapture}
                    className="w-8 h-8 rounded-full bg-amber-100 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 flex items-center justify-center hover:bg-amber-200 dark:hover:bg-amber-500/20 transition-colors"
                    title="Capture scene"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                </div>
                {globalScenes.length > 0 ? (
                  <div className="grid grid-cols-3 gap-3">
                    {globalScenes.slice(0, 6).map((scene) => (
                      <div
                        key={scene.id}
                        draggable={isEditMode}
                        onDragStart={(e) => isEditMode && handleSceneDragStart(e, scene.id)}
                        onDragOver={(e) => isEditMode && handleSceneDragOver(e, scene.id)}
                        onDragEnd={isEditMode ? handleSceneDragEnd : undefined}
                        className={`${isEditMode ? 'cursor-grab active:cursor-grabbing' : ''} ${
                          draggedSceneId === scene.id ? 'opacity-50' : ''
                        }`}
                      >
                        <SceneCard
                          name={scene.name}
                          icon={getSceneIcon(scene.name)}
                          isActive={activeSceneId === scene.id}
                          onActivate={isEditMode ? () => {} : () => activateScene(scene.id)}
                        />
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-sm text-gray-500 dark:text-gray-400 italic">
                    No scenes yet. Tap + to capture the current lighting.
                  </div>
                )}
              </section>

              {/* Light Groups */}
              <section>
                <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-3 lg:text-xl">Rooms</h2>
                <div className="space-y-3 lg:space-y-4">
                  {groupsWithFixtures.map((group) => {
                    const groupScenes = getScenesForGroup(group.id).map(s => ({
                      id: s.id,
                      name: s.name,
                      icon: getSceneIcon(s.name),
                    }));

                    // In edit mode, wrap with draggable container
                    if (isEditMode) {
                      return (
                        <div
                          key={group.id}
                          draggable
                          onDragStart={(e) => handleGroupDragStart(e, group.id)}
                          onDragOver={(e) => handleGroupDragOver(e, group.id)}
                          onDragEnd={handleGroupDragEnd}
                          className={`flex items-center gap-2 ${
                            draggedGroupId === group.id ? 'opacity-50' : ''
                          }`}
                        >
                          <div className="flex-shrink-0 cursor-grab active:cursor-grabbing touch-none">
                            <GripVertical className="w-5 h-5 text-gray-400 dark:text-gray-500" />
                          </div>
                          <div className="flex-1 min-w-0 bg-white dark:bg-[#1a1a1f] rounded-xl shadow-sm border border-gray-100 dark:border-[#2a2a2f] p-4">
                            <h3 className="font-semibold text-gray-900 dark:text-white text-sm">{group.name}</h3>
                            {group.description && (
                              <p className="text-xs text-gray-500 dark:text-gray-400">{group.description}</p>
                            )}
                          </div>
                        </div>
                      );
                    }

                    return (
                      <LightGroup
                        key={group.id}
                        name={group.name}
                        description={group.description}
                        isOn={isGroupOn(group)}
                        brightness={getGroupBrightness(group)}
                        fixtures={group.fixtures.map(f => ({
                          id: f.id,
                          name: f.name,
                          isOn: f.state?.is_on ?? false,
                          brightness: Math.round((f.state?.goal_brightness ?? 0) / 10),
                        }))}
                        scenes={groupScenes}
                        activeSceneId={activeSceneId}
                        sleepLock={group.sleep_lock_enabled ? {
                          enabled: group.sleep_lock_enabled,
                          active: group.sleep_lock_active ?? false,
                          unlockDurationMinutes: group.sleep_lock_unlock_duration_minutes ?? 5,
                        } : undefined}
                        onToggle={() => handleGroupToggle(group)}
                        onBrightnessChange={(brightness) => handleGroupBrightnessChange(group, brightness)}
                        onFixtureToggle={(fixtureId) => handleFixtureToggle(group.id, fixtureId)}
                        onFixtureBrightnessChange={(fixtureId, brightness) =>
                          handleFixtureBrightnessChange(group.id, fixtureId, brightness)
                        }
                        onSceneActivate={activateScene}
                        onCaptureScene={() => openRoomCapture(group.id, group.name)}
                      />
                    );
                  })}
                </div>

                {/* Edit button */}
                <div className="mt-4 flex justify-center">
                  <button
                    onClick={() => setIsEditMode(!isEditMode)}
                    className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                      isEditMode
                        ? 'bg-amber-500 text-white hover:bg-amber-600'
                        : 'bg-gray-100 dark:bg-[#2a2a2f] text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-[#3a3a3f]'
                    }`}
                  >
                    {isEditMode ? (
                      <>
                        <Check className="w-4 h-4" />
                        Done
                      </>
                    ) : (
                      <>
                        <Pencil className="w-4 h-4" />
                        Edit Order
                      </>
                    )}
                  </button>
                </div>
              </section>
            </div>

            {/* Right column: Scenes sidebar (desktop only) */}
            <aside className="hidden lg:block lg:w-80 lg:flex-shrink-0">
              <div className="sticky top-8">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Scenes</h2>
                  <button
                    onClick={openGlobalCapture}
                    className="w-8 h-8 rounded-full bg-amber-100 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 flex items-center justify-center hover:bg-amber-200 dark:hover:bg-amber-500/20 transition-colors"
                    title="Capture scene"
                  >
                    <Plus className="w-4 h-4" />
                  </button>
                </div>
                <div className="bg-white dark:bg-[#1a1a1f] rounded-xl shadow-sm border border-gray-100 dark:border-[#2a2a2f] p-4">
                  {globalScenes.length > 0 ? (
                    <div className="grid grid-cols-2 gap-3">
                      {globalScenes.map((scene) => (
                        <div
                          key={scene.id}
                          draggable={isEditMode}
                          onDragStart={(e) => isEditMode && handleSceneDragStart(e, scene.id)}
                          onDragOver={(e) => isEditMode && handleSceneDragOver(e, scene.id)}
                          onDragEnd={isEditMode ? handleSceneDragEnd : undefined}
                          className={`${isEditMode ? 'cursor-grab active:cursor-grabbing' : ''} ${
                            draggedSceneId === scene.id ? 'opacity-50' : ''
                          }`}
                        >
                          <SceneCard
                            name={scene.name}
                            icon={getSceneIcon(scene.name)}
                            isActive={activeSceneId === scene.id}
                            onActivate={isEditMode ? () => {} : () => activateScene(scene.id)}
                          />
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-sm text-gray-500 dark:text-gray-400 italic text-center py-4">
                      No scenes yet. Click + to capture.
                    </div>
                  )}
                </div>
              </div>
            </aside>
          </div>
        </div>
      </div>

      {/* Scene Capture Modal */}
      <SceneCaptureModal
        isOpen={captureModalOpen}
        onClose={() => setCaptureModalOpen(false)}
        onCapture={captureScene}
        groupName={captureGroupName}
      />
    </div>
  );
}
