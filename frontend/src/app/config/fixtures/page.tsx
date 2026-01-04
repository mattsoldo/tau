'use client';

import { useState, useEffect, useCallback, useRef } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// === Types ===

type FixtureType = 'simple_dimmable' | 'tunable_white' | 'dim_to_warm' | 'non_dimmable' | 'other';
type MixingType = 'linear' | 'perceptual' | 'logarithmic' | 'custom';
type ActiveTab = 'fixtures' | 'models';

interface FixtureModel {
  id: number;
  manufacturer: string;
  model: string;
  description: string | null;
  type: FixtureType;
  dmx_footprint: number;
  cct_min_kelvin: number;
  cct_max_kelvin: number;
  mixing_type: MixingType;
  created_at: string;
}

interface Fixture {
  id: number;
  name: string;
  fixture_model_id: number;
  dmx_channel_start: number;
  secondary_dmx_channel: number | null;
  created_at: string;
}

interface Group {
  id: number;
  name: string;
}

interface RDMDeviceInfo {
  rdm_uid: string;
  manufacturer_id: number;
  device_id: number;
  manufacturer_name: string;
  model_name: string;
  dmx_address: number;
  dmx_footprint: number;
  device_label: string | null;
}

interface DiscoveredDeviceRow extends RDMDeviceInfo {
  selected: boolean;
  configured_name: string;
  configured_model_id: number | null;
  configured_group_ids: number[];
  merged_with: string | null;
  is_secondary: boolean;
  secondary_dmx_address: number | null;
  testing: boolean;
}

type DiscoveryPhase = 'idle' | 'scanning' | 'configuring';

interface DiscoveryState {
  phase: DiscoveryPhase;
  discoveryId: string | null;
  progress: number;
  devicesFound: number;
  discoveredDevices: DiscoveredDeviceRow[];
  error: string | null;
}

// === Constants ===

const typeLabels: Record<FixtureType, { label: string; color: string }> = {
  simple_dimmable: { label: 'Simple Dimmable', color: 'bg-blue-500/15 text-blue-400 border-blue-500/30' },
  tunable_white: { label: 'Tunable White', color: 'bg-amber-500/15 text-amber-400 border-amber-500/30' },
  dim_to_warm: { label: 'Dim to Warm', color: 'bg-orange-500/15 text-orange-400 border-orange-500/30' },
  non_dimmable: { label: 'Non-Dimmable', color: 'bg-gray-500/15 text-gray-400 border-gray-500/30' },
  other: { label: 'Other', color: 'bg-purple-500/15 text-purple-400 border-purple-500/30' },
};

const dmxFootprintByType: Record<FixtureType, number> = {
  simple_dimmable: 1,
  tunable_white: 2,
  dim_to_warm: 1,
  non_dimmable: 1,
  other: 1,
};

const mixingLabels: Record<MixingType, string> = {
  linear: 'Linear',
  perceptual: 'Perceptual',
  logarithmic: 'Logarithmic',
  custom: 'Custom',
};

const usesCctRange = (type: FixtureType) => type === 'tunable_white';
const usesSingleCct = (type: FixtureType) => type === 'simple_dimmable' || type === 'dim_to_warm';

interface FixtureFormData {
  name: string;
  fixture_model_id: string;
  dmx_channel_start: string;
  // Dim-to-warm configuration
  dim_to_warm_enabled: boolean;
  dim_to_warm_max_cct: string;
  dim_to_warm_min_cct: string;
}

interface ModelFormData {
  manufacturer: string;
  model: string;
  description: string | null;
  type: FixtureType;
  cct_kelvin: string;
  cct_min_kelvin: string;
  cct_max_kelvin: string;
  mixing_type: MixingType;
}

const emptyFixtureFormData: FixtureFormData = {
  name: '',
  fixture_model_id: '',
  dmx_channel_start: '',
  dim_to_warm_enabled: false,
  dim_to_warm_max_cct: '',
  dim_to_warm_min_cct: '',
};

const emptyModelFormData: ModelFormData = {
  manufacturer: '',
  model: '',
  description: null,
  type: 'simple_dimmable',
  cct_kelvin: '',
  cct_min_kelvin: '',
  cct_max_kelvin: '',
  mixing_type: 'linear',
};

const initialDiscoveryState: DiscoveryState = {
  phase: 'idle',
  discoveryId: null,
  progress: 0,
  devicesFound: 0,
  discoveredDevices: [],
  error: null,
};

