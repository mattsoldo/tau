'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { ToastContainer, ToastProps } from '@/components/ui/Toast';
import { API_URL, getWsUrl } from '@/utils/api';

// === Types ===

type SwitchInputType = 'retractive' | 'rotary_abs' | 'paddle_composite' | 'switch_simple';
type DimmingCurve = 'linear' | 'logarithmic';

interface SwitchModel {
  id: number;
  manufacturer: string;
  model: string;
  input_type: SwitchInputType;
  debounce_ms: number;
  dimming_curve: DimmingCurve;
  requires_digital_pin: boolean;
  requires_analog_pin: boolean;
}

type SwitchType = 'normally-open' | 'normally-closed';

interface Switch {
  id: number;
  name: string | null;
  switch_model_id: number;
  labjack_digital_pin: number | null;
  labjack_analog_pin: number | null;
  switch_type: SwitchType;
  invert_reading: boolean;
  target_group_id: number | null;
  target_fixture_id: number | null;
  photo_url: string | null;
}

interface Group {
  id: number;
  name: string;
  description: string | null;
}

interface Fixture {
  id: number;
  name: string;
  dmx_channel_start: number;
}

type TargetType = 'group' | 'fixture';

interface FormData {
  name: string;
  switch_model_id: string;
  labjack_digital_pin: string;
  labjack_analog_pin: string;
  switch_type: SwitchType;
  invert_reading: boolean;
  target_type: TargetType;
  target_group_id: string;
  target_fixture_id: string;
}

const emptyFormData: FormData = {
  name: '',
  switch_model_id: '',
  labjack_digital_pin: '',
  labjack_analog_pin: '',
  switch_type: 'normally-closed',
  invert_reading: false,
  target_type: 'group',
  target_group_id: '',
  target_fixture_id: '',
};

const inputTypeLabels: Record<SwitchInputType, { label: string; color: string }> = {
  retractive: { label: 'Retractive', color: 'bg-blue-500/15 text-blue-400 border-blue-500/30' },
  rotary_abs: { label: 'Rotary', color: 'bg-purple-500/15 text-purple-400 border-purple-500/30' },
  paddle_composite: { label: 'Paddle', color: 'bg-amber-500/15 text-amber-400 border-amber-500/30' },
  switch_simple: { label: 'Simple', color: 'bg-green-500/15 text-green-400 border-green-500/30' },
};

// === Component ===

