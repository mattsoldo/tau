'use client';

import { useState, useEffect, useCallback } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

type InputType = 'retractive' | 'rotary_abs' | 'paddle_composite' | 'switch_simple';
type DimmingCurve = 'linear' | 'logarithmic';

interface SwitchModel {
  id: number;
  manufacturer: string;
  model: string;
  input_type: InputType;
  debounce_ms: number;
  dimming_curve: DimmingCurve;
  requires_digital_pin: boolean;
  requires_analog_pin: boolean;
}

const inputTypeLabels: Record<InputType, { label: string; description: string; color: string }> = {
  retractive: {
    label: 'Retractive',
    description: 'Momentary push button that springs back',
    color: 'bg-blue-500/15 text-blue-400 border-blue-500/30'
  },
  rotary_abs: {
    label: 'Rotary (Absolute)',
    description: 'Analog rotary dimmer with position tracking',
    color: 'bg-amber-500/15 text-amber-400 border-amber-500/30'
  },
  paddle_composite: {
    label: 'Paddle Composite',
    description: 'Multi-button paddle switch',
    color: 'bg-purple-500/15 text-purple-400 border-purple-500/30'
  },
  switch_simple: {
    label: 'Simple Switch',
    description: 'On/off toggle switch',
    color: 'bg-green-500/15 text-green-400 border-green-500/30'
  },
};

interface FormData {
  manufacturer: string;
  model: string;
  input_type: InputType;
  debounce_ms: string;
  dimming_curve: DimmingCurve;
  requires_digital_pin: boolean;
  requires_analog_pin: boolean;
}

const emptyFormData: FormData = {
  manufacturer: '',
  model: '',
  input_type: 'retractive',
  debounce_ms: '500',
  dimming_curve: 'logarithmic',
  requires_digital_pin: true,
  requires_analog_pin: false,
};