export default function FixturesPage() {
  // Tab state
  const [activeTab, setActiveTab] = useState<ActiveTab>('fixtures');

  // Shared data
  const [fixtures, setFixtures] = useState<Fixture[]>([]);
  const [fixtureModels, setFixtureModels] = useState<FixtureModel[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fixture state
  const [isFixtureModalOpen, setIsFixtureModalOpen] = useState(false);
  const [editingFixture, setEditingFixture] = useState<Fixture | null>(null);
  const [fixtureFormData, setFixtureFormData] = useState<FixtureFormData>(emptyFixtureFormData);
  const [fixtureDeleteConfirm, setFixtureDeleteConfirm] = useState<number | null>(null);
  const [isSavingFixture, setIsSavingFixture] = useState(false);

  // Model state
  const [isModelModalOpen, setIsModelModalOpen] = useState(false);
  const [editingModel, setEditingModel] = useState<FixtureModel | null>(null);
  const [modelFormData, setModelFormData] = useState<ModelFormData>(emptyModelFormData);
  const [modelDeleteConfirm, setModelDeleteConfirm] = useState<number | null>(null);
  const [isSavingModel, setIsSavingModel] = useState(false);

  // Discovery state
  const [discovery, setDiscovery] = useState<DiscoveryState>(initialDiscoveryState);
  const [bulkModelId, setBulkModelId] = useState<number | null>(null);
  const [draggedDevice, setDraggedDevice] = useState<string | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Bulk selection state
  const [selectedFixtureIds, setSelectedFixtureIds] = useState<Set<number>>(new Set());
  const [fixtureGroups, setFixtureGroups] = useState<Map<number, number[]>>(new Map());
  const [bulkModelSelectKey, setBulkModelSelectKey] = useState(0); // Force select reset

  // Inline editing state
  const [editingField, setEditingField] = useState<{ fixtureId: number; field: 'name' | 'model' } | null>(null);
  const [editValue, setEditValue] = useState<string>('');

  // Find mode state
  const [findingFixtureId, setFindingFixtureId] = useState<number | null>(null);
  const [findState, setFindState] = useState<boolean>(false);
  const findIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Dropdown state
  const [isAddDropdownOpen, setIsAddDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Merge modal state
  const [isMergeModalOpen, setIsMergeModalOpen] = useState(false);
  const [mergeTargetModel, setMergeTargetModel] = useState<FixtureModel | null>(null);

  // Sort state
  type SortColumn = 'name' | 'model' | 'dmx';
  type SortDirection = 'asc' | 'desc';
  const [sortColumn, setSortColumn] = useState<SortColumn>('dmx');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');

  // === Data Fetching ===

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [fixturesRes, modelsRes, groupsRes] = await Promise.all([
        fetch(`${API_URL}/api/fixtures/`),
        fetch(`${API_URL}/api/fixtures/models`),
        fetch(`${API_URL}/api/groups/`),
      ]);

      if (!fixturesRes.ok) throw new Error(`Failed to fetch fixtures: ${fixturesRes.status}`);
      if (!modelsRes.ok) throw new Error(`Failed to fetch models: ${modelsRes.status}`);
      if (!groupsRes.ok) throw new Error(`Failed to fetch groups: ${groupsRes.status}`);

      const [fixturesData, modelsData, groupsData] = await Promise.all([
        fixturesRes.json(),
        modelsRes.json(),
        groupsRes.json(),
      ]);

      setFixtures(fixturesData);
      setFixtureModels(modelsData);
      setGroups(groupsData);

      // Fetch group memberships
      const groupMap = new Map<number, number[]>();
      for (const group of groupsData) {
        try {
          const membersRes = await fetch(`${API_URL}/api/groups/${group.id}/fixtures`);
          if (membersRes.ok) {
            const members = await membersRes.json();
            for (const fixture of members) {
              const existing = groupMap.get(fixture.id) || [];
              groupMap.set(fixture.id, [...existing, group.id]);
            }
          }
        } catch {
          // Ignore
        }
      }
      setFixtureGroups(groupMap);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      if (findIntervalRef.current) clearInterval(findIntervalRef.current);
    };
  }, []);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsAddDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // === Helper Functions ===

  const getModel = (modelId: number) => fixtureModels.find(m => m.id === modelId);

  const getDmxRange = (fixture: Fixture) => {
    // If fixture has a secondary channel (merged), show both
    if (fixture.secondary_dmx_channel) {
      return `${fixture.dmx_channel_start}+${fixture.secondary_dmx_channel}`;
    }
    const model = getModel(fixture.fixture_model_id);
    if (!model) return `${fixture.dmx_channel_start}`;
    const endChannel = fixture.dmx_channel_start + model.dmx_footprint - 1;
    if (model.dmx_footprint === 1) return `${fixture.dmx_channel_start}`;
    return `${fixture.dmx_channel_start}-${endChannel}`;
  };

  // === Sorting Functions ===

  const toggleSort = (column: SortColumn) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection('asc');
    }
  };

  const sortedFixtures = [...fixtures].sort((a, b) => {
    let comparison = 0;

    switch (sortColumn) {
      case 'name':
        comparison = a.name.localeCompare(b.name);
        break;
      case 'model':
        const modelA = getModel(a.fixture_model_id);
        const modelB = getModel(b.fixture_model_id);
        const nameA = modelA ? `${modelA.manufacturer} ${modelA.model}` : '';
        const nameB = modelB ? `${modelB.manufacturer} ${modelB.model}` : '';
        comparison = nameA.localeCompare(nameB);
        break;
      case 'dmx':
        comparison = a.dmx_channel_start - b.dmx_channel_start;
        break;
    }

    return sortDirection === 'asc' ? comparison : -comparison;
  });

  const SortIcon = ({ column }: { column: SortColumn }) => (
    <span className="ml-1 inline-flex flex-col text-[10px] leading-none">
      <span className={sortColumn === column && sortDirection === 'asc' ? 'text-amber-400' : 'text-[#636366]'}>▲</span>
      <span className={sortColumn === column && sortDirection === 'desc' ? 'text-amber-400' : 'text-[#636366]'}>▼</span>
    </span>
  );

  // === Fixture Merge Functions ===

  const canMergeFixtures = () => {
    if (selectedFixtureIds.size !== 2) return false;
    // Can only merge if neither fixture is already merged (no secondary channel)
    const selectedList = fixtures.filter(f => selectedFixtureIds.has(f.id));
    return selectedList.every(f => f.secondary_dmx_channel == null);
  };

  const canUnmergeFixtures = () => {
    // Can unmerge if any selected fixture has a secondary channel (not null/undefined)
    const selectedList = fixtures.filter(f => selectedFixtureIds.has(f.id));
    return selectedList.some(f => f.secondary_dmx_channel != null);
  };

  const openMergeModal = () => {
    // Find a tunable white model to use
    const tunableWhiteModel = fixtureModels.find(m => m.type === 'tunable_white');
    setMergeTargetModel(tunableWhiteModel || null);
    setIsMergeModalOpen(true);
  };

  const confirmMerge = async () => {
    if (selectedFixtureIds.size !== 2) return;

    const [firstId, secondId] = Array.from(selectedFixtureIds);
    const firstFixture = fixtures.find(f => f.id === firstId);
    const secondFixture = fixtures.find(f => f.id === secondId);

    if (!firstFixture || !secondFixture) return;

    // Primary is the one with lower DMX channel (comes first)
    const primaryId = firstFixture.dmx_channel_start < secondFixture.dmx_channel_start ? firstId : secondId;
    const secondaryId = primaryId === firstId ? secondId : firstId;

    try {
      const response = await fetch(`${API_URL}/api/fixtures/merge`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          primary_fixture_id: primaryId,
          secondary_fixture_id: secondaryId,
          target_model_id: mergeTargetModel?.id || null,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to merge fixtures');
      }

      await fetchData();
      setSelectedFixtureIds(new Set());
      setIsMergeModalOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to merge fixtures');
    }
  };

  const unmergeFixture = async (fixtureId: number) => {
    try {
      const response = await fetch(`${API_URL}/api/fixtures/${fixtureId}/unmerge`, {
        method: 'POST',
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to unmerge fixture');
      }

      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to unmerge fixture');
    }
  };

  const bulkUnmerge = async () => {
    const mergedFixtures = fixtures.filter(f => selectedFixtureIds.has(f.id) && f.secondary_dmx_channel !== null);
    for (const fixture of mergedFixtures) {
      await unmergeFixture(fixture.id);
    }
    setSelectedFixtureIds(new Set());
  };

  const getNextAvailableDmxChannel = () => {
    if (fixtures.length === 0) return 1;
    const usedChannels = new Set<number>();
    fixtures.forEach(f => {
      const model = getModel(f.fixture_model_id);
      const footprint = model?.dmx_footprint || 1;
      for (let i = 0; i < footprint; i++) {
        usedChannels.add(f.dmx_channel_start + i);
      }
    });
    for (let ch = 1; ch <= 512; ch++) {
      if (!usedChannels.has(ch)) return ch;
    }
    return 1;
  };

  // === Discovery Functions ===

  const startDiscovery = async () => {
    try {
      setDiscovery({
        phase: 'scanning',
        discoveryId: null,
        progress: 0,
        devicesFound: 0,
        discoveredDevices: [],
        error: null,
      });

      const response = await fetch(`${API_URL}/api/discovery/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ universe: 0 }),
      });

      if (!response.ok) throw new Error('Failed to start discovery');

      const data = await response.json();
      const discoveryId = data.discovery_id;

      setDiscovery(prev => ({ ...prev, discoveryId }));

      pollIntervalRef.current = setInterval(async () => {
        try {
          const progressRes = await fetch(`${API_URL}/api/discovery/progress/${discoveryId}`);
          if (!progressRes.ok) throw new Error('Failed to get progress');

          const progress = await progressRes.json();

          setDiscovery(prev => ({
            ...prev,
            progress: progress.progress_percent,
            devicesFound: progress.devices_found,
          }));

          if (progress.status === 'complete') {
            clearInterval(pollIntervalRef.current!);
            pollIntervalRef.current = null;

            const resultsRes = await fetch(`${API_URL}/api/discovery/results/${discoveryId}`);
            if (!resultsRes.ok) throw new Error('Failed to get results');

            const results = await resultsRes.json();

            const deviceRows: DiscoveredDeviceRow[] = results.devices.map((device: RDMDeviceInfo) => ({
              ...device,
              selected: false,
              configured_name: '',
              configured_model_id: null,
              configured_group_ids: [],
              merged_with: null,
              is_secondary: false,
              secondary_dmx_address: null,
              testing: false,
            }));

            setDiscovery(prev => ({
              ...prev,
              phase: 'configuring',
              discoveredDevices: deviceRows,
            }));
          }
        } catch (err) {
          console.error('Polling error:', err);
        }
      }, 500);
    } catch (err) {
      setDiscovery(prev => ({
        ...prev,
        phase: 'idle',
        error: err instanceof Error ? err.message : 'Discovery failed',
      }));
    }
  };

  const cancelDiscovery = async () => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }

    if (discovery.discoveryId) {
      try {
        await fetch(`${API_URL}/api/discovery/cancel/${discovery.discoveryId}`, { method: 'POST' });
      } catch {
        // Ignore
      }
    }

    setDiscovery(initialDiscoveryState);
  };

  const toggleDeviceSelection = (rdmUid: string) => {
    setDiscovery(prev => ({
      ...prev,
      discoveredDevices: prev.discoveredDevices.map(d =>
        d.rdm_uid === rdmUid ? { ...d, selected: !d.selected } : d
      ),
    }));
  };

  const toggleAllDevices = () => {
    const visibleDevices = discovery.discoveredDevices.filter(d => !d.is_secondary);
    const allSelected = visibleDevices.every(d => d.selected);
    setDiscovery(prev => ({
      ...prev,
      discoveredDevices: prev.discoveredDevices.map(d =>
        d.is_secondary ? d : { ...d, selected: !allSelected }
      ),
    }));
  };

  const updateDeviceName = (rdmUid: string, name: string) => {
    setDiscovery(prev => ({
      ...prev,
      discoveredDevices: prev.discoveredDevices.map(d =>
        d.rdm_uid === rdmUid ? { ...d, configured_name: name } : d
      ),
    }));
  };

  const updateDeviceModel = (rdmUid: string, modelId: number | null) => {
    if (!modelId) {
      // Clearing model - also unmerge if needed
      setDiscovery(prev => {
        const device = prev.discoveredDevices.find(d => d.rdm_uid === rdmUid);
        if (!device) return prev;

        return {
          ...prev,
          discoveredDevices: prev.discoveredDevices.map(d => {
            if (d.rdm_uid === rdmUid) {
              return { ...d, configured_model_id: null, merged_with: null, secondary_dmx_address: null };
            }
            // Unhide any secondary that was merged with this device
            if (d.is_secondary && device.merged_with === d.rdm_uid) {
              return { ...d, is_secondary: false };
            }
            return d;
          }),
        };
      });
      return;
    }

    const model = fixtureModels.find(m => m.id === modelId);
    if (!model) return;

    const footprint = model.dmx_footprint;

    setDiscovery(prev => {
      const device = prev.discoveredDevices.find(d => d.rdm_uid === rdmUid);
      if (!device) return prev;

      if (footprint === 1) {
        // Simple case: no merging needed
        let newName = device.configured_name;
        if (!device.configured_name) {
          newName = `${model.manufacturer} ${model.model} ${device.dmx_address}`;
        }
        return {
          ...prev,
          discoveredDevices: prev.discoveredDevices.map(d => {
            if (d.rdm_uid !== rdmUid) return d;
            return { ...d, configured_model_id: modelId, configured_name: newName };
          }),
        };
      }

      // Multi-channel: find consecutive channels to merge
      const startDmx = device.dmx_address;
      const channelsNeeded: string[] = [rdmUid];

      for (let i = 1; i < footprint; i++) {
        const nextDmx = startDmx + i;
        const nextDevice = prev.discoveredDevices.find(
          d => d.dmx_address === nextDmx && !d.is_secondary && d.rdm_uid !== rdmUid
        );
        if (nextDevice) {
          channelsNeeded.push(nextDevice.rdm_uid);
        }
      }

      if (channelsNeeded.length < footprint) {
        setError(`Cannot apply ${footprint}-channel model: need ${footprint} consecutive DMX channels starting at ${startDmx}, but only found ${channelsNeeded.length}.`);
        return prev;
      }

      // Apply merge
      let newName = device.configured_name;
      if (!device.configured_name) {
        newName = `${model.manufacturer} ${model.model} ${device.dmx_address}`;
      }

      return {
        ...prev,
        discoveredDevices: prev.discoveredDevices.map(d => {
          if (d.rdm_uid === rdmUid) {
            // Primary device
            const secondaryDmx = prev.discoveredDevices.find(dev => dev.rdm_uid === channelsNeeded[1])?.dmx_address ?? null;
            return {
              ...d,
              configured_model_id: modelId,
              configured_name: newName,
              merged_with: channelsNeeded[1],
              secondary_dmx_address: secondaryDmx,
            };
          }
          if (channelsNeeded.slice(1).includes(d.rdm_uid)) {
            // Secondary device(s)
            return {
              ...d,
              configured_model_id: null,
              is_secondary: true,
              merged_with: null,
              secondary_dmx_address: null,
            };
          }
          return d;
        }),
      };
    });
  };

  const applyBulkModel = (modelId: number) => {
    setBulkModelId(modelId);
    const model = fixtureModels.find(m => m.id === modelId);
    if (!model) return;

    const footprint = model.dmx_footprint;

    setDiscovery(prev => {
      // Get selected devices that aren't already secondaries, sorted by DMX address
      const selectedDevices = prev.discoveredDevices
        .filter(d => d.selected && !d.is_secondary)
        .sort((a, b) => a.dmx_address - b.dmx_address);

      if (footprint === 1) {
        // Simple case: no merging needed
        return {
          ...prev,
          discoveredDevices: prev.discoveredDevices.map(d => {
            if (!d.selected || d.is_secondary) return d;
            let newName = d.configured_name;
            if (!d.configured_name) {
              newName = `${model.manufacturer} ${model.model} ${d.dmx_address}`;
            }
            return { ...d, configured_model_id: modelId, configured_name: newName };
          }),
        };
      }

      // Multi-channel footprint: auto-merge consecutive channels
      const mergeGroups: string[][] = [];
      let currentGroup: string[] = [];
      let expectedNextDmx = -1;

      for (const device of selectedDevices) {
        if (expectedNextDmx === -1 || device.dmx_address === expectedNextDmx) {
          currentGroup.push(device.rdm_uid);
          expectedNextDmx = device.dmx_address + 1;

          // Group is complete
          if (currentGroup.length === footprint) {
            mergeGroups.push([...currentGroup]);
            currentGroup = [];
            expectedNextDmx = -1;
          }
        } else {
          // Non-consecutive: save incomplete group and start new one
          if (currentGroup.length > 0) {
            mergeGroups.push([...currentGroup]);
          }
          currentGroup = [device.rdm_uid];
          expectedNextDmx = device.dmx_address + 1;

          if (currentGroup.length === footprint) {
            mergeGroups.push([...currentGroup]);
            currentGroup = [];
            expectedNextDmx = -1;
          }
        }
      }

      // Handle any remaining incomplete group
      if (currentGroup.length > 0) {
        mergeGroups.push([...currentGroup]);
      }

      // Check for incomplete groups (leftovers)
      const incompleteGroups = mergeGroups.filter(g => g.length < footprint);
      if (incompleteGroups.length > 0) {
        const leftoverCount = incompleteGroups.reduce((sum, g) => sum + g.length, 0);
        setError(`${leftoverCount} channel(s) couldn't be merged (${footprint}-channel fixtures require consecutive DMX addresses). Please select a different model for these channels.`);
      }

      // Build the updated devices array
      const updatedDevices = prev.discoveredDevices.map(d => {
        // Find which merge group this device belongs to
        for (const group of mergeGroups) {
          const indexInGroup = group.indexOf(d.rdm_uid);
          if (indexInGroup !== -1) {
            const primaryUid = group[0];
            const primaryDevice = prev.discoveredDevices.find(dev => dev.rdm_uid === primaryUid);
            const isComplete = group.length === footprint;

            if (indexInGroup === 0) {
              // Primary device
              let newName = d.configured_name;
              if (!d.configured_name) {
                newName = `${model.manufacturer} ${model.model} ${d.dmx_address}`;
              }
              // Get secondary DMX address if group is complete
              const secondaryDmx = isComplete && group.length > 1
                ? prev.discoveredDevices.find(dev => dev.rdm_uid === group[1])?.dmx_address ?? null
                : null;
              return {
                ...d,
                configured_model_id: isComplete ? modelId : null,
                configured_name: isComplete ? newName : d.configured_name,
                merged_with: isComplete && group.length > 1 ? group[1] : null,
                secondary_dmx_address: secondaryDmx,
                is_secondary: false,
              };
            } else {
              // Secondary device
              return {
                ...d,
                configured_model_id: null,
                is_secondary: isComplete,
                merged_with: null,
                secondary_dmx_address: null,
              };
            }
          }
        }
        return d;
      });

      return { ...prev, discoveredDevices: updatedDevices };
    });
  };

  const applyBulkGroup = (groupId: number, add: boolean) => {
    setDiscovery(prev => ({
      ...prev,
      discoveredDevices: prev.discoveredDevices.map(d => {
        if (!d.selected) return d;
        const newGroupIds = add
          ? d.configured_group_ids.includes(groupId) ? d.configured_group_ids : [...d.configured_group_ids, groupId]
          : d.configured_group_ids.filter(id => id !== groupId);
        return { ...d, configured_group_ids: newGroupIds };
      }),
    }));
  };

  const testFixture = async (device: DiscoveredDeviceRow) => {
    try {
      setDiscovery(prev => ({
        ...prev,
        discoveredDevices: prev.discoveredDevices.map(d =>
          d.rdm_uid === device.rdm_uid ? { ...d, testing: true } : d
        ),
      }));

      await fetch(`${API_URL}/api/discovery/test-dmx`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          universe: 0,
          channel: device.dmx_address,
          value: 255,
          secondary_channel: device.secondary_dmx_address,
        }),
      });
    } catch (err) {
      console.error('Failed to test fixture:', err);
    }
  };

  const stopTestFixture = async (device: DiscoveredDeviceRow) => {
    try {
      await fetch(`${API_URL}/api/discovery/test-dmx/off`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          universe: 0,
          channel: device.dmx_address,
          secondary_channel: device.secondary_dmx_address,
        }),
      });

      setDiscovery(prev => ({
        ...prev,
        discoveredDevices: prev.discoveredDevices.map(d =>
          d.rdm_uid === device.rdm_uid ? { ...d, testing: false } : d
        ),
      }));
    } catch (err) {
      console.error('Failed to stop test:', err);
    }
  };

  const handleDragStart = (rdmUid: string) => setDraggedDevice(rdmUid);
  const handleDragOver = (e: React.DragEvent) => e.preventDefault();

  const handleDrop = (targetRdmUid: string) => {
    if (!draggedDevice || draggedDevice === targetRdmUid) {
      setDraggedDevice(null);
      return;
    }

    setDiscovery(prev => {
      const draggedDev = prev.discoveredDevices.find(d => d.rdm_uid === draggedDevice);
      const targetDev = prev.discoveredDevices.find(d => d.rdm_uid === targetRdmUid);

      if (!draggedDev || !targetDev) return prev;

      return {
        ...prev,
        discoveredDevices: prev.discoveredDevices.map(d => {
          if (d.rdm_uid === targetRdmUid) {
            return { ...d, merged_with: draggedDevice, secondary_dmx_address: draggedDev.dmx_address };
          }
          if (d.rdm_uid === draggedDevice) {
            return { ...d, is_secondary: true };
          }
          return d;
        }),
      };
    });

    setDraggedDevice(null);
  };

  const unmergeDevice = (rdmUid: string) => {
    setDiscovery(prev => {
      const device = prev.discoveredDevices.find(d => d.rdm_uid === rdmUid);
      if (!device || !device.merged_with) return prev;

      const secondaryUid = device.merged_with;

      return {
        ...prev,
        discoveredDevices: prev.discoveredDevices.map(d => {
          if (d.rdm_uid === rdmUid) {
            return { ...d, merged_with: null, secondary_dmx_address: null };
          }
          if (d.rdm_uid === secondaryUid) {
            return { ...d, is_secondary: false };
          }
          return d;
        }),
      };
    });
  };

  const addDiscoveredFixtures = async () => {
    const toCreate = discovery.discoveredDevices.filter(
      d => !d.is_secondary && d.configured_model_id && d.configured_name
    );

    if (toCreate.length === 0) return;

    try {
      const response = await fetch(`${API_URL}/api/discovery/bulk-create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          fixtures: toCreate.map(d => ({
            rdm_uid: d.rdm_uid,
            name: d.configured_name,
            fixture_model_id: d.configured_model_id,
            dmx_channel_start: d.dmx_address,
            secondary_dmx_channel: d.secondary_dmx_address,
            group_ids: d.configured_group_ids,
          })),
        }),
      });

      if (!response.ok) throw new Error('Failed to create fixtures');

      await fetchData();
      setDiscovery(initialDiscoveryState);
    } catch (err) {
      setDiscovery(prev => ({
        ...prev,
        error: err instanceof Error ? err.message : 'Failed to create fixtures',
      }));
    }
  };

  // === Fixture CRUD ===

  const openCreateFixtureModal = () => {
    setEditingFixture(null);
    setFixtureFormData({
      ...emptyFixtureFormData,
      fixture_model_id: fixtureModels.length > 0 ? fixtureModels[0].id.toString() : '',
      dmx_channel_start: getNextAvailableDmxChannel().toString(),
    });
    setIsFixtureModalOpen(true);
  };

  const openEditFixtureModal = (fixture: Fixture) => {
    setEditingFixture(fixture);
    setFixtureFormData({
      name: fixture.name,
      fixture_model_id: fixture.fixture_model_id.toString(),
      dmx_channel_start: fixture.dmx_channel_start.toString(),
      dim_to_warm_enabled: fixture.dim_to_warm_enabled || false,
      dim_to_warm_max_cct: fixture.dim_to_warm_max_cct?.toString() || '',
      dim_to_warm_min_cct: fixture.dim_to_warm_min_cct?.toString() || '',
    });
    setIsFixtureModalOpen(true);
  };

  const handleSaveFixture = async () => {
    setIsSavingFixture(true);
    setError(null);

    try {
      const payload: Record<string, unknown> = {
        name: fixtureFormData.name,
        dmx_channel_start: parseInt(fixtureFormData.dmx_channel_start),
        dim_to_warm_enabled: fixtureFormData.dim_to_warm_enabled,
      };

      // Add dim-to-warm CCT overrides if provided
      if (fixtureFormData.dim_to_warm_max_cct) {
        payload.dim_to_warm_max_cct = parseInt(fixtureFormData.dim_to_warm_max_cct);
      }
      if (fixtureFormData.dim_to_warm_min_cct) {
        payload.dim_to_warm_min_cct = parseInt(fixtureFormData.dim_to_warm_min_cct);
      }

      if (!editingFixture) {
        payload.fixture_model_id = parseInt(fixtureFormData.fixture_model_id);
      }

      let response: Response;

      if (editingFixture) {
        response = await fetch(`${API_URL}/api/fixtures/${editingFixture.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      } else {
        response = await fetch(`${API_URL}/api/fixtures/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to save: ${response.status}`);
      }

      await fetchData();
      setIsFixtureModalOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save fixture');
    } finally {
      setIsSavingFixture(false);
    }
  };

  const handleDeleteFixture = async (id: number) => {
    setError(null);

    try {
      const response = await fetch(`${API_URL}/api/fixtures/${id}`, { method: 'DELETE' });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to delete: ${response.status}`);
      }

      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete fixture');
    } finally {
      setFixtureDeleteConfirm(null);
    }
  };

  const isFixtureFormValid = () => {
    if (!fixtureFormData.name.trim()) return false;
    if (!editingFixture && !fixtureFormData.fixture_model_id) return false;
    const dmxChannel = parseInt(fixtureFormData.dmx_channel_start);
    if (!dmxChannel || dmxChannel < 1 || dmxChannel > 512) return false;
    return true;
  };

  // === Model CRUD ===

  const openCreateModelModal = () => {
    setEditingModel(null);
    setModelFormData(emptyModelFormData);
    setIsModelModalOpen(true);
  };

  const openEditModelModal = (model: FixtureModel) => {
    setEditingModel(model);
    const singleCct = usesSingleCct(model.type) ? (model.cct_min_kelvin?.toString() || '') : '';
    setModelFormData({
      manufacturer: model.manufacturer,
      model: model.model,
      description: model.description,
      type: model.type,
      cct_kelvin: singleCct,
      cct_min_kelvin: model.cct_min_kelvin?.toString() || '',
      cct_max_kelvin: model.cct_max_kelvin?.toString() || '',
      mixing_type: model.mixing_type,
    });
    setIsModelModalOpen(true);
  };

  const handleSaveModel = async () => {
    setIsSavingModel(true);
    setError(null);

    try {
      let cctMin: number | null = null;
      let cctMax: number | null = null;

      if (usesCctRange(modelFormData.type)) {
        cctMin = parseInt(modelFormData.cct_min_kelvin) || null;
        cctMax = parseInt(modelFormData.cct_max_kelvin) || null;
      } else if (usesSingleCct(modelFormData.type)) {
        const singleCct = parseInt(modelFormData.cct_kelvin) || null;
        cctMin = singleCct;
        cctMax = singleCct;
      }

      const payload = {
        manufacturer: modelFormData.manufacturer,
        model: modelFormData.model,
        description: modelFormData.description || null,
        type: modelFormData.type,
        dmx_footprint: dmxFootprintByType[modelFormData.type],
        cct_min_kelvin: cctMin,
        cct_max_kelvin: cctMax,
        mixing_type: modelFormData.mixing_type,
      };

      let response: Response;

      if (editingModel) {
        response = await fetch(`${API_URL}/api/fixtures/models/${editingModel.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      } else {
        response = await fetch(`${API_URL}/api/fixtures/models`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to save: ${response.status}`);
      }

      await fetchData();
      setIsModelModalOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save fixture model');
    } finally {
      setIsSavingModel(false);
    }
  };

  const handleDeleteModel = async (id: number) => {
    setError(null);

    try {
      const response = await fetch(`${API_URL}/api/fixtures/models/${id}`, { method: 'DELETE' });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to delete: ${response.status}`);
      }

      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete fixture model');
    } finally {
      setModelDeleteConfirm(null);
    }
  };

  const isModelFormValid = () => {
    if (!modelFormData.manufacturer || !modelFormData.model) return false;

    if (usesCctRange(modelFormData.type)) {
      const minCct = parseInt(modelFormData.cct_min_kelvin);
      const maxCct = parseInt(modelFormData.cct_max_kelvin);
      if (!minCct || !maxCct || minCct < 1000 || maxCct < 1000 || minCct > maxCct) return false;
    } else if (usesSingleCct(modelFormData.type)) {
      const cct = parseInt(modelFormData.cct_kelvin);
      if (!cct || cct < 1000 || cct > 10000) return false;
    }

    return true;
  };

  // === Bulk Selection ===

  const toggleFixtureSelection = (fixtureId: number) => {
    setSelectedFixtureIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(fixtureId)) {
        newSet.delete(fixtureId);
      } else {
        newSet.add(fixtureId);
      }
      return newSet;
    });
  };

  const toggleAllFixtures = () => {
    if (selectedFixtureIds.size === fixtures.length) {
      setSelectedFixtureIds(new Set());
    } else {
      setSelectedFixtureIds(new Set(fixtures.map(f => f.id)));
    }
  };

  const bulkAddToGroup = async (groupId: number) => {
    const fixtureIdsToAdd = Array.from(selectedFixtureIds).filter(
      fixtureId => !(fixtureGroups.get(fixtureId) || []).includes(groupId)
    );

    for (const fixtureId of fixtureIdsToAdd) {
      try {
        await fetch(`${API_URL}/api/groups/${groupId}/fixtures`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ fixture_id: fixtureId }),
        });
      } catch {
        // Continue
      }
    }
    await fetchData();
  };

  const bulkRemoveFromGroup = async (groupId: number) => {
    const fixtureIdsToRemove = Array.from(selectedFixtureIds).filter(
      fixtureId => (fixtureGroups.get(fixtureId) || []).includes(groupId)
    );

    for (const fixtureId of fixtureIdsToRemove) {
      try {
        await fetch(`${API_URL}/api/groups/${groupId}/fixtures/${fixtureId}`, { method: 'DELETE' });
      } catch {
        // Continue
      }
    }
    await fetchData();
  };

  const bulkToggleGroup = async (groupId: number) => {
    const selectedFixturesList = fixtures.filter(f => selectedFixtureIds.has(f.id));
    const allHaveGroup = selectedFixturesList.every(f => (fixtureGroups.get(f.id) || []).includes(groupId));

    if (allHaveGroup) {
      await bulkRemoveFromGroup(groupId);
    } else {
      await bulkAddToGroup(groupId);
    }
  };

  const bulkChangeModel = async (modelId: number) => {
    const fixtureIdsToUpdate = Array.from(selectedFixtureIds);

    for (const fixtureId of fixtureIdsToUpdate) {
      try {
        const response = await fetch(`${API_URL}/api/fixtures/${fixtureId}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ fixture_model_id: modelId }),
        });
        if (!response.ok) {
          console.error(`Failed to update fixture ${fixtureId}:`, response.status);
        }
      } catch (err) {
        console.error(`Failed to update fixture ${fixtureId}:`, err);
      }
    }

    // Reset select dropdown and refresh data
    setBulkModelSelectKey(prev => prev + 1);
    await fetchData();
  };

  const [bulkDeleteConfirm, setBulkDeleteConfirm] = useState(false);

  const bulkDeleteFixtures = async () => {
    const fixtureIdsToDelete = Array.from(selectedFixtureIds);

    for (const fixtureId of fixtureIdsToDelete) {
      try {
        const response = await fetch(`${API_URL}/api/fixtures/${fixtureId}`, {
          method: 'DELETE',
        });
        if (!response.ok) {
          console.error(`Failed to delete fixture ${fixtureId}:`, response.status);
        }
      } catch (err) {
        console.error(`Failed to delete fixture ${fixtureId}:`, err);
      }
    }

    // Clear selection and refresh data
    setSelectedFixtureIds(new Set());
    setBulkDeleteConfirm(false);
    await fetchData();
  };

  // === Inline Editing ===

  const startEdit = (fixtureId: number, field: 'name' | 'model') => {
    const fixture = fixtures.find(f => f.id === fixtureId);
    if (!fixture) return;

    if (field === 'name') {
      setEditValue(fixture.name);
    } else {
      setEditValue(fixture.fixture_model_id.toString());
    }
    setEditingField({ fixtureId, field });
  };

  const cancelEdit = () => {
    setEditingField(null);
    setEditValue('');
  };

  const saveEdit = async (overrideValue?: string) => {
    if (!editingField) return;

    const fixture = fixtures.find(f => f.id === editingField.fixtureId);
    if (!fixture) {
      cancelEdit();
      return;
    }

    const valueToSave = overrideValue ?? editValue;

    try {
      const payload: Record<string, unknown> = {};

      if (editingField.field === 'name') {
        if (!valueToSave.trim()) {
          cancelEdit();
          return;
        }
        payload.name = valueToSave.trim();
      } else {
        payload.fixture_model_id = parseInt(valueToSave);
      }

      const response = await fetch(`${API_URL}/api/fixtures/${fixture.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to save: ${response.status}`);
      }

      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save');
    } finally {
      cancelEdit();
    }
  };

  const handleEditKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') saveEdit();
    else if (e.key === 'Escape') cancelEdit();
  };

  // === Find Mode ===

  const toggleFindMode = async (fixtureId: number) => {
    if (findingFixtureId === fixtureId) {
      stopFindMode();
      return;
    }

    if (findingFixtureId !== null) {
      await stopFindMode();
    }

    setFindingFixtureId(fixtureId);
    setFindState(true);

    await setFixtureBrightness(fixtureId, 1.0);

    findIntervalRef.current = setInterval(async () => {
      setFindState(prev => {
        const newState = !prev;
        setFixtureBrightness(fixtureId, newState ? 1.0 : 0);
        return newState;
      });
    }, 2000);
  };

  const stopFindMode = async () => {
    if (findIntervalRef.current) {
      clearInterval(findIntervalRef.current);
      findIntervalRef.current = null;
    }

    if (findingFixtureId !== null) {
      await setFixtureBrightness(findingFixtureId, 0);
    }

    setFindingFixtureId(null);
    setFindState(false);
  };

  const setFixtureBrightness = async (fixtureId: number, brightness: number) => {
    try {
      await fetch(`${API_URL}/api/control/fixtures/${fixtureId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ brightness }),
      });
    } catch (err) {
      console.error('Failed to set fixture brightness:', err);
    }
  };

  const allFixturesSelected = fixtures.length > 0 && selectedFixtureIds.size === fixtures.length;

  if (isLoading) {
    return (
      <div className="p-8 flex items-center justify-center">
        <div className="text-[#636366]">Loading...</div>
      </div>
    );
  }

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold">Fixtures</h1>
          <p className="text-[#636366] mt-1">Manage fixtures and fixture models</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 bg-[#1a1a1f] p-1 rounded-lg w-fit">
        <button
          onClick={() => setActiveTab('fixtures')}
          className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
            activeTab === 'fixtures'
              ? 'bg-white text-black'
              : 'text-[#a1a1a6] hover:text-white'
          }`}
        >
          Fixtures
        </button>
        <button
          onClick={() => setActiveTab('models')}
          className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
            activeTab === 'models'
              ? 'bg-white text-black'
              : 'text-[#a1a1a6] hover:text-white'
          }`}
        >
          Fixture Models
        </button>
      </div>

      {/* Error Banner */}
      {(error || discovery.error) && (
        <div className="mb-6 px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
          {error || discovery.error}
        </div>
      )}

      {/* Fixtures Tab */}
      {activeTab === 'fixtures' && (
        <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] overflow-hidden">
          {discovery.phase === 'scanning' ? (
            <div className="p-12 flex flex-col items-center justify-center">
              <div className="w-16 h-16 mb-6 text-amber-500 animate-pulse">
                <svg fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
                </svg>
              </div>
              <h2 className="text-xl font-semibold mb-2">Discovering Fixtures</h2>
              <p className="text-[#636366] mb-6">Using RDM to find fixtures on the DMX network...</p>

              <div className="w-64 h-2 bg-[#2a2a2f] rounded-full overflow-hidden mb-4">
                <div
                  className="h-full bg-amber-500 transition-all duration-300"
                  style={{ width: `${discovery.progress}%` }}
                />
              </div>
              <div className="text-sm text-[#636366] mb-6">
                {discovery.progress}% - {discovery.devicesFound} device{discovery.devicesFound !== 1 ? 's' : ''} found
              </div>

              <button onClick={cancelDiscovery} className="px-4 py-2 text-[#a1a1a6] hover:text-white transition-colors">
                Cancel
              </button>
            </div>
          ) : discovery.phase === 'configuring' ? (
            <div>
              <div className="px-6 py-4 border-b border-[#2a2a2f] flex items-center justify-between">
                <div>
                  <h2 className="font-semibold">Configure Discovered Devices</h2>
                  <p className="text-sm text-[#636366]">{discovery.discoveredDevices.filter(d => !d.is_secondary).length} devices found</p>
                </div>
                <div className="flex items-center gap-3">
                  <button onClick={cancelDiscovery} className="px-4 py-2 text-[#a1a1a6] hover:text-white transition-colors">
                    Cancel
                  </button>
                  <button
                    onClick={addDiscoveredFixtures}
                    disabled={!discovery.discoveredDevices.some(d => !d.is_secondary && d.configured_model_id && d.configured_name)}
                    className="px-4 py-2 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-500/50 disabled:cursor-not-allowed text-black font-medium rounded-lg transition-colors"
                  >
                    Add {discovery.discoveredDevices.filter(d => !d.is_secondary && d.configured_model_id && d.configured_name).length} Fixtures
                  </button>
                </div>
              </div>

              {/* Bulk Actions */}
              {discovery.discoveredDevices.some(d => d.selected && !d.is_secondary) && (
                <div className="px-6 py-3 bg-blue-500/10 border-b border-blue-500/30 flex items-center gap-4">
                  <span className="text-blue-400 text-sm font-medium">
                    {discovery.discoveredDevices.filter(d => d.selected && !d.is_secondary).length} selected
                  </span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-[#a1a1a6]">Apply model:</span>
                    <select
                      value={bulkModelId || ''}
                      onChange={(e) => {
                        if (e.target.value === '__new__') {
                          openCreateModelModal();
                        } else if (e.target.value) {
                          applyBulkModel(parseInt(e.target.value));
                        }
                      }}
                      className="px-2 py-1 bg-[#2a2a2f] border border-[#3a3a3f] rounded text-sm focus:outline-none focus:border-amber-500/50"
                    >
                      <option value="">Select model...</option>
                      {fixtureModels.map(m => (
                        <option key={m.id} value={m.id}>{m.manufacturer} {m.model}</option>
                      ))}
                      <option value="__new__">+ Add Fixture Model...</option>
                    </select>
                  </div>
                  {groups.length > 0 && (
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-[#a1a1a6]">Groups:</span>
                      <div className="flex gap-1">
                        {groups.map(group => (
                          <button
                            key={group.id}
                            onClick={() => {
                              const selectedDevs = discovery.discoveredDevices.filter(d => d.selected && !d.is_secondary);
                              const allHave = selectedDevs.every(d => d.configured_group_ids.includes(group.id));
                              applyBulkGroup(group.id, !allHave);
                            }}
                            className={`px-2 py-0.5 text-xs rounded-full transition-colors ${
                              discovery.discoveredDevices.filter(d => d.selected && !d.is_secondary).every(d => d.configured_group_ids.includes(group.id))
                                ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                                : 'bg-[#2a2a2f] text-[#a1a1a6] hover:text-white hover:bg-[#3a3a3f]'
                            }`}
                          >
                            {group.name}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              <table className="w-full">
                <thead>
                  <tr className="border-b border-[#2a2a2f]">
                    <th className="px-4 py-3 w-12">
                      <input
                        type="checkbox"
                        checked={discovery.discoveredDevices.filter(d => !d.is_secondary).every(d => d.selected)}
                        onChange={toggleAllDevices}
                        className="w-4 h-4 rounded border-[#3a3a3f] bg-[#111113] text-amber-500 focus:ring-amber-500/50"
                      />
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">DMX</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Fixture Model</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Name</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Groups</th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-[#636366] uppercase tracking-wider">Test</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#2a2a2f]">
                  {discovery.discoveredDevices.filter(d => !d.is_secondary).map((device) => (
                    <tr
                      key={device.rdm_uid}
                      draggable
                      onDragStart={() => handleDragStart(device.rdm_uid)}
                      onDragOver={handleDragOver}
                      onDrop={() => handleDrop(device.rdm_uid)}
                      className={`hover:bg-white/[0.02] transition-colors ${device.selected ? 'bg-blue-500/5' : ''} ${draggedDevice === device.rdm_uid ? 'opacity-50' : ''}`}
                    >
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          checked={device.selected}
                          onChange={() => toggleDeviceSelection(device.rdm_uid)}
                          className="w-4 h-4 rounded border-[#3a3a3f] bg-[#111113] text-amber-500 focus:ring-amber-500/50"
                        />
                      </td>
                      <td className="px-4 py-3">
                        <div className="font-mono text-sm">
                          {device.dmx_address}
                          {device.secondary_dmx_address && (
                            <span className="text-amber-400 ml-1">+{device.secondary_dmx_address}</span>
                          )}
                        </div>
                        {device.merged_with && (
                          <button onClick={() => unmergeDevice(device.rdm_uid)} className="text-xs text-amber-400 hover:text-amber-300">
                            Unmerge
                          </button>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <select
                          value={device.configured_model_id || ''}
                          onChange={(e) => {
                            if (e.target.value === '__new__') {
                              openCreateModelModal();
                            } else {
                              updateDeviceModel(device.rdm_uid, e.target.value ? parseInt(e.target.value) : null);
                            }
                          }}
                          className="w-full px-2 py-1.5 bg-[#2a2a2f] border border-[#3a3a3f] rounded text-sm focus:outline-none focus:border-amber-500/50"
                        >
                          <option value="">Select model...</option>
                          {fixtureModels.map(m => (
                            <option key={m.id} value={m.id}>{m.manufacturer} {m.model}</option>
                          ))}
                          <option value="__new__">+ Add Fixture Model...</option>
                        </select>
                      </td>
                      <td className="px-4 py-3">
                        <input
                          type="text"
                          value={device.configured_name}
                          onChange={(e) => updateDeviceName(device.rdm_uid, e.target.value)}
                          placeholder="Fixture name..."
                          className="w-full px-2 py-1.5 bg-[#2a2a2f] border border-[#3a3a3f] rounded text-sm focus:outline-none focus:border-amber-500/50"
                        />
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1">
                          {groups.map(group => (
                            <button
                              key={group.id}
                              onClick={() => {
                                const has = device.configured_group_ids.includes(group.id);
                                setDiscovery(prev => ({
                                  ...prev,
                                  discoveredDevices: prev.discoveredDevices.map(d =>
                                    d.rdm_uid === device.rdm_uid
                                      ? { ...d, configured_group_ids: has ? d.configured_group_ids.filter(id => id !== group.id) : [...d.configured_group_ids, group.id] }
                                      : d
                                  ),
                                }));
                              }}
                              className={`px-2 py-0.5 text-xs rounded-full transition-colors ${
                                device.configured_group_ids.includes(group.id)
                                  ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                                  : 'bg-[#2a2a2f] text-[#a1a1a6] hover:text-white hover:bg-[#3a3a3f]'
                              }`}
                            >
                              {group.name}
                            </button>
                          ))}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onMouseDown={() => testFixture(device)}
                          onMouseUp={() => stopTestFixture(device)}
                          onMouseLeave={() => device.testing && stopTestFixture(device)}
                          className={`p-2 rounded-lg transition-colors ${
                            device.testing ? 'text-amber-400 bg-amber-500/20' : 'text-[#636366] hover:text-amber-400 hover:bg-amber-500/10'
                          }`}
                          title="Hold to test"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 18v-5.25m0 0a6.01 6.01 0 001.5-.189m-1.5.189a6.01 6.01 0 01-1.5-.189m3.75 7.478a12.06 12.06 0 01-4.5 0m3.75 2.383a14.406 14.406 0 01-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 10-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <>
              {/* Section Header */}
              <div className="px-6 py-4 border-b border-[#2a2a2f] flex items-center justify-between">
                <h2 className="font-semibold">Fixture Instances</h2>
                <div className="relative" ref={dropdownRef}>
                  <div className="flex items-stretch">
                    {/* Main button - triggers discovery directly */}
                    <button
                      onClick={() => {
                        startDiscovery();
                      }}
                      disabled={discovery.phase !== 'idle'}
                      className="flex items-center gap-2 px-4 py-2 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-500/50 disabled:cursor-not-allowed text-black font-medium rounded-l-lg transition-colors"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
                      </svg>
                      Discover via RDM
                    </button>
                    {/* Separator */}
                    <div className="w-px bg-amber-600/50" />
                    {/* Dropdown toggle */}
                    <button
                      onClick={() => setIsAddDropdownOpen(!isAddDropdownOpen)}
                      disabled={discovery.phase !== 'idle'}
                      className="flex items-center px-2 py-2 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-500/50 disabled:cursor-not-allowed text-black rounded-r-lg transition-colors"
                    >
                      <svg className={`w-4 h-4 transition-transform ${isAddDropdownOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
                      </svg>
                    </button>
                  </div>
                  {isAddDropdownOpen && (
                    <div className="absolute right-0 mt-1 w-48 bg-[#1a1a1f] border border-[#2a2a2f] rounded-lg shadow-lg z-10 overflow-hidden">
                      <button
                        onClick={() => {
                          startDiscovery();
                          setIsAddDropdownOpen(false);
                        }}
                        className="w-full px-4 py-2.5 text-left text-sm text-white hover:bg-amber-500/20 transition-colors flex items-center gap-2"
                      >
                        <svg className="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
                        </svg>
                        Discover via RDM
                      </button>
                      <button
                        onClick={() => {
                          openCreateFixtureModal();
                          setIsAddDropdownOpen(false);
                        }}
                        disabled={fixtureModels.length === 0}
                        className="w-full px-4 py-2.5 text-left text-sm text-white hover:bg-white/5 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
                      >
                        <svg className="w-4 h-4 text-[#636366]" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                        </svg>
                        Add Manually
                      </button>
                    </div>
                  )}
                </div>
              </div>

              <table className="w-full">
                <thead>
                  {selectedFixtureIds.size > 0 ? (
                    <tr className="border-b border-blue-500/30 bg-blue-500/10">
                      <th className="px-6 py-3 w-12">
                        <input
                          type="checkbox"
                          checked={allFixturesSelected}
                          onChange={toggleAllFixtures}
                          className="w-4 h-4 rounded border-[#3a3a3f] bg-[#111113] text-amber-500 focus:ring-amber-500/50"
                        />
                      </th>
                      <th className="px-6 py-3 text-left" colSpan={6}>
                        <div className="flex items-center flex-wrap gap-3">
                          <span className="text-blue-400 font-medium text-sm">{selectedFixtureIds.size} selected</span>
                          {/* Model dropdown */}
                          <select
                            key={bulkModelSelectKey}
                            onChange={(e) => {
                              if (e.target.value === '__new__') {
                                openCreateModelModal();
                                setBulkModelSelectKey(prev => prev + 1);
                              } else if (e.target.value) {
                                bulkChangeModel(parseInt(e.target.value));
                              }
                            }}
                            defaultValue=""
                            className="px-2 py-1 text-xs bg-[#2a2a2f] border border-[#3a3a3f] rounded text-white focus:outline-none focus:border-amber-500/50"
                          >
                            <option value="" disabled>Change model...</option>
                            {fixtureModels.map(m => (
                              <option key={m.id} value={m.id}>{m.manufacturer} {m.model}</option>
                            ))}
                            <option value="__new__">+ Add Fixture Model...</option>
                          </select>
                          {/* Groups selector */}
                          {groups.length > 0 && (
                            <div className="flex items-center gap-2">
                              <span className="text-xs text-[#a1a1a6]">Groups:</span>
                              <div className="flex flex-wrap gap-1">
                                {groups.map(group => {
                                  const selectedFixturesList = fixtures.filter(f => selectedFixtureIds.has(f.id));
                                  const allHaveGroup = selectedFixturesList.every(f => (fixtureGroups.get(f.id) || []).includes(group.id));
                                  const someHaveGroup = selectedFixturesList.some(f => (fixtureGroups.get(f.id) || []).includes(group.id));

                                  return (
                                    <button
                                      key={group.id}
                                      onClick={() => bulkToggleGroup(group.id)}
                                      className={`px-2 py-0.5 text-xs rounded-full transition-colors ${
                                        allHaveGroup
                                          ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                                          : someHaveGroup
                                            ? 'bg-amber-500/10 text-amber-400/60 border border-amber-500/20'
                                            : 'bg-[#2a2a2f] text-[#a1a1a6] hover:text-white hover:bg-[#3a3a3f]'
                                      }`}
                                      title={allHaveGroup ? `Remove all from ${group.name}` : `Add all to ${group.name}`}
                                    >
                                      {group.name}
                                    </button>
                                  );
                                })}
                              </div>
                            </div>
                          )}
                          {/* Spacer to push actions to the right */}
                          <div className="flex-1 min-w-4" />
                          {/* Action buttons */}
                          <div className="flex items-center flex-wrap gap-2">
                            {/* Merge button - only show when exactly 2 unmerged fixtures selected */}
                            {canMergeFixtures() && (
                              <button
                                onClick={openMergeModal}
                                className="px-2 py-0.5 text-xs rounded bg-purple-500/20 text-purple-400 border border-purple-500/30 hover:bg-purple-500/30 transition-colors"
                              >
                                Merge Channels
                              </button>
                            )}
                            {/* Unmerge button - show when any selected fixture has secondary channel */}
                            {canUnmergeFixtures() && (
                              <button
                                onClick={bulkUnmerge}
                                className="px-2 py-0.5 text-xs rounded bg-orange-500/20 text-orange-400 border border-orange-500/30 hover:bg-orange-500/30 transition-colors"
                              >
                                Unmerge
                              </button>
                            )}
                            {/* Delete button */}
                            {bulkDeleteConfirm ? (
                              <div className="flex items-center gap-1">
                                <span className="text-xs text-red-400">Delete {selectedFixtureIds.size}?</span>
                                <button
                                  onClick={bulkDeleteFixtures}
                                  className="px-2 py-0.5 text-xs rounded bg-red-500 text-white hover:bg-red-600 transition-colors"
                                >
                                  Yes
                                </button>
                                <button
                                  onClick={() => setBulkDeleteConfirm(false)}
                                  className="px-2 py-0.5 text-xs rounded bg-[#3a3a3f] text-white hover:bg-[#4a4a4f] transition-colors"
                                >
                                  No
                                </button>
                              </div>
                            ) : (
                              <button
                                onClick={() => setBulkDeleteConfirm(true)}
                                className="px-2 py-0.5 text-xs rounded bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30 transition-colors"
                              >
                                Delete
                              </button>
                            )}
                            <button
                              onClick={() => {
                                setSelectedFixtureIds(new Set());
                                setBulkDeleteConfirm(false);
                              }}
                              className="px-3 py-1 bg-amber-500 hover:bg-amber-600 text-black text-xs font-medium rounded-lg transition-colors"
                            >
                              Done
                            </button>
                          </div>
                        </div>
                      </th>
                    </tr>
                  ) : (
                    <tr className="border-b border-[#2a2a2f]">
                      <th className="px-6 py-4 w-12">
                        <input
                          type="checkbox"
                          checked={allFixturesSelected}
                          onChange={toggleAllFixtures}
                          className="w-4 h-4 rounded border-[#3a3a3f] bg-[#111113] text-amber-500 focus:ring-amber-500/50"
                        />
                      </th>
                      <th
                        className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider cursor-pointer hover:text-[#8e8e93] select-none"
                        onClick={() => toggleSort('name')}
                      >
                        <span className="inline-flex items-center">Name<SortIcon column="name" /></span>
                      </th>
                      <th
                        className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider cursor-pointer hover:text-[#8e8e93] select-none"
                        onClick={() => toggleSort('model')}
                      >
                        <span className="inline-flex items-center">Fixture Model<SortIcon column="model" /></span>
                      </th>
                      <th
                        className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider cursor-pointer hover:text-[#8e8e93] select-none"
                        onClick={() => toggleSort('dmx')}
                      >
                        <span className="inline-flex items-center">DMX Channel<SortIcon column="dmx" /></span>
                      </th>
                      <th className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Groups</th>
                      <th className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Status</th>
                      <th className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Actions</th>
                    </tr>
                  )}
                </thead>
                <tbody className="divide-y divide-[#2a2a2f]">
                  {sortedFixtures.map((fixture) => {
                    const model = getModel(fixture.fixture_model_id);
                    const fixtureGroupIds = fixtureGroups.get(fixture.id) || [];
                    const isEditingName = editingField?.fixtureId === fixture.id && editingField.field === 'name';
                    const isEditingModel = editingField?.fixtureId === fixture.id && editingField.field === 'model';
                    const isFinding = findingFixtureId === fixture.id;
                    const isMerged = fixture.secondary_dmx_channel != null;

                    return (
                      <tr
                        key={fixture.id}
                        className={`hover:bg-white/[0.02] transition-colors ${
                          selectedFixtureIds.has(fixture.id) ? 'bg-blue-500/5' : ''
                        } ${isFinding ? 'bg-amber-500/10' : ''}`}
                      >
                        <td className="px-6 py-4">
                          <input
                            type="checkbox"
                            checked={selectedFixtureIds.has(fixture.id)}
                            onChange={() => toggleFixtureSelection(fixture.id)}
                            className="w-4 h-4 rounded border-[#3a3a3f] bg-[#111113] text-amber-500 focus:ring-amber-500/50"
                          />
                        </td>
                        <td className="px-6 py-4">
                          {isEditingName ? (
                            <input
                              type="text"
                              value={editValue}
                              onChange={(e) => setEditValue(e.target.value)}
                              onKeyDown={handleEditKeyDown}
                              onBlur={() => saveEdit()}
                              autoFocus
                              className="w-full px-2 py-1 bg-[#1a1a1f] border border-amber-500/50 rounded text-white text-sm focus:outline-none focus:border-amber-500"
                            />
                          ) : (
                            <div onClick={() => startEdit(fixture.id, 'name')} className="font-medium cursor-pointer hover:text-amber-400 transition-colors" title="Click to edit">
                              {fixture.name}
                            </div>
                          )}
                        </td>
                        <td className="px-6 py-4">
                          {isEditingModel ? (
                            <select
                              value={editValue}
                              onChange={(e) => {
                                if (e.target.value === '__new__') {
                                  cancelEdit();
                                  openCreateModelModal();
                                } else {
                                  // Save immediately with the new value
                                  saveEdit(e.target.value);
                                }
                              }}
                              onBlur={() => cancelEdit()}
                              autoFocus
                              className="w-full px-2 py-1 bg-[#1a1a1f] border border-amber-500/50 rounded text-white text-sm focus:outline-none focus:border-amber-500"
                            >
                              {fixtureModels.map(m => (
                                <option key={m.id} value={m.id}>{m.manufacturer} {m.model}</option>
                              ))}
                              <option value="__new__" className="text-amber-400">+ Add Fixture Model...</option>
                            </select>
                          ) : model ? (
                            <div onClick={() => startEdit(fixture.id, 'model')} className="cursor-pointer hover:text-amber-400 transition-colors" title="Click to edit">
                              {model.manufacturer} {model.model}
                            </div>
                          ) : (
                            <span onClick={() => startEdit(fixture.id, 'model')} className="text-[#636366] cursor-pointer hover:text-amber-400">Unknown</span>
                          )}
                        </td>
                        <td className="px-6 py-4">
                          <div className="font-mono text-sm">
                            {fixture.dmx_channel_start}
                            {fixture.secondary_dmx_channel && (
                              <span className="text-amber-400">+{fixture.secondary_dmx_channel}</span>
                            )}
                          </div>
                          {fixture.secondary_dmx_channel && (
                            <button
                              onClick={() => unmergeFixture(fixture.id)}
                              className="text-xs text-amber-400 hover:text-amber-300 mt-0.5"
                            >
                              Unmerge
                            </button>
                          )}
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex flex-wrap gap-1">
                            {fixtureGroupIds.length > 0 ? (
                              fixtureGroupIds.map(groupId => {
                                const group = groups.find(g => g.id === groupId);
                                return group ? (
                                  <span
                                    key={groupId}
                                    className="px-2 py-0.5 text-xs rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20"
                                  >
                                    {group.name}
                                  </span>
                                ) : null;
                              })
                            ) : (
                              <span className="text-[#636366] text-sm">—</span>
                            )}
                          </div>
                        </td>
                        <td className="px-6 py-4">
                          <span className="inline-flex px-2.5 py-1 text-xs font-medium rounded-full bg-green-500/15 text-green-400 border border-green-500/30">
                            Active
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          <div className="flex items-center gap-3">
                            <button
                              onClick={() => toggleFindMode(fixture.id)}
                              className={`text-sm font-medium transition-colors ${
                                isFinding ? 'text-amber-400' : 'text-[#636366] hover:text-amber-400'
                              }`}
                            >
                              {isFinding ? 'Finding...' : 'Find'}
                            </button>
                            <button onClick={() => openEditFixtureModal(fixture)} className="text-sm font-medium text-[#636366] hover:text-white transition-colors">
                              Edit
                            </button>
                            {fixtureDeleteConfirm === fixture.id ? (
                              <div className="flex items-center gap-2">
                                <button onClick={() => handleDeleteFixture(fixture.id)} className="text-sm font-medium text-red-400 hover:text-red-300 transition-colors">
                                  Confirm
                                </button>
                                <button onClick={() => setFixtureDeleteConfirm(null)} className="text-sm font-medium text-[#636366] hover:text-white transition-colors">
                                  Cancel
                                </button>
                              </div>
                            ) : (
                              <button onClick={() => setFixtureDeleteConfirm(fixture.id)} className="text-sm font-medium text-[#636366] hover:text-red-400 transition-colors">
                                Delete
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {fixtures.length === 0 && (
                <div className="p-12 text-center text-[#636366]">
                  No fixtures configured. Add a fixture or discover devices to get started.
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Fixture Models Tab */}
      {activeTab === 'models' && (
        <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] overflow-hidden">
          {/* Section Header */}
          <div className="px-6 py-4 border-b border-[#2a2a2f] flex items-center justify-between">
            <h2 className="font-semibold">Fixture Models</h2>
            <button
              onClick={openCreateModelModal}
              className="px-4 py-2 bg-[#111113] hover:bg-[#1a1a1f] border border-[#2a2a2f] text-white font-medium rounded-lg transition-colors"
            >
              Add Model
            </button>
          </div>

          {fixtureModels.length === 0 ? (
            <div className="p-12 text-center text-[#636366]">
              <svg className="w-12 h-12 mx-auto mb-4 stroke-current" fill="none" strokeWidth="1" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
              <p className="mb-2">No fixture models defined</p>
              <p className="text-sm">Create your first fixture model to get started</p>
            </div>
          ) : (
            <table className="w-full">
              <thead>
                <tr className="border-b border-[#2a2a2f]">
                  <th className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Model</th>
                  <th className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Type</th>
                  <th className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">DMX</th>
                  <th className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">CCT</th>
                  <th className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Mixing</th>
                  <th className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#2a2a2f]">
                {fixtureModels.map((model) => (
                  <tr key={model.id} className="hover:bg-white/[0.02] transition-colors">
                    <td className="px-6 py-4">
                      <div>
                        <div className="font-medium">{model.manufacturer} {model.model}</div>
                        {model.description && (
                          <div className="text-sm text-[#636366] mt-0.5">{model.description}</div>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex px-2.5 py-1 text-xs font-medium rounded-md border ${typeLabels[model.type].color}`}>
                        {typeLabels[model.type].label}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className="font-mono text-sm">{model.dmx_footprint} ch</span>
                    </td>
                    <td className="px-6 py-4">
                      {model.type === 'non_dimmable' || !model.cct_min_kelvin ? (
                        <span className="text-[#636366]">N/A</span>
                      ) : model.cct_min_kelvin === model.cct_max_kelvin ? (
                        <span className="font-mono text-sm">{model.cct_min_kelvin}K</span>
                      ) : (
                        <span className="font-mono text-sm">{model.cct_min_kelvin}K - {model.cct_max_kelvin}K</span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <span className="text-sm text-[#a1a1a6]">{mixingLabels[model.mixing_type]}</span>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <button onClick={() => openEditModelModal(model)} className="text-sm font-medium text-[#636366] hover:text-white transition-colors">
                          Edit
                        </button>
                        {modelDeleteConfirm === model.id ? (
                          <div className="flex items-center gap-2">
                            <button onClick={() => handleDeleteModel(model.id)} className="text-sm font-medium text-red-400 hover:text-red-300 transition-colors">
                              Confirm
                            </button>
                            <button onClick={() => setModelDeleteConfirm(null)} className="text-sm font-medium text-[#636366] hover:text-white transition-colors">
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <button onClick={() => setModelDeleteConfirm(model.id)} className="text-sm font-medium text-[#636366] hover:text-red-400 transition-colors">
                            Delete
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Summary */}
      <div className="mt-4 text-sm text-[#636366]">
        {activeTab === 'fixtures'
          ? `${fixtures.length} fixture${fixtures.length !== 1 ? 's' : ''} configured`
          : `${fixtureModels.length} fixture model${fixtureModels.length !== 1 ? 's' : ''} configured`
        }
      </div>

      {/* Fixture Modal */}
      {isFixtureModalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] w-full max-w-md p-6">
            <h2 className="text-xl font-semibold mb-6">{editingFixture ? 'Edit Fixture' : 'Add Fixture'}</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-[#a1a1a6] mb-1.5">Name</label>
                <input
                  type="text"
                  value={fixtureFormData.name}
                  onChange={(e) => setFixtureFormData({ ...fixtureFormData, name: e.target.value })}
                  placeholder="e.g., Living Room Pendant"
                  className="w-full px-3 py-2 bg-[#111113] border border-[#2a2a2f] rounded-lg focus:outline-none focus:border-amber-500/50"
                />
              </div>

              {!editingFixture && (
                <div>
                  <label className="block text-sm font-medium text-[#a1a1a6] mb-1.5">Fixture Model</label>
                  <select
                    value={fixtureFormData.fixture_model_id}
                    onChange={(e) => {
                      if (e.target.value === '__new__') {
                        setIsFixtureModalOpen(false);
                        openCreateModelModal();
                      } else {
                        setFixtureFormData({ ...fixtureFormData, fixture_model_id: e.target.value });
                      }
                    }}
                    className="w-full px-3 py-2 bg-[#111113] border border-[#2a2a2f] rounded-lg focus:outline-none focus:border-amber-500/50"
                  >
                    {fixtureModels.map(m => (
                      <option key={m.id} value={m.id}>{m.manufacturer} {m.model}</option>
                    ))}
                    <option value="__new__">+ Add Fixture Model...</option>
                  </select>
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-[#a1a1a6] mb-1.5">DMX Start Channel</label>
                <input
                  type="number"
                  min="1"
                  max="512"
                  value={fixtureFormData.dmx_channel_start}
                  onChange={(e) => setFixtureFormData({ ...fixtureFormData, dmx_channel_start: e.target.value })}
                  className="w-full px-3 py-2 bg-[#111113] border border-[#2a2a2f] rounded-lg focus:outline-none focus:border-amber-500/50"
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <button onClick={() => setIsFixtureModalOpen(false)} className="px-4 py-2 text-[#a1a1a6] hover:text-white transition-colors">
                Cancel
              </button>
              <button
                onClick={handleSaveFixture}
                disabled={!isFixtureFormValid() || isSavingFixture}
                className="px-4 py-2 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-500/50 disabled:cursor-not-allowed text-black font-medium rounded-lg transition-colors"
              >
                {isSavingFixture ? 'Saving...' : editingFixture ? 'Save Changes' : 'Add Fixture'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Merge Confirmation Modal */}
      {isMergeModalOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-[#161619] border border-[#2a2a2f] rounded-2xl w-full max-w-md mx-4 shadow-2xl">
            <div className="flex items-center justify-between px-6 py-4 border-b border-[#2a2a2f]">
              <h2 className="text-lg font-semibold">Merge Fixtures</h2>
              <button onClick={() => setIsMergeModalOpen(false)} className="p-2 text-[#636366] hover:text-white hover:bg-white/10 rounded-lg transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="p-6 space-y-4">
              <p className="text-[#a1a1a6] text-sm">
                This will combine two single-channel fixtures into one dual-channel tunable white fixture.
              </p>

              {(() => {
                const selectedList = fixtures.filter(f => selectedFixtureIds.has(f.id));
                const sorted = [...selectedList].sort((a, b) => a.dmx_channel_start - b.dmx_channel_start);
                const primary = sorted[0];
                const secondary = sorted[1];

                return (
                  <div className="bg-[#111113] rounded-lg p-4 space-y-3">
                    <div className="flex justify-between text-sm">
                      <span className="text-[#636366]">Primary fixture:</span>
                      <span className="font-medium">{primary?.name} (CH {primary?.dmx_channel_start})</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-[#636366]">Secondary channel:</span>
                      <span className="font-medium">CH {secondary?.dmx_channel_start}</span>
                    </div>
                    <div className="flex justify-between text-sm">
                      <span className="text-[#636366]">Result:</span>
                      <span className="font-mono text-amber-400">CH {primary?.dmx_channel_start}+{secondary?.dmx_channel_start}</span>
                    </div>
                  </div>
                );
              })()}

              <div>
                <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Target Fixture Model</label>
                <select
                  value={mergeTargetModel?.id || ''}
                  onChange={(e) => {
                    const model = fixtureModels.find(m => m.id === parseInt(e.target.value));
                    setMergeTargetModel(model || null);
                  }}
                  className="w-full px-3 py-2 bg-[#111113] border border-[#2a2a2f] rounded-lg focus:outline-none focus:border-amber-500/50"
                >
                  <option value="">Keep current model</option>
                  {fixtureModels.filter(m => m.type === 'tunable_white').map(m => (
                    <option key={m.id} value={m.id}>{m.manufacturer} {m.model} (Tunable White)</option>
                  ))}
                </select>
                <p className="text-xs text-[#636366] mt-1">
                  {fixtureModels.filter(m => m.type === 'tunable_white').length === 0
                    ? 'No tunable white models defined. The fixture will keep its current model.'
                    : 'Select a tunable white model for the merged fixture.'}
                </p>
              </div>
            </div>

            <div className="flex justify-end gap-3 px-6 py-4 border-t border-[#2a2a2f]">
              <button
                onClick={() => setIsMergeModalOpen(false)}
                className="px-4 py-2 text-[#a1a1a6] hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmMerge}
                className="px-4 py-2 bg-purple-500 hover:bg-purple-600 text-white font-medium rounded-lg transition-colors"
              >
                Merge Fixtures
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Model Modal */}
      {isModelModalOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-[#161619] border border-[#2a2a2f] rounded-2xl w-full max-w-lg mx-4 shadow-2xl">
            <div className="flex items-center justify-between px-6 py-4 border-b border-[#2a2a2f]">
              <h2 className="text-lg font-semibold">{editingModel ? 'Edit Fixture Model' : 'New Fixture Model'}</h2>
              <button onClick={() => setIsModelModalOpen(false)} className="p-2 text-[#636366] hover:text-white hover:bg-white/10 rounded-lg transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <div className="p-6 space-y-5">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Manufacturer</label>
                  <input
                    type="text"
                    value={modelFormData.manufacturer}
                    onChange={(e) => setModelFormData({ ...modelFormData, manufacturer: e.target.value })}
                    className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white placeholder-[#636366] focus:outline-none focus:border-amber-500/50"
                    placeholder="e.g., Cree"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Model</label>
                  <input
                    type="text"
                    value={modelFormData.model}
                    onChange={(e) => setModelFormData({ ...modelFormData, model: e.target.value })}
                    className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white placeholder-[#636366] focus:outline-none focus:border-amber-500/50"
                    placeholder="e.g., TW-200"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Description</label>
                <input
                  type="text"
                  value={modelFormData.description || ''}
                  onChange={(e) => setModelFormData({ ...modelFormData, description: e.target.value || null })}
                  className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white placeholder-[#636366] focus:outline-none focus:border-amber-500/50"
                  placeholder="Optional description"
                />
              </div>

              <div className="grid grid-cols-3 gap-4">
                <div className="col-span-2">
                  <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Fixture Type</label>
                  <select
                    value={modelFormData.type}
                    onChange={(e) => setModelFormData({ ...modelFormData, type: e.target.value as FixtureType })}
                    className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white focus:outline-none focus:border-amber-500/50"
                  >
                    <option value="simple_dimmable">Simple Dimmable</option>
                    <option value="tunable_white">Tunable White</option>
                    <option value="dim_to_warm">Dim to Warm</option>
                    <option value="non_dimmable">Non-Dimmable</option>
                    <option value="other">Other</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-[#a1a1a6] mb-2">DMX Channels</label>
                  <div className="px-3 py-2.5 bg-[#0a0a0b] border border-[#2a2a2f] rounded-lg text-[#636366] font-mono">
                    {dmxFootprintByType[modelFormData.type]} ch
                  </div>
                </div>
              </div>

              {usesSingleCct(modelFormData.type) && (
                <div>
                  <label className="block text-sm font-medium text-[#a1a1a6] mb-2">
                    {modelFormData.type === 'dim_to_warm' ? 'Warm CCT (K)' : 'CCT (K)'}
                  </label>
                  <input
                    type="number"
                    min="1000"
                    max="10000"
                    value={modelFormData.cct_kelvin}
                    onChange={(e) => setModelFormData({ ...modelFormData, cct_kelvin: e.target.value })}
                    className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white placeholder-[#4a4a4f] focus:outline-none focus:border-amber-500/50"
                    placeholder={modelFormData.type === 'dim_to_warm' ? 'e.g., 2200' : 'e.g., 2700'}
                  />
                </div>
              )}

              {usesCctRange(modelFormData.type) && (
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Min CCT (K)</label>
                    <input
                      type="number"
                      min="1000"
                      max="10000"
                      value={modelFormData.cct_min_kelvin}
                      onChange={(e) => setModelFormData({ ...modelFormData, cct_min_kelvin: e.target.value })}
                      className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white placeholder-[#4a4a4f] focus:outline-none focus:border-amber-500/50"
                      placeholder="e.g., 2700"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Max CCT (K)</label>
                    <input
                      type="number"
                      min="1000"
                      max="10000"
                      value={modelFormData.cct_max_kelvin}
                      onChange={(e) => setModelFormData({ ...modelFormData, cct_max_kelvin: e.target.value })}
                      className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white placeholder-[#4a4a4f] focus:outline-none focus:border-amber-500/50"
                      placeholder="e.g., 6500"
                    />
                  </div>
                </div>
              )}

              {modelFormData.type === 'tunable_white' && (
                <div>
                  <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Mixing Type</label>
                  <select
                    value={modelFormData.mixing_type}
                    onChange={(e) => setModelFormData({ ...modelFormData, mixing_type: e.target.value as MixingType })}
                    className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white focus:outline-none focus:border-amber-500/50"
                  >
                    <option value="linear">Linear</option>
                    <option value="perceptual">Perceptual (recommended)</option>
                    <option value="logarithmic">Logarithmic</option>
                    <option value="custom">Custom</option>
                  </select>
                  <p className="text-xs text-[#636366] mt-1">How warm/cool channels are mixed for CCT control</p>
                </div>
              )}
            </div>

            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-[#2a2a2f]">
              <button onClick={() => setIsModelModalOpen(false)} className="px-4 py-2.5 text-[#a1a1a6] hover:text-white hover:bg-white/10 rounded-lg transition-colors">
                Cancel
              </button>
              <button
                onClick={handleSaveModel}
                disabled={!isModelFormValid() || isSavingModel}
                className="px-4 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-500/50 disabled:cursor-not-allowed text-black font-medium rounded-lg transition-colors"
              >
                {isSavingModel ? 'Saving...' : (editingModel ? 'Save Changes' : 'Create Model')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
