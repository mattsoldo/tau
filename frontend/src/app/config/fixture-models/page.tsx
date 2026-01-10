'use client';

import { useState, useEffect, useCallback } from 'react';
import { API_URL } from '@/utils/api';

type FixtureType = 'simple_dimmable' | 'tunable_white' | 'dim_to_warm' | 'non_dimmable' | 'other';

interface FixtureModel {
  id: number;
  manufacturer: string;
  model: string;
  description: string | null;
  type: FixtureType;
  dmx_footprint: number;
  cct_min_kelvin: number;
  cct_max_kelvin: number;
  // Planckian locus color mixing parameters
  warm_xy_x: number | null;
  warm_xy_y: number | null;
  cool_xy_x: number | null;
  cool_xy_y: number | null;
  warm_lumens: number | null;
  cool_lumens: number | null;
  gamma: number | null;
  created_at: string;
}

const typeLabels: Record<FixtureType, { label: string; color: string }> = {
  simple_dimmable: { label: 'Simple Dimmable', color: 'bg-blue-500/15 text-blue-400 border-blue-500/30' },
  tunable_white: { label: 'Tunable White', color: 'bg-amber-500/15 text-amber-400 border-amber-500/30' },
  dim_to_warm: { label: 'Dim to Warm', color: 'bg-orange-500/15 text-orange-400 border-orange-500/30' },
  non_dimmable: { label: 'Non-Dimmable', color: 'bg-gray-500/15 text-gray-400 border-gray-500/30' },
  other: { label: 'Other', color: 'bg-purple-500/15 text-purple-400 border-purple-500/30' },
};

// DMX footprint is derived from fixture type (not user-editable)
const dmxFootprintByType: Record<FixtureType, number> = {
  simple_dimmable: 1,
  tunable_white: 2,
  dim_to_warm: 1,
  non_dimmable: 1,
  other: 1,
};

// Form data uses strings for numeric inputs to allow empty input
interface FormData {
  manufacturer: string;
  model: string;
  description: string | null;
  type: FixtureType;
  cct_kelvin: string;       // Single CCT for simple_dimmable, dim_to_warm
  cct_min_kelvin: string;   // Range min for tunable_white
  cct_max_kelvin: string;   // Range max for tunable_white
  // Planckian locus color mixing parameters (for tunable_white)
  warm_xy_x: string;
  warm_xy_y: string;
  cool_xy_x: string;
  cool_xy_y: string;
  warm_lumens: string;
  cool_lumens: string;
  gamma: string;
}

// Helper to determine if type uses single CCT or range
const usesCctRange = (type: FixtureType) => type === 'tunable_white';
const usesSingleCct = (type: FixtureType) => type === 'simple_dimmable' || type === 'dim_to_warm';
const usesNoCct = (type: FixtureType) => type === 'non_dimmable';

const emptyFormData: FormData = {
  manufacturer: '',
  model: '',
  description: null,
  type: 'simple_dimmable',
  cct_kelvin: '',
  cct_min_kelvin: '',
  cct_max_kelvin: '',
  warm_xy_x: '',
  warm_xy_y: '',
  cool_xy_x: '',
  cool_xy_y: '',
  warm_lumens: '',
  cool_lumens: '',
  gamma: '2.2',
};