export default function SwitchesPage() {
  // Data state
  const [switches, setSwitches] = useState<Switch[]>([]);
  const [switchModels, setSwitchModels] = useState<SwitchModel[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [fixtures, setFixtures] = useState<Fixture[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingSwitch, setEditingSwitch] = useState<Switch | null>(null);
  const [formData, setFormData] = useState<FormData>(emptyFormData);
  const [isSaving, setIsSaving] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);

  // Sort state
  type SortColumn = 'name' | 'model' | 'target' | 'pins';
  type SortDirection = 'asc' | 'desc';
  const [sortColumn, setSortColumn] = useState<SortColumn>('name');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');

  // Toast state for switch discovery
  const [toasts, setToasts] = useState<ToastProps[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  // Fetch all data
  const fetchData = useCallback(async () => {
    try {
      const [switchesRes, modelsRes, groupsRes, fixturesRes] = await Promise.all([
        fetch(`${API_URL}/api/switches/`),
        fetch(`${API_URL}/api/switches/models`),
        fetch(`${API_URL}/api/groups/`),
        fetch(`${API_URL}/api/fixtures/`),
      ]);

      if (!switchesRes.ok) throw new Error('Failed to fetch switches');
      if (!modelsRes.ok) throw new Error('Failed to fetch switch models');
      if (!groupsRes.ok) throw new Error('Failed to fetch groups');
      if (!fixturesRes.ok) throw new Error('Failed to fetch fixtures');

      const [switchesData, modelsData, groupsData, fixturesData] = await Promise.all([
        switchesRes.json(),
        modelsRes.json(),
        groupsRes.json(),
        fixturesRes.json(),
      ]);

      setSwitches(switchesData);
      setSwitchModels(modelsData);
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

  // WebSocket connection for switch auto-discovery
  useEffect(() => {
    const ws = new WebSocket(`${getWsUrl()}/ws`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('WebSocket connected for switch discovery');
      // Subscribe to switch discovery events
      ws.send(JSON.stringify({
        action: 'subscribe',
        event_types: ['switch_discovered']
      }));
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'switch_discovered') {
          handleSwitchDiscovered(data);
        }
      } catch (err) {
        console.error('WebSocket message error:', err);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };

    ws.onclose = () => {
      console.log('WebSocket closed');
    };

    return () => {
      ws.close();
    };
  }, []);

  // Handle new switch discovered
  const handleSwitchDiscovered = useCallback((data: {
    pin: number;
    is_digital: boolean;
    change_count: number;
  }) => {
    const pinType = data.is_digital ? 'Digital' : 'Analog';
    const message = `New ${pinType} switch detected on pin ${data.pin}`;

    // Add toast notification with Configure and Ignore actions
    const toastId = `switch-${data.pin}-${data.is_digital ? 'digital' : 'analog'}`;

    setToasts(prev => [
      ...prev.filter(t => t.id !== toastId), // Remove duplicate if exists
      {
        id: toastId,
        type: 'success',
        message,
        action: {
          label: 'Configure',
          onClick: () => {
            handleConfigureDiscoveredSwitch(data.pin, data.is_digital);
          },
        },
        duration: 0, // Don't auto-dismiss
        onDismiss: (id) => handleDismissToast(id, data.pin, data.is_digital),
      },
    ]);
  }, []);

  // Handle clicking "Configure" on discovery toast
  const handleConfigureDiscoveredSwitch = useCallback((pin: number, isDigital: boolean) => {
    // Pre-fill form with detected pin
    setFormData({
      ...emptyFormData,
      [isDigital ? 'labjack_digital_pin' : 'labjack_analog_pin']: pin.toString(),
    });
    setEditingSwitch(null);
    setIsModalOpen(true);

    // Dismiss the toast
    handleDismissToast(`switch-${pin}-${isDigital ? 'digital' : 'analog'}`, pin, isDigital);
  }, []);

  // Handle dismissing a toast
  const handleDismissToast = useCallback(async (toastId: string, pin?: number, isDigital?: boolean) => {
    setToasts(prev => prev.filter(t => t.id !== toastId));

    // If pin info provided, notify backend to clear detection
    if (pin !== undefined && isDigital !== undefined) {
      try {
        await fetch(`${API_URL}/api/switches/discovery/dismiss?pin=${pin}&is_digital=${isDigital}`, {
          method: 'POST',
        });
      } catch (err) {
        console.error('Failed to dismiss discovery:', err);
      }
    }
  }, []);

  // Helpers
  const getModelById = (id: number): SwitchModel | undefined => {
    return switchModels.find(m => m.id === id);
  };

  const getGroupById = (id: number): Group | undefined => {
    return groups.find(g => g.id === id);
  };

  const getFixtureById = (id: number): Fixture | undefined => {
    return fixtures.find(f => f.id === id);
  };

  const getTargetDisplay = (sw: Switch): { type: string; name: string; icon: string } => {
    if (sw.target_group_id !== null) {
      const group = getGroupById(sw.target_group_id);
      return {
        type: 'Group',
        name: group?.name || `Group #${sw.target_group_id}`,
        icon: 'M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z',
      };
    }
    if (sw.target_fixture_id !== null) {
      const fixture = getFixtureById(sw.target_fixture_id);
      return {
        type: 'Fixture',
        name: fixture?.name || `Fixture #${sw.target_fixture_id}`,
        icon: 'M12 18v-5.25m0 0a6.01 6.01 0 001.5-.189m-1.5.189a6.01 6.01 0 01-1.5-.189m3.75 7.478a12.06 12.06 0 01-4.5 0m3.75 2.383a14.406 14.406 0 01-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 10-7.517 0c.85.493 1.509 1.333 1.509 2.316V18',
      };
    }
    return { type: 'Unknown', name: 'No target', icon: '' };
  };

  // Sort switches
  const sortedSwitches = [...switches].sort((a, b) => {
    let comparison = 0;
    switch (sortColumn) {
      case 'name':
        comparison = (a.name || '').localeCompare(b.name || '');
        break;
      case 'model':
        const modelA = getModelById(a.switch_model_id);
        const modelB = getModelById(b.switch_model_id);
        comparison = (`${modelA?.manufacturer} ${modelA?.model}`).localeCompare(`${modelB?.manufacturer} ${modelB?.model}`);
        break;
      case 'target':
        const targetA = getTargetDisplay(a);
        const targetB = getTargetDisplay(b);
        comparison = targetA.name.localeCompare(targetB.name);
        break;
      case 'pins':
        comparison = (a.labjack_digital_pin ?? 100) - (b.labjack_digital_pin ?? 100);
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

  // Modal operations
  const openCreateModal = () => {
    setEditingSwitch(null);
    setFormData({
      ...emptyFormData,
      switch_model_id: switchModels.length > 0 ? switchModels[0].id.toString() : '',
    });
    setIsModalOpen(true);
  };

  const openEditModal = (sw: Switch) => {
    setEditingSwitch(sw);
    setFormData({
      name: sw.name || '',
      switch_model_id: sw.switch_model_id.toString(),
      labjack_digital_pin: sw.labjack_digital_pin?.toString() || '',
      labjack_analog_pin: sw.labjack_analog_pin?.toString() || '',
      switch_type: sw.switch_type || 'normally-closed',
      invert_reading: sw.invert_reading || false,
      target_type: sw.target_group_id !== null ? 'group' : 'fixture',
      target_group_id: sw.target_group_id?.toString() || '',
      target_fixture_id: sw.target_fixture_id?.toString() || '',
    });
    setIsModalOpen(true);
  };

  const handleSave = async () => {
    if (!formData.switch_model_id) {
      setError('Please select a switch model');
      return;
    }

    // Validate switch_type is a valid value
    const validSwitchTypes: SwitchType[] = ['normally-open', 'normally-closed'];
    if (!validSwitchTypes.includes(formData.switch_type)) {
      setError('Invalid switch type. Must be "normally-open" or "normally-closed"');
      return;
    }

    const targetGroupId = formData.target_type === 'group' && formData.target_group_id
      ? parseInt(formData.target_group_id)
      : null;
    const targetFixtureId = formData.target_type === 'fixture' && formData.target_fixture_id
      ? parseInt(formData.target_fixture_id)
      : null;

    if (targetGroupId === null && targetFixtureId === null) {
      setError('Please select a target group or fixture');
      return;
    }

    setIsSaving(true);
    setError(null);

    try {
      const payload = {
        name: formData.name.trim() || null,
        switch_model_id: parseInt(formData.switch_model_id),
        labjack_digital_pin: formData.labjack_digital_pin ? parseInt(formData.labjack_digital_pin) : null,
        labjack_analog_pin: formData.labjack_analog_pin ? parseInt(formData.labjack_analog_pin) : null,
        switch_type: formData.switch_type,
        invert_reading: formData.invert_reading,
        target_group_id: targetGroupId,
        target_fixture_id: targetFixtureId,
      };

      const url = editingSwitch
        ? `${API_URL}/api/switches/${editingSwitch.id}`
        : `${API_URL}/api/switches/`;

      const res = await fetch(url, {
        method: editingSwitch ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to save switch');
      }

      setIsModalOpen(false);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save switch');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      const res = await fetch(`${API_URL}/api/switches/${id}`, {
        method: 'DELETE',
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to delete switch');
      }

      setDeleteConfirm(null);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete switch');
    }
  };

  // Get selected model for validation display
  const selectedModel = formData.switch_model_id
    ? getModelById(parseInt(formData.switch_model_id))
    : null;

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold">Switches</h1>
          <p className="text-[#636366] mt-1">Physical switches and dimmers mapped to fixtures or groups</p>
        </div>
        <button
          onClick={openCreateModal}
          disabled={switchModels.length === 0}
          className="flex items-center gap-2 px-4 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-500/50 disabled:cursor-not-allowed text-black font-medium rounded-lg transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          Add Switch
        </button>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="mb-6 px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}

      {/* No switch models warning */}
      {!isLoading && switchModels.length === 0 && (
        <div className="mb-6 px-4 py-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-amber-400 text-sm">
          No switch models defined. Create a switch model first before adding switches.
        </div>
      )}

      {/* Loading State */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-2 border-amber-500 border-t-transparent rounded-full animate-spin"></div>
        </div>
      ) : switches.length === 0 ? (
        <div className="bg-[#161619] border border-[#2a2a2f] rounded-xl p-12 text-center text-[#636366]">
          <svg className="w-12 h-12 mx-auto mb-4 stroke-current" fill="none" strokeWidth="1" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M5.636 5.636a9 9 0 1012.728 0M12 3v9" />
          </svg>
          <p className="mb-2">No switches configured</p>
          <p className="text-sm mb-4">Create your first switch to connect physical controls to your lighting</p>
          {switchModels.length > 0 && (
            <button
              onClick={openCreateModal}
              className="inline-flex items-center gap-2 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors"
            >
              Create Switch
            </button>
          )}
        </div>
      ) : (
        /* Switches Table */
        <div className="bg-[#161619] border border-[#2a2a2f] rounded-xl overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-[#2a2a2f]">
                <th
                  className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider cursor-pointer hover:text-white"
                  onClick={() => handleSort('name')}
                >
                  Name <SortIndicator column="name" />
                </th>
                <th
                  className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider cursor-pointer hover:text-white"
                  onClick={() => handleSort('model')}
                >
                  Model <SortIndicator column="model" />
                </th>
                <th
                  className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider cursor-pointer hover:text-white"
                  onClick={() => handleSort('target')}
                >
                  Target <SortIndicator column="target" />
                </th>
                <th
                  className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider cursor-pointer hover:text-white"
                  onClick={() => handleSort('pins')}
                >
                  Pins <SortIndicator column="pins" />
                </th>
                <th className="px-6 py-4 text-right text-xs font-medium text-[#636366] uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#2a2a2f]">
              {sortedSwitches.map((sw) => {
                const model = getModelById(sw.switch_model_id);
                const target = getTargetDisplay(sw);
                return (
                  <tr key={sw.id} className="hover:bg-white/[0.02] transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-medium">{sw.name || <span className="text-[#636366]">Unnamed</span>}</div>
                    </td>
                    <td className="px-6 py-4">
                      {model ? (
                        <div>
                          <div className="text-sm">{model.manufacturer} {model.model}</div>
                          <span className={`inline-flex mt-1 px-2 py-0.5 text-xs font-medium rounded border ${inputTypeLabels[model.input_type].color}`}>
                            {inputTypeLabels[model.input_type].label}
                          </span>
                        </div>
                      ) : (
                        <span className="text-[#636366]">Unknown model</span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <svg className="w-4 h-4 text-[#636366]" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" d={target.icon} />
                        </svg>
                        <div>
                          <div className="text-sm">{target.name}</div>
                          <div className="text-xs text-[#636366]">{target.type}</div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 align-middle">
                      <div className="flex flex-col gap-1 min-h-[40px] justify-center">
                        <div className="flex gap-2">
                          {sw.labjack_digital_pin !== null && (
                            <span className="px-2 py-0.5 text-xs bg-blue-500/10 text-blue-400 rounded font-mono">
                              D{sw.labjack_digital_pin}
                            </span>
                          )}
                          {sw.labjack_analog_pin !== null && (
                            <span className="px-2 py-0.5 text-xs bg-purple-500/10 text-purple-400 rounded font-mono">
                              A{sw.labjack_analog_pin}
                            </span>
                          )}
                          {sw.labjack_digital_pin === null && sw.labjack_analog_pin === null && (
                            <span className="text-[#636366] text-sm">None</span>
                          )}
                        </div>
                        <div className="flex gap-1 items-center">
                          <span
                            className="text-xs text-[#636366] cursor-help"
                            title={(!sw.switch_type || sw.switch_type === 'normally-closed')
                              ? 'Normally Closed: Circuit is closed when switch is not pressed'
                              : 'Normally Open: Circuit is open when switch is not pressed'}
                          >
                            {(!sw.switch_type || sw.switch_type === 'normally-closed') ? 'NC' : 'NO'}
                          </span>
                          {sw.invert_reading && (
                            <span
                              className="px-1.5 py-0.5 text-[10px] bg-amber-500/10 text-amber-400 rounded cursor-help"
                              title="Invert Logic: Switch reading is flipped in software"
                            >
                              INV
                            </span>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => openEditModal(sw)}
                          className="p-2 text-[#636366] hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
                          </svg>
                        </button>
                        {deleteConfirm === sw.id ? (
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => handleDelete(sw.id)}
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
                            onClick={() => setDeleteConfirm(sw.id)}
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
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Summary */}
      <div className="mt-4 text-sm text-[#636366]">
        {switches.length} switch{switches.length !== 1 ? 'es' : ''} configured
      </div>

      {/* Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-[#161619] border border-[#2a2a2f] rounded-2xl w-full max-w-lg mx-4 shadow-2xl max-h-[90vh] overflow-y-auto">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-[#2a2a2f] sticky top-0 bg-[#161619]">
              <h2 className="text-lg font-semibold">
                {editingSwitch ? 'Edit Switch' : 'New Switch'}
              </h2>
              <button
                onClick={() => setIsModalOpen(false)}
                className="p-2 text-[#636366] hover:text-white hover:bg-white/10 rounded-lg transition-colors"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 space-y-5">
              {/* Name */}
              <div>
                <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Name (optional)</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white placeholder-[#636366] focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                  placeholder="e.g., Living Room Dimmer"
                />
              </div>

              {/* Switch Model */}
              <div>
                <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Switch Model</label>
                <select
                  value={formData.switch_model_id}
                  onChange={(e) => setFormData({ ...formData, switch_model_id: e.target.value })}
                  className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                >
                  <option value="">Select a model...</option>
                  {switchModels.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.manufacturer} {model.model} ({inputTypeLabels[model.input_type].label})
                    </option>
                  ))}
                </select>
              </div>

              {/* Pin Requirements Indicator */}
              {selectedModel && (
                <div className="px-3 py-2 bg-[#0a0a0b] border border-[#2a2a2f] rounded-lg">
                  <div className="text-xs text-[#636366] mb-1">Pin Requirements</div>
                  <div className="flex gap-3">
                    {selectedModel.requires_digital_pin && (
                      <span className="text-sm text-blue-400">Digital pin required</span>
                    )}
                    {selectedModel.requires_analog_pin && (
                      <span className="text-sm text-purple-400">Analog pin required</span>
                    )}
                    {!selectedModel.requires_digital_pin && !selectedModel.requires_analog_pin && (
                      <span className="text-sm text-[#636366]">No specific pins required</span>
                    )}
                  </div>
                </div>
              )}

              {/* LabJack Pins */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-[#a1a1a6] mb-2">
                    Digital Pin
                    {selectedModel?.requires_digital_pin && <span className="text-red-400 ml-1">*</span>}
                  </label>
                  <select
                    value={formData.labjack_digital_pin}
                    onChange={(e) => setFormData({ ...formData, labjack_digital_pin: e.target.value })}
                    className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                  >
                    <option value="">None</option>
                    {Array.from({ length: 16 }, (_, i) => (
                      <option key={i} value={i}>FIO{i} / D{i}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-[#a1a1a6] mb-2">
                    Analog Pin
                    {selectedModel?.requires_analog_pin && <span className="text-red-400 ml-1">*</span>}
                  </label>
                  <select
                    value={formData.labjack_analog_pin}
                    onChange={(e) => setFormData({ ...formData, labjack_analog_pin: e.target.value })}
                    className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                  >
                    <option value="">None</option>
                    {Array.from({ length: 16 }, (_, i) => (
                      <option key={i} value={i}>AIN{i} / A{i}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Switch Type Configuration */}
              <div className="space-y-3">
                <label className="block text-sm font-medium text-[#a1a1a6]">Hardware Configuration</label>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs text-[#636366] mb-2">Switch Type</label>
                    <select
                      value={formData.switch_type}
                      onChange={(e) => setFormData({ ...formData, switch_type: e.target.value as SwitchType })}
                      className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                    >
                      <option value="normally-closed">Normally Closed (NC)</option>
                      <option value="normally-open">Normally Open (NO)</option>
                    </select>
                  </div>
                  <div className="flex items-end pb-1">
                    <label className="flex items-center gap-3 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={formData.invert_reading}
                        onChange={(e) => setFormData({ ...formData, invert_reading: e.target.checked })}
                        className="w-5 h-5 rounded border-[#3a3a3f] bg-[#111113] text-amber-500 focus:ring-amber-500/30 focus:ring-offset-0"
                      />
                      <span className="text-sm text-[#a1a1a6]">Invert Logic</span>
                    </label>
                  </div>
                </div>
                <p className="text-xs text-[#636366]">
                  NC: Circuit closed when not pressed. NO: Circuit open when not pressed. Invert Logic flips the reading in software.
                </p>
              </div>

              {/* Target Selection */}
              <div className="space-y-3">
                <label className="block text-sm font-medium text-[#a1a1a6]">Control Target</label>

                {/* Target Type Toggle */}
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setFormData({ ...formData, target_type: 'group', target_fixture_id: '' })}
                    className={`flex-1 px-4 py-2.5 rounded-lg border text-sm font-medium transition-colors ${
                      formData.target_type === 'group'
                        ? 'bg-amber-500/15 border-amber-500/30 text-amber-400'
                        : 'bg-[#111113] border-[#2a2a2f] text-[#a1a1a6] hover:border-[#3a3a3f]'
                    }`}
                  >
                    <svg className="w-4 h-4 inline-block mr-2" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z" />
                    </svg>
                    Group
                  </button>
                  <button
                    type="button"
                    onClick={() => setFormData({ ...formData, target_type: 'fixture', target_group_id: '' })}
                    className={`flex-1 px-4 py-2.5 rounded-lg border text-sm font-medium transition-colors ${
                      formData.target_type === 'fixture'
                        ? 'bg-amber-500/15 border-amber-500/30 text-amber-400'
                        : 'bg-[#111113] border-[#2a2a2f] text-[#a1a1a6] hover:border-[#3a3a3f]'
                    }`}
                  >
                    <svg className="w-4 h-4 inline-block mr-2" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 18v-5.25m0 0a6.01 6.01 0 001.5-.189m-1.5.189a6.01 6.01 0 01-1.5-.189m3.75 7.478a12.06 12.06 0 01-4.5 0m3.75 2.383a14.406 14.406 0 01-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 10-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" />
                    </svg>
                    Fixture
                  </button>
                </div>

                {/* Target Dropdown */}
                {formData.target_type === 'group' ? (
                  <select
                    value={formData.target_group_id}
                    onChange={(e) => setFormData({ ...formData, target_group_id: e.target.value })}
                    className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                  >
                    <option value="">Select a group...</option>
                    {groups.map((group) => (
                      <option key={group.id} value={group.id}>
                        {group.name}{group.description ? ` - ${group.description}` : ''}
                      </option>
                    ))}
                  </select>
                ) : (
                  <select
                    value={formData.target_fixture_id}
                    onChange={(e) => setFormData({ ...formData, target_fixture_id: e.target.value })}
                    className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                  >
                    <option value="">Select a fixture...</option>
                    {fixtures.map((fixture) => (
                      <option key={fixture.id} value={fixture.id}>
                        {fixture.name} (DMX {fixture.dmx_channel_start})
                      </option>
                    ))}
                  </select>
                )}

                {/* No targets warning */}
                {formData.target_type === 'group' && groups.length === 0 && (
                  <p className="text-xs text-amber-400">No groups available. Create a group first.</p>
                )}
                {formData.target_type === 'fixture' && fixtures.length === 0 && (
                  <p className="text-xs text-amber-400">No fixtures available. Create a fixture first.</p>
                )}
              </div>
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-[#2a2a2f] sticky bottom-0 bg-[#161619]">
              <button
                onClick={() => setIsModalOpen(false)}
                className="px-4 py-2.5 text-[#a1a1a6] hover:text-white hover:bg-white/10 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={isSaving}
                className="px-4 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-500/50 disabled:cursor-not-allowed text-black font-medium rounded-lg transition-colors"
              >
                {isSaving ? 'Saving...' : (editingSwitch ? 'Save Changes' : 'Create Switch')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Toast notifications for switch auto-discovery */}
      <ToastContainer toasts={toasts} onDismiss={handleDismissToast} />
    </div>
  );
}
