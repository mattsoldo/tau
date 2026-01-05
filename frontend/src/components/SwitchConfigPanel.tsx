'use client';

import { useState, useEffect } from 'react';
import { api } from '../utils/api';
import type { Switch, SwitchModel, SwitchType, Group } from '../types/tau';

export default function SwitchConfigPanel() {
  const [switches, setSwitches] = useState<Switch[]>([]);
  const [switchModels, setSwitchModels] = useState<SwitchModel[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingSwitch, setEditingSwitch] = useState<Switch | null>(null);

  // Fetch data
  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [switchesData, modelsData, groupsData] = await Promise.all([
        api.switches.list(),
        api.switchModels.list(),
        api.groups.list(),
      ]);
      setSwitches(switchesData);
      setSwitchModels(modelsData);
      setGroups(groupsData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load switches');
    } finally {
      setIsLoading(false);
    }
  };

  const handleUpdateSwitch = async (
    switchId: number,
    updates: { switch_type?: SwitchType; invert_reading?: boolean }
  ) => {
    try {
      await api.switches.update(switchId, updates);
      await loadData(); // Reload data
      setEditingSwitch(null);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update switch');
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="w-6 h-6 border-2 border-amber-500 border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  if (switches.length === 0) {
    return (
      <div className="text-center py-8 text-[#636366]">
        <svg className="w-12 h-12 mx-auto mb-3 opacity-50" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.75 9.75l4.5 4.5m0-4.5l-4.5 4.5M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <p>No switches configured</p>
        <p className="text-sm mt-1">Configure switches via the API to manage them here</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
          {error}
        </div>
      )}

      <div className="space-y-3">
        {switches.map((sw) => {
          const targetGroup = groups.find((g) => g.id === sw.target_group_id);
          const isEditing = editingSwitch?.id === sw.id;

          return (
            <div
              key={sw.id}
              className="p-4 bg-[#2a2a2f] rounded-lg border border-[#3a3a3f] hover:border-amber-500/30 transition-colors"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 space-y-2">
                  {/* Switch Name and Pin */}
                  <div className="flex items-center gap-3">
                    <h3 className="font-medium">
                      {sw.name || `Switch ${sw.id}`}
                    </h3>
                    {sw.labjack_digital_pin !== null && sw.labjack_digital_pin !== undefined && (
                      <span className="text-xs px-2 py-1 bg-amber-500/10 text-amber-400 rounded-md font-mono">
                        FIO{sw.labjack_digital_pin}
                      </span>
                    )}
                  </div>

                  {/* Target Group */}
                  {targetGroup && (
                    <div className="text-sm text-[#636366]">
                      Controls: <span className="text-[#a1a1a6]">{targetGroup.name}</span>
                    </div>
                  )}

                  {/* Switch Configuration */}
                  <div className="flex items-center gap-4 text-sm">
                    {isEditing ? (
                      <>
                        {/* Switch Type Selector */}
                        <div className="flex items-center gap-2">
                          <label className="text-[#636366]">Type:</label>
                          <select
                            value={editingSwitch.switch_type}
                            onChange={(e) =>
                              setEditingSwitch({
                                ...editingSwitch,
                                switch_type: e.target.value as SwitchType,
                              })
                            }
                            className="px-2 py-1 bg-[#1a1a1f] border border-[#3a3a3f] rounded text-sm"
                          >
                            <option value="normally-closed">Normally Closed</option>
                            <option value="normally-open">Normally Open</option>
                          </select>
                        </div>

                        {/* Invert Reading Checkbox */}
                        <div className="flex items-center gap-2">
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={editingSwitch.invert_reading}
                              onChange={(e) =>
                                setEditingSwitch({
                                  ...editingSwitch,
                                  invert_reading: e.target.checked,
                                })
                              }
                              className="w-4 h-4 rounded border-[#3a3a3f] bg-[#1a1a1f] text-amber-500 focus:ring-amber-500/30"
                            />
                            <span className="text-[#636366]">Invert Logic</span>
                          </label>
                        </div>

                        {/* Save/Cancel Buttons */}
                        <div className="flex items-center gap-2 ml-auto">
                          <button
                            onClick={() =>
                              handleUpdateSwitch(sw.id, {
                                switch_type: editingSwitch.switch_type,
                                invert_reading: editingSwitch.invert_reading,
                              })
                            }
                            className="px-3 py-1 bg-amber-500 hover:bg-amber-600 text-black rounded text-sm font-medium transition-colors"
                          >
                            Save
                          </button>
                          <button
                            onClick={() => setEditingSwitch(null)}
                            className="px-3 py-1 bg-[#3a3a3f] hover:bg-[#4a4a4f] rounded text-sm transition-colors"
                          >
                            Cancel
                          </button>
                        </div>
                      </>
                    ) : (
                      <>
                        {/* Display Mode */}
                        <div className="flex items-center gap-1">
                          <span className="text-[#636366]">Type:</span>
                          <span className="text-[#a1a1a6] font-mono text-xs">
                            {sw.switch_type === 'normally-closed' ? 'NC' : 'NO'}
                          </span>
                        </div>

                        {sw.invert_reading && (
                          <span className="text-xs px-2 py-1 bg-blue-500/10 text-blue-400 rounded-md">
                            Inverted
                          </span>
                        )}

                        {/* Edit Button */}
                        <button
                          onClick={() => setEditingSwitch(sw)}
                          className="ml-auto px-3 py-1 bg-[#3a3a3f] hover:bg-[#4a4a4f] rounded text-sm transition-colors"
                        >
                          Configure
                        </button>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Info Box */}
      <div className="mt-4 p-4 bg-blue-500/5 border border-blue-500/20 rounded-lg text-sm text-blue-300">
        <div className="font-medium mb-2">Switch Configuration Guide:</div>
        <ul className="space-y-1 text-xs text-blue-300/80">
          <li>• <strong>Normally Closed (NC):</strong> Circuit closed when not pressed, opens when pressed</li>
          <li>• <strong>Normally Open (NO):</strong> Circuit open when not pressed, closes when pressed</li>
          <li>• <strong>Invert Logic:</strong> Flip the reading in software (useful for switches without pull-ups)</li>
        </ul>
      </div>
    </div>
  );
}