export default function FixtureModelsPage() {
  const [models, setModels] = useState<FixtureModel[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingModel, setEditingModel] = useState<FixtureModel | null>(null);
  const [formData, setFormData] = useState<FormData>(emptyFormData);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // Fetch fixture models from API
  const fetchModels = useCallback(async () => {
    try {
      setError(null);
      const response = await fetch(`${API_URL}/api/fixtures/models`);
      if (!response.ok) {
        throw new Error(`Failed to fetch: ${response.status}`);
      }
      const data = await response.json();
      setModels(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load fixture models');
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

  const openEditModal = (model: FixtureModel) => {
    setEditingModel(model);
    // For single-CCT types, use cct_min_kelvin as the single value
    const singleCct = usesSingleCct(model.type) ? (model.cct_min_kelvin?.toString() || '') : '';
    setFormData({
      manufacturer: model.manufacturer,
      model: model.model,
      description: model.description,
      type: model.type,
      cct_kelvin: singleCct,
      cct_min_kelvin: model.cct_min_kelvin?.toString() || '',
      cct_max_kelvin: model.cct_max_kelvin?.toString() || '',
      warm_xy_x: model.warm_xy_x?.toString() || '',
      warm_xy_y: model.warm_xy_y?.toString() || '',
      cool_xy_x: model.cool_xy_x?.toString() || '',
      cool_xy_y: model.cool_xy_y?.toString() || '',
      warm_lumens: model.warm_lumens?.toString() || '',
      cool_lumens: model.cool_lumens?.toString() || '',
      gamma: model.gamma?.toString() || '2.2',
    });
    setIsModalOpen(true);
  };

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);

    try {
      // Build CCT values based on fixture type
      let cctMin: number | null = null;
      let cctMax: number | null = null;

      if (usesCctRange(formData.type)) {
        // Tunable white: use range values
        cctMin = parseInt(formData.cct_min_kelvin) || null;
        cctMax = parseInt(formData.cct_max_kelvin) || null;
      } else if (usesSingleCct(formData.type)) {
        // Simple dimmable / dim to warm: single CCT stored in both fields
        const singleCct = parseInt(formData.cct_kelvin) || null;
        cctMin = singleCct;
        cctMax = singleCct;
      }
      // non_dimmable and other: leave as null

      // Build the payload
      const payload: Record<string, unknown> = {
        manufacturer: formData.manufacturer,
        model: formData.model,
        description: formData.description || null,
        type: formData.type,
        dmx_footprint: dmxFootprintByType[formData.type],
        cct_min_kelvin: cctMin,
        cct_max_kelvin: cctMax,
      };

      // Add Planckian locus parameters for tunable_white
      if (formData.type === 'tunable_white') {
        const warmXY_x = parseFloat(formData.warm_xy_x);
        const warmXY_y = parseFloat(formData.warm_xy_y);
        const coolXY_x = parseFloat(formData.cool_xy_x);
        const coolXY_y = parseFloat(formData.cool_xy_y);
        const warmLumens = parseInt(formData.warm_lumens);
        const coolLumens = parseInt(formData.cool_lumens);
        const gamma = parseFloat(formData.gamma);

        if (!isNaN(warmXY_x)) payload.warm_xy_x = warmXY_x;
        if (!isNaN(warmXY_y)) payload.warm_xy_y = warmXY_y;
        if (!isNaN(coolXY_x)) payload.cool_xy_x = coolXY_x;
        if (!isNaN(coolXY_y)) payload.cool_xy_y = coolXY_y;
        if (!isNaN(warmLumens)) payload.warm_lumens = warmLumens;
        if (!isNaN(coolLumens)) payload.cool_lumens = coolLumens;
        if (!isNaN(gamma)) payload.gamma = gamma;
      }

      let response: Response;

      if (editingModel) {
        // Update existing model
        response = await fetch(`${API_URL}/api/fixtures/models/${editingModel.id}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
      } else {
        // Create new model
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

      // Refresh the list
      await fetchModels();
      setIsModalOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save fixture model');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    setError(null);

    try {
      const response = await fetch(`${API_URL}/api/fixtures/models/${id}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Failed to delete: ${response.status}`);
      }

      // Refresh the list
      await fetchModels();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete fixture model');
    } finally {
      setDeleteConfirm(null);
    }
  };

  // Check if form is valid for submission
  const isFormValid = () => {
    if (!formData.manufacturer || !formData.model) return false;

    // CCT validation based on fixture type
    if (usesCctRange(formData.type)) {
      // Tunable white: need valid range
      const minCct = parseInt(formData.cct_min_kelvin);
      const maxCct = parseInt(formData.cct_max_kelvin);
      if (!minCct || !maxCct || minCct < 1000 || maxCct < 1000 || minCct > maxCct) return false;
    } else if (usesSingleCct(formData.type)) {
      // Simple dimmable / dim to warm: need single valid CCT
      const cct = parseInt(formData.cct_kelvin);
      if (!cct || cct < 1000 || cct > 10000) return false;
    }
    // non_dimmable and other: no CCT required

    return true;
  };

  if (isLoading) {
    return (
      <div className="p-8 flex items-center justify-center">
        <div className="text-[#636366]">Loading fixture models...</div>
      </div>
    );
  }

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-semibold">Fixture Models</h1>
          <p className="text-[#636366] mt-1">Define fixture types with DMX footprint and CCT characteristics</p>
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
                <th className="px-6 py-4 text-left text-xs font-medium text-[#636366] uppercase tracking-wider">Calibration</th>
                <th className="px-6 py-4 text-right text-xs font-medium text-[#636366] uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#2a2a2f]">
              {models.map((model) => (
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
                      <span className="font-mono text-sm">
                        {model.cct_min_kelvin}K - {model.cct_max_kelvin}K
                      </span>
                    )}
                  </td>
                  <td className="px-6 py-4">
                    {model.type === 'tunable_white' ? (
                      // Full calibration: xy + lumens
                      model.warm_xy_x && model.cool_xy_x && model.warm_lumens && model.cool_lumens ? (
                        <span className="inline-flex items-center gap-1.5 text-sm text-green-400">
                          <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z" clipRule="evenodd" />
                          </svg>
                          Calibrated
                        </span>
                      // Approximate calibration: lumens only (xy derived from CCT)
                      ) : model.warm_lumens && model.cool_lumens ? (
                        <span className="inline-flex items-center gap-1.5 text-sm text-amber-400">
                          <span className="text-base font-medium">~</span>
                          Calibrated
                        </span>
                      // Basic: no calibration data
                      ) : (
                        <span className="inline-flex items-center gap-1.5 text-sm text-[#636366]">
                          <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-8-5a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 0110 5zm0 10a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
                          </svg>
                          Basic
                        </span>
                      )
                    ) : (
                      <span className="text-[#636366]">—</span>
                    )}
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
        {models.length} fixture model{models.length !== 1 ? 's' : ''} configured
      </div>

      {/* Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
          <div className="bg-[#161619] border border-[#2a2a2f] rounded-2xl w-full max-w-lg mx-4 shadow-2xl">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-[#2a2a2f]">
              <h2 className="text-lg font-semibold">
                {editingModel ? 'Edit Fixture Model' : 'New Fixture Model'}
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
                    placeholder="e.g., Cree"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Model</label>
                  <input
                    type="text"
                    value={formData.model}
                    onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                    className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white placeholder-[#636366] focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                    placeholder="e.g., TW-200"
                  />
                </div>
              </div>

              {/* Description */}
              <div>
                <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Description</label>
                <input
                  type="text"
                  value={formData.description || ''}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value || null })}
                  className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white placeholder-[#636366] focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                  placeholder="Optional description"
                />
              </div>

              {/* Type & DMX Footprint */}
              <div className="grid grid-cols-3 gap-4">
                <div className="col-span-2">
                  <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Fixture Type</label>
                  <select
                    value={formData.type}
                    onChange={(e) => setFormData({ ...formData, type: e.target.value as FixtureType })}
                    className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
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
                    {dmxFootprintByType[formData.type]} ch
                  </div>
                </div>
              </div>

              {/* CCT - Single value for simple_dimmable and dim_to_warm */}
              {usesSingleCct(formData.type) && (
                <div>
                  <label className="block text-sm font-medium text-[#a1a1a6] mb-2">
                    {formData.type === 'dim_to_warm' ? 'Warm CCT (K)' : 'CCT (K)'}
                  </label>
                  <input
                    type="number"
                    min="1000"
                    max="10000"
                    value={formData.cct_kelvin}
                    onChange={(e) => setFormData({ ...formData, cct_kelvin: e.target.value })}
                    className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white placeholder-[#4a4a4f] focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                    placeholder={formData.type === 'dim_to_warm' ? 'e.g., 2200' : 'e.g., 2700'}
                  />
                  <p className="text-xs text-[#636366] mt-1">
                    {formData.type === 'dim_to_warm'
                      ? 'The warmest color temperature when dimmed'
                      : 'Fixed color temperature of the fixture'}
                  </p>
                </div>
              )}

              {/* CCT Range - For tunable_white */}
              {usesCctRange(formData.type) && (
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Min CCT (K)</label>
                    <input
                      type="number"
                      min="1000"
                      max="10000"
                      value={formData.cct_min_kelvin}
                      onChange={(e) => setFormData({ ...formData, cct_min_kelvin: e.target.value })}
                      className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white placeholder-[#4a4a4f] focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                      placeholder="e.g., 2700"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Max CCT (K)</label>
                    <input
                      type="number"
                      min="1000"
                      max="10000"
                      value={formData.cct_max_kelvin}
                      onChange={(e) => setFormData({ ...formData, cct_max_kelvin: e.target.value })}
                      className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white placeholder-[#4a4a4f] focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                      placeholder="e.g., 6500"
                    />
                  </div>
                </div>
              )}

              {/* Color Mixing Parameters (Planckian Locus) */}
              {formData.type === 'tunable_white' && (
                <div className="space-y-4 pt-2">
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-px bg-[#2a2a2f]" />
                    <span className="text-xs font-medium text-[#636366] uppercase tracking-wider">Color Calibration</span>
                    <div className="flex-1 h-px bg-[#2a2a2f]" />
                  </div>
                  <p className="text-xs text-[#636366]">
                    Optional: CIE 1931 xy chromaticity coordinates and luminous flux for accurate Planckian locus color mixing
                  </p>

                  {/* Warm LED Parameters */}
                  <div>
                    <label className="block text-sm font-medium text-amber-400/80 mb-2">Warm LED</label>
                    <div className="grid grid-cols-3 gap-3">
                      <div>
                        <label className="block text-xs text-[#636366] mb-1">x</label>
                        <input
                          type="number"
                          step="0.0001"
                          min="0"
                          max="1"
                          value={formData.warm_xy_x}
                          onChange={(e) => setFormData({ ...formData, warm_xy_x: e.target.value })}
                          className="w-full px-3 py-2 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white text-sm placeholder-[#4a4a4f] focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                          placeholder="0.5268"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-[#636366] mb-1">y</label>
                        <input
                          type="number"
                          step="0.0001"
                          min="0"
                          max="1"
                          value={formData.warm_xy_y}
                          onChange={(e) => setFormData({ ...formData, warm_xy_y: e.target.value })}
                          className="w-full px-3 py-2 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white text-sm placeholder-[#4a4a4f] focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                          placeholder="0.4133"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-[#636366] mb-1">Lumens</label>
                        <input
                          type="number"
                          min="1"
                          value={formData.warm_lumens}
                          onChange={(e) => setFormData({ ...formData, warm_lumens: e.target.value })}
                          className="w-full px-3 py-2 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white text-sm placeholder-[#4a4a4f] focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                          placeholder="800"
                        />
                      </div>
                    </div>
                  </div>

                  {/* Cool LED Parameters */}
                  <div>
                    <label className="block text-sm font-medium text-blue-400/80 mb-2">Cool LED</label>
                    <div className="grid grid-cols-3 gap-3">
                      <div>
                        <label className="block text-xs text-[#636366] mb-1">x</label>
                        <input
                          type="number"
                          step="0.0001"
                          min="0"
                          max="1"
                          value={formData.cool_xy_x}
                          onChange={(e) => setFormData({ ...formData, cool_xy_x: e.target.value })}
                          className="w-full px-3 py-2 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white text-sm placeholder-[#4a4a4f] focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                          placeholder="0.3135"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-[#636366] mb-1">y</label>
                        <input
                          type="number"
                          step="0.0001"
                          min="0"
                          max="1"
                          value={formData.cool_xy_y}
                          onChange={(e) => setFormData({ ...formData, cool_xy_y: e.target.value })}
                          className="w-full px-3 py-2 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white text-sm placeholder-[#4a4a4f] focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                          placeholder="0.3237"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-[#636366] mb-1">Lumens</label>
                        <input
                          type="number"
                          min="1"
                          value={formData.cool_lumens}
                          onChange={(e) => setFormData({ ...formData, cool_lumens: e.target.value })}
                          className="w-full px-3 py-2 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white text-sm placeholder-[#4a4a4f] focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                          placeholder="900"
                        />
                      </div>
                    </div>
                  </div>

                  {/* Gamma */}
                  <div>
                    <label className="block text-sm font-medium text-[#a1a1a6] mb-2">Gamma Correction</label>
                    <input
                      type="number"
                      step="0.1"
                      min="1"
                      max="4"
                      value={formData.gamma}
                      onChange={(e) => setFormData({ ...formData, gamma: e.target.value })}
                      className="w-full px-3 py-2.5 bg-[#111113] border border-[#2a2a2f] rounded-lg text-white placeholder-[#4a4a4f] focus:outline-none focus:border-amber-500/50 focus:ring-1 focus:ring-amber-500/50"
                      placeholder="2.2"
                    />
                    <p className="text-xs text-[#636366] mt-1">PWM-to-light gamma (2.2 is typical for LEDs)</p>
                  </div>
                </div>
              )}
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