export default function SwitchModelsPage() {
  const [models, setModels] = useState<SwitchModel[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingModel, setEditingModel] = useState<SwitchModel | null>(null);
  const [formData, setFormData] = useState<FormData>(emptyFormData);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const fetchModels = useCallback(async () => {
    try {
      setError(null);
      const response = await fetch(`${API_URL}/api/switches/models`);
      if (!response.ok) {
        throw new Error(`Failed to fetch: ${response.status}`);
      }
      const data = await response.json();
      setModels(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load switch models');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchModels();
  }, [fetchModels]);

  const openCreateModal = () => {
    setEditingModel(null);
    setFormData(emptyFormData);
    setIsModalOpen(true);
  };

  const openEditModal = (model: SwitchModel) => {
    setEditingModel(model);
    setFormData({
      manufacturer: model.manufacturer,
      model: model.model,
      input_type: model.input_type,
      debounce_ms: model.debounce_ms.toString(),
      dimming_curve: model.dimming_curve,
      requires_digital_pin: model.requires_digital_pin,
      requires_analog_pin: model.requires_analog_pin,
    });
    setIsModalOpen(true);
  };

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);

    try {
      const payload = {
        manufacturer: formData.manufacturer,
        model: formData.model,
        input_type: formData.input_type,
        debounce_ms: parseInt(formData.debounce_ms) || 500,
        dimming_curve: formData.dimming_curve,
        requires_digital_pin: formData.requires_digital_pin,
        requires_analog_pin: formData.requires_analog_pin,
      };

      let response: Response;

      if (editingModel) {
        response = await fetch(`${API_URL}/api/switches/models/${editingModel.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      } else {
        response = await fetch(`${API_URL}/api/switches/models`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to save: ${response.status}`);
      }

      await fetchModels();
      setIsModalOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save switch model');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    setError(null);

    try {
      const response = await fetch(`${API_URL}/api/switches/models/${id}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to delete: ${response.status}`);
      }

      await fetchModels();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete switch model');
    } finally {
      setDeleteConfirm(null);
    }
  };

  const isFormValid = () => {
    return formData.manufacturer && formData.model;
  };

  if (isLoading) {
    return (
      <div className="p-8 flex items-center justify-center">
        <div className="text-[#636366]">Loading switch models...</div>
      </div>
    );
  }

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold">Switch Models</h1>
          <p className="text-[#636366] mt-1">Define switch types with input characteristics and hardware requirements</p>
        </div>
        <button
          onClick={openCreateModal}
          className="flex items-center gap-2 px-4 py-2.5 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          Add Model
        </button>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="mb-6 px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="bg-[#161619] border border-[#2a2a2f] rounded-xl overflow-hidden">
        {models.length === 0 ? (
          <div className="p-12 text-center text-[#636366]">
            <svg className="w-12 h-12 mx-auto mb-4 stroke-current" fill="none" strokeWidth="1" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
            </svg>
            <p className="mb-2">No switch models defined</p>
            <p className="text-sm">Create your first switch model to get started</p>
          </div>
        ) : (
          <table className="w-full">
            <thead>
              <tr className="border-b border-[#2a2a2f]">
                <th className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Model</th>
                <th className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Input Type</th>
                <th className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Debounce</th>
                <th className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Curve</th>
                <th className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Pins</th>
                <th className="px-6 py-4 text-right text-xs font-medium text-[#636366] uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#2a2a2f]">
              {models.map((model) => (
                <tr key={model.id} className="hover:bg-white/[0.02] transition-colors">
                  <td className="px-6 py-4">
                    <div className="font-medium">{model.manufacturer} {model.model}</div>
                  </td>
                  <td className="px-6 py-4">
                    <span className={`inline-flex px-2.5 py-1 text-xs font-medium rounded-md border ${inputTypeLabels[model.input_type].color}`}>
                      {inputTypeLabels[model.input_type].label}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <span className="font-mono text-sm">{model.debounce_ms}ms</span>
                  </td>
                  <td className="px-6 py-4">
                    <span className="text-sm capitalize">{model.dimming_curve}</span>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex gap-2">
                      {model.requires_digital_pin && (
                        <span className="inline-flex px-2 py-0.5 text-xs font-medium rounded bg-blue-500/15 text-blue-400 border border-blue-500/30">
                          Digital
                        </span>
                      )}
                      {model.requires_analog_pin && (
                        <span className="inline-flex px-2 py-0.5 text-xs font-medium rounded bg-amber-500/15 text-amber-400 border border-amber-500/30">
                          Analog
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => openEditModal(model)}
                        className="p-2 text-[#636366] hover:text-white hover:bg-white/10 rounded-lg transition-colors"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
                        </svg>
                      </button>
                      {deleteConfirm === model.id ? (
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleDelete(model.id)}
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
                          onClick={() => setDeleteConfirm(model.id)}
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
        )}
      </div>

      {/* Summary */}
      <div className="mt-4 text-sm text-[#636366]">
        {models.length} switch model{models.length !== 1 ? 's' : ''} configured
      </div>

      {/* Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-[#161619] border border-[#2a2a2f] rounded-2xl w-full max-w-lg mx-4 shadow-2xl">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-[#2a2a2f]">
              <h2 className="text-lg font-semibold">
                {editingModel ? 'Edit Switch Model' : 'New Switch Model'}
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
              {/* Manufacturer & Model */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Manufacturer</label>
                  <input
                    type="text"
                    value={formData.manufacturer}
                    onChange={(e) => setFormData({ ...formData, manufacturer: e.target.value })}
                    className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white placeholder-[#636366] focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                    placeholder="e.g., Lutron"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Model</label>
                  <input
                    type="text"
                    value={formData.model}
                    onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                    className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white placeholder-[#636366] focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                    placeholder="e.g., Pico Remote"
                  />
                </div>
              </div>

              {/* Input Type */}
              <div>
                <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Input Type</label>
                <select
                  value={formData.input_type}
                  onChange={(e) => {
                    const newType = e.target.value as InputType;
                    // Auto-set pin requirements based on input type
                    let requires_digital = true;
                    let requires_analog = false;
                    if (newType === 'rotary_abs') {
                      requires_digital = false;
                      requires_analog = true;
                    }
                    setFormData({
                      ...formData,
                      input_type: newType,
                      requires_digital_pin: requires_digital,
                      requires_analog_pin: requires_analog,
                    });
                  }}
                  className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                >
                  {Object.entries(inputTypeLabels).map(([value, { label }]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
                <p className="text-xs text-[#636366] mt-1">
                  {inputTypeLabels[formData.input_type].description}
                </p>
              </div>

              {/* Debounce & Dimming Curve */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Debounce (ms)</label>
                  <input
                    type="number"
                    min="0"
                    max="5000"
                    value={formData.debounce_ms}
                    onChange={(e) => setFormData({ ...formData, debounce_ms: e.target.value })}
                    className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white placeholder-[#636366] focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                    placeholder="500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Dimming Curve</label>
                  <select
                    value={formData.dimming_curve}
                    onChange={(e) => setFormData({ ...formData, dimming_curve: e.target.value as DimmingCurve })}
                    className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                  >
                    <option value="logarithmic">Logarithmic</option>
                    <option value="linear">Linear</option>
                  </select>
                </div>
              </div>

              {/* Pin Requirements */}
              <div>
                <label className="block text-sm font-medium text-[#a1a1a6] mb-3">Pin Requirements</label>
                <div className="flex gap-6">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.requires_digital_pin}
                      onChange={(e) => setFormData({ ...formData, requires_digital_pin: e.target.checked })}
                      className="w-4 h-4 rounded border-[#2a2a2f] bg-[#111113] text-amber-500 focus:ring-amber-500/50"
                    />
                    <span className="text-sm">Requires Digital Pin</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.requires_analog_pin}
                      onChange={(e) => setFormData({ ...formData, requires_analog_pin: e.target.checked })}
                      className="w-4 h-4 rounded border-[#2a2a2f] bg-[#111113] text-amber-500 focus:ring-amber-500/50"
                    />
                    <span className="text-sm">Requires Analog Pin</span>
                  </label>
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
                {isSaving ? 'Saving...' : (editingModel ? 'Save Changes' : 'Create Model')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
