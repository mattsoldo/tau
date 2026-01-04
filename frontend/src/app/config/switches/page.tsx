'use client';

import { useState, useEffect, useCallback } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type InputType = 'retractive' | 'rotary_abs' | 'paddle_composite' | 'switch_simple';
type TargetType = 'fixture' | 'group';

interface SwitchModel {
  id: number;
  manufacturer: string;
  model: string;
  input_type: InputType;
  debounce_ms: number;
  dimming_curve: string;
  requires_digital_pin: boolean;
  requires_analog_pin: boolean;
}

interface Switch {
  id: number;
  name: string | null;
  switch_model_id: number;
  labjack_digital_pin: number | null;
  labjack_analog_pin: number | null;
  target_group_id: number | null;
  target_fixture_id: number | null;
  model: SwitchModel | null;
}

interface Fixture {
  id: number;
  name: string;
}

interface Group {
  id: number;
  name: string;
}

const inputTypeLabels: Record<InputType, { label: string; color: string }> = {
  retractive: { label: 'Retractive', color: 'bg-blue-500/15 text-blue-400 border-blue-500/30' },
  rotary_abs: { label: 'Rotary', color: 'bg-amber-500/15 text-amber-400 border-amber-500/30' },
  paddle_composite: { label: 'Paddle', color: 'bg-purple-500/15 text-purple-400 border-purple-500/30' },
  switch_simple: { label: 'Simple', color: 'bg-green-500/15 text-green-400 border-green-500/30' },
};

interface FormData {
  name: string;
  switch_model_id: string;
  labjack_digital_pin: string;
  labjack_analog_pin: string;
  target_type: TargetType;
  target_id: string;
}

const emptyFormData: FormData = {
  name: '',
  switch_model_id: '',
  labjack_digital_pin: '',
  labjack_analog_pin: '',
  target_type: 'group',
  target_id: '',
};

export default function SwitchesPage() {
  const [switches, setSwitches] = useState<Switch[]>([]);
  const [switchModels, setSwitchModels] = useState<SwitchModel[]>([]);
  const [fixtures, setFixtures] = useState<Fixture[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingSwitch, setEditingSwitch] = useState<Switch | null>(null);
  const [formData, setFormData] = useState<FormData>(emptyFormData);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const fetchData = useCallback(async () => {
    try {
      setError(null);
      const [switchesRes, modelsRes, fixturesRes, groupsRes] = await Promise.all([
        fetch(`${API_URL}/api/switches/`),
        fetch(`${API_URL}/api/switches/models`),
        fetch(`${API_URL}/api/fixtures/`),
        fetch(`${API_URL}/api/groups/`),
      ]);

      if (!switchesRes.ok) throw new Error(`Failed to fetch switches: ${switchesRes.status}`);
      if (!modelsRes.ok) throw new Error(`Failed to fetch switch models: ${modelsRes.status}`);
      if (!fixturesRes.ok) throw new Error(`Failed to fetch fixtures: ${fixturesRes.status}`);
      if (!groupsRes.ok) throw new Error(`Failed to fetch groups: ${groupsRes.status}`);

      const [switchesData, modelsData, fixturesData, groupsData] = await Promise.all([
        switchesRes.json(),
        modelsRes.json(),
        fixturesRes.json(),
        groupsRes.json(),
      ]);

      setSwitches(switchesData);
      setSwitchModels(modelsData);
      setFixtures(fixturesData);
      setGroups(groupsData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const getTargetName = (sw: Switch): string => {
    if (sw.target_group_id) {
      const group = groups.find(g => g.id === sw.target_group_id);
      return group ? group.name : `Group #${sw.target_group_id}`;
    }
    if (sw.target_fixture_id) {
      const fixture = fixtures.find(f => f.id === sw.target_fixture_id);
      return fixture ? fixture.name : `Fixture #${sw.target_fixture_id}`;
    }
    return 'Unassigned';
  };

  const getTargetType = (sw: Switch): 'group' | 'fixture' | null => {
    if (sw.target_group_id) return 'group';
    if (sw.target_fixture_id) return 'fixture';
    return null;
  };

  const selectedModel = switchModels.find(m => m.id === parseInt(formData.switch_model_id));

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
    const targetType: TargetType = sw.target_group_id ? 'group' : 'fixture';
    const targetId = sw.target_group_id?.toString() || sw.target_fixture_id?.toString() || '';
    setFormData({
      name: sw.name || '',
      switch_model_id: sw.switch_model_id.toString(),
      labjack_digital_pin: sw.labjack_digital_pin?.toString() || '',
      labjack_analog_pin: sw.labjack_analog_pin?.toString() || '',
      target_type: targetType,
      target_id: targetId,
    });
    setIsModalOpen(true);
  };

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);

    try {
      const payload: Record<string, unknown> = {
        name: formData.name || null,
        switch_model_id: parseInt(formData.switch_model_id),
        labjack_digital_pin: formData.labjack_digital_pin ? parseInt(formData.labjack_digital_pin) : null,
        labjack_analog_pin: formData.labjack_analog_pin ? parseInt(formData.labjack_analog_pin) : null,
        target_group_id: formData.target_type === 'group' ? parseInt(formData.target_id) : null,
        target_fixture_id: formData.target_type === 'fixture' ? parseInt(formData.target_id) : null,
      };

      let response: Response;

      if (editingSwitch) {
        response = await fetch(`${API_URL}/api/switches/${editingSwitch.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      } else {
        response = await fetch(`${API_URL}/api/switches/`, {
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
      setIsModalOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save switch');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    setError(null);

    try {
      const response = await fetch(`${API_URL}/api/switches/${id}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to delete: ${response.status}`);
      }

      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete switch');
    } finally {
      setDeleteConfirm(null);
    }
  };

  const isFormValid = () => {
    if (!formData.switch_model_id || !formData.target_id) return false;

    // Validate pin requirements based on selected model
    if (selectedModel) {
      if (selectedModel.requires_digital_pin && !formData.labjack_digital_pin) return false;
      if (selectedModel.requires_analog_pin && !formData.labjack_analog_pin) return false;
    }

    return true;
  };

  if (isLoading) {
    return (
      <div className="p-8 flex items-center justify-center">
        <div className="text-[#636366]">Loading switches...</div>
      </div>
    );
  }

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold">Switches</h1>
          <p className="text-[#636366] mt-1">Configure physical switches and assign them to fixtures or groups</p>
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

      {/* Warning if no switch models */}
      {switchModels.length === 0 && (
        <div className="mb-6 px-4 py-3 bg-amber-500/10 border border-amber-500/30 rounded-lg text-amber-400 text-sm">
          You need to create at least one switch model before adding switches.{' '}
          <a href="/config/switch-models" className="underline hover:text-amber-300">
            Create a switch model
          </a>
        </div>
      )}

      {/* Error Banner */}
      {error && (
        <div className="mb-6 px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="bg-[#161619] border border-[#2a2a2f] rounded-xl overflow-hidden">
        {switches.length === 0 ? (
          <div className="p-12 text-center text-[#636366]">
            <svg className="w-12 h-12 mx-auto mb-4 stroke-current" fill="none" strokeWidth="1" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M5.636 5.636a9 9 0 1012.728 0M12 3v9" />
            </svg>
            <p className="mb-2">No switches configured</p>
            <p className="text-sm">Create your first switch to control fixtures and groups</p>
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-[#2a2a2f]">
                <th className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Switch</th>
                <th className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Model</th>
                <th className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Pins</th>
                <th className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Target</th>
                <th className="px-6 py-4 text-right text-xs font-medium text-[#636366] uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#2a2a2f]">
              {switches.map((sw) => {
                const targetType = getTargetType(sw);
                return (
                  <tr key={sw.id} className="hover:bg-white/[0.02] transition-colors">
                    <td className="px-6 py-4">
                      <div className="font-medium">{sw.name || `Switch #${sw.id}`}</div>
                    </td>
                    <td className="px-6 py-4">
                      {sw.model ? (
                        <div className="flex items-center gap-2">
                          <span className={`inline-flex px-2 py-0.5 text-xs font-medium rounded border ${inputTypeLabels[sw.model.input_type].color}`}>
                            {inputTypeLabels[sw.model.input_type].label}
                          </span>
                          <span className="text-sm text-[#a1a1a6]">
                            {sw.model.manufacturer} {sw.model.model}
                          </span>
                        </div>
                      ) : (
                        <span className="text-[#636366]">Unknown Model</span>
                      )}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex gap-2 font-mono text-sm">
                        {sw.labjack_digital_pin !== null && (
                          <span className="px-2 py-0.5 bg-blue-500/15 text-blue-400 rounded border border-blue-500/30">
                            D{sw.labjack_digital_pin}
                          </span>
                        )}
                        {sw.labjack_analog_pin !== null && (
                          <span className="px-2 py-0.5 bg-amber-500/15 text-amber-400 rounded border border-amber-500/30">
                            A{sw.labjack_analog_pin}
                          </span>
                        )}
                        {sw.labjack_digital_pin === null && sw.labjack_analog_pin === null && (
                          <span className="text-[#636366]">None</span>
                        )}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        {targetType === 'group' && (
                          <span className="inline-flex px-2 py-0.5 text-xs font-medium rounded bg-purple-500/15 text-purple-400 border border-purple-500/30">
                            Group
                          </span>
                        )}
                        {targetType === 'fixture' && (
                          <span className="inline-flex px-2 py-0.5 text-xs font-medium rounded bg-green-500/15 text-green-400 border border-green-500/30">
                            Fixture
                          </span>
                        )}
                        <span className="text-sm">{getTargetName(sw)}</span>
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
        )}
      </div>

      {/* Summary */}
      <div className="mt-4 text-sm text-[#636366]">
        {switches.length} switch{switches.length !== 1 ? 'es' : ''} configured
      </div>

      {/* Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-[#161619] border border-[#2a2a2f] rounded-2xl w-full max-w-lg mx-4 shadow-2xl">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-[#2a2a2f]">
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
                <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Name (Optional)</label>
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

              {/* Pin Assignments */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-[#a1a1a6] mb-2">
                    Digital Pin
                    {selectedModel?.requires_digital_pin && (
                      <span className="text-red-400 ml-1">*</span>
                    )}
                  </label>
                  <select
                    value={formData.labjack_digital_pin}
                    onChange={(e) => setFormData({ ...formData, labjack_digital_pin: e.target.value })}
                    className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                  >
                    <option value="">None</option>
                    {Array.from({ length: 16 }, (_, i) => (
                      <option key={i} value={i}>D{i}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-[#a1a1a6] mb-2">
                    Analog Pin
                    {selectedModel?.requires_analog_pin && (
                      <span className="text-red-400 ml-1">*</span>
                    )}
                  </label>
                  <select
                    value={formData.labjack_analog_pin}
                    onChange={(e) => setFormData({ ...formData, labjack_analog_pin: e.target.value })}
                    className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                  >
                    <option value="">None</option>
                    {Array.from({ length: 16 }, (_, i) => (
                      <option key={i} value={i}>A{i}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Target Assignment */}
              <div className="space-y-3">
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-px bg-[#2a2a2f]" />
                  <span className="text-xs font-medium text-[#636366] uppercase tracking-wider">Target Assignment</span>
                  <div className="flex-1 h-px bg-[#2a2a2f]" />
                </div>

                {/* Target Type Toggle */}
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setFormData({ ...formData, target_type: 'group', target_id: '' })}
                    className={`flex-1 px-4 py-2.5 rounded-lg border text-sm font-medium transition-colors ${
                      formData.target_type === 'group'
                        ? 'bg-purple-500/15 text-purple-400 border-purple-500/50'
                        : 'bg-[#111113] text-[#636366] border-[#2a2a2f] hover:text-white hover:border-[#3a3a3f]'
                    }`}
                  >
                    <div className="flex items-center justify-center gap-2">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 7.125C2.25 6.504 2.754 6 3.375 6h6c.621 0 1.125.504 1.125 1.125v3.75c0 .621-.504 1.125-1.125 1.125h-6a1.125 1.125 0 01-1.125-1.125v-3.75z" />
                      </svg>
                      Group
                    </div>
                  </button>
                  <button
                    type="button"
                    onClick={() => setFormData({ ...formData, target_type: 'fixture', target_id: '' })}
                    className={`flex-1 px-4 py-2.5 rounded-lg border text-sm font-medium transition-colors ${
                      formData.target_type === 'fixture'
                        ? 'bg-green-500/15 text-green-400 border-green-500/50'
                        : 'bg-[#111113] text-[#636366] border-[#2a2a2f] hover:text-white hover:border-[#3a3a3f]'
                    }`}
                  >
                    <div className="flex items-center justify-center gap-2">
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 18v-5.25m0 0a6.01 6.01 0 001.5-.189m-1.5.189a6.01 6.01 0 01-1.5-.189m3.75 7.478a12.06 12.06 0 01-4.5 0m3.75 2.383a14.406 14.406 0 01-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 10-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" />
                      </svg>
                      Fixture
                    </div>
                  </button>
                </div>

                {/* Target Selection */}
                <div>
                  <label className="block text-sm font-medium text-[#a1a1a6] mb-2">
                    Select {formData.target_type === 'group' ? 'Group' : 'Fixture'}
                    <span className="text-red-400 ml-1">*</span>
                  </label>
                  <select
                    value={formData.target_id}
                    onChange={(e) => setFormData({ ...formData, target_id: e.target.value })}
                    className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                  >
                    <option value="">Select a {formData.target_type}...</option>
                    {formData.target_type === 'group' ? (
                      groups.map((group) => (
                        <option key={group.id} value={group.id}>{group.name}</option>
                      ))
                    ) : (
                      fixtures.map((fixture) => (
                        <option key={fixture.id} value={fixture.id}>{fixture.name}</option>
                      ))
                    )}
                  </select>
                  <p className="text-xs text-[#636366] mt-1.5">
                    {formData.target_type === 'group'
                      ? 'The switch will control all fixtures in this group'
                      : 'The switch will control this individual fixture'
                    }
                  </p>
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-[#2a2a2f]">
              <button
                onClick={() => setIsModalOpen(false)}
                className="px-4 py-2.5 text-[#a1a1a6] hover:text-white hover:bg-white/10 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={!isFormValid() || isSaving}
                className="px-4 py-2.5 bg-amber-500 hover:bg-amber-600 disabled:bg-amber-500/50 disabled:cursor-not-allowed text-black font-medium rounded-lg transition-colors"
              >
                {isSaving ? 'Saving...' : (editingSwitch ? 'Save Changes' : 'Create Switch')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
