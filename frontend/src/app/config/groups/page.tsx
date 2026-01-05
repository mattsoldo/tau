'use client';

import { useState, useEffect, useCallback } from 'react';

const API_URL = ''; // Use relative paths for nginx proxy

// === Types ===

interface Group {
  id: number;
  name: string;
  description: string | null;
  circadian_enabled: boolean;
  circadian_profile_id: number | null;
  created_at: string;
}

interface CircadianProfile {
  id: number;
  name: string;
  description: string | null;
}

interface Fixture {
  id: number;
  name: string;
  dmx_channel_start: number;
}

interface GroupFormData {
  name: string;
  description: string;
  circadian_enabled: boolean;
  circadian_profile_id: string;
}

const emptyGroupFormData: GroupFormData = {
  name: '',
  description: '',
  circadian_enabled: false,
  circadian_profile_id: '',
};

export default function GroupsPage() {
  // Data state
  const [groups, setGroups] = useState<Group[]>([]);
  const [circadianProfiles, setCircadianProfiles] = useState<CircadianProfile[]>([]);
  const [fixtures, setFixtures] = useState<Fixture[]>([]);
  const [groupFixtures, setGroupFixtures] = useState<Map<number, number[]>>(new Map());
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Group modal state
  const [isGroupModalOpen, setIsGroupModalOpen] = useState(false);
  const [editingGroup, setEditingGroup] = useState<Group | null>(null);
  const [groupFormData, setGroupFormData] = useState<GroupFormData>(emptyGroupFormData);
  const [isSavingGroup, setIsSavingGroup] = useState(false);
  const [groupDeleteConfirm, setGroupDeleteConfirm] = useState<number | null>(null);

  // Fixtures modal state
  const [isFixturesModalOpen, setIsFixturesModalOpen] = useState(false);
  const [managingGroupId, setManagingGroupId] = useState<number | null>(null);
  const [selectedFixtureIds, setSelectedFixtureIds] = useState<Set<number>>(new Set());

  // Sort state
  type SortColumn = 'name' | 'fixtures' | 'circadian';
  type SortDirection = 'asc' | 'desc';
  const [sortColumn, setSortColumn] = useState<SortColumn>('name');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');

  // Fetch all data
  const fetchData = useCallback(async () => {
    try {
      const [groupsRes, profilesRes, fixturesRes] = await Promise.all([
        fetch(`${API_URL}/api/groups/`),
        fetch(`${API_URL}/api/circadian/`),
        fetch(`${API_URL}/api/fixtures/`),
      ]);

      if (!groupsRes.ok) throw new Error('Failed to fetch groups');
      if (!profilesRes.ok) throw new Error('Failed to fetch circadian profiles');
      if (!fixturesRes.ok) throw new Error('Failed to fetch fixtures');

      const [groupsData, profilesData, fixturesData] = await Promise.all([
        groupsRes.json(),
        profilesRes.json(),
        fixturesRes.json(),
      ]);

      setGroups(groupsData);
      setCircadianProfiles(profilesData);
      setFixtures(fixturesData);

      // Fetch fixtures for each group
      const fixtureMap = new Map<number, number[]>();
      await Promise.all(
        groupsData.map(async (group: Group) => {
          try {
            const res = await fetch(`${API_URL}/api/groups/${group.id}/fixtures`);
            if (res.ok) {
              const groupFixturesList = await res.json();
              fixtureMap.set(group.id, groupFixturesList.map((f: Fixture) => f.id));
            }
          } catch {
            // Ignore errors for individual groups
          }
        })
      );
      setGroupFixtures(fixtureMap);

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

  // Sort groups
  const sortedGroups = [...groups].sort((a, b) => {
    let comparison = 0;
    switch (sortColumn) {
      case 'name':
        comparison = a.name.localeCompare(b.name);
        break;
      case 'fixtures':
        comparison = (groupFixtures.get(a.id)?.length ?? 0) - (groupFixtures.get(b.id)?.length ?? 0);
        break;
      case 'circadian':
        comparison = (a.circadian_enabled ? 1 : 0) - (b.circadian_enabled ? 1 : 0);
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

  // Group CRUD operations
  const openCreateGroupModal = () => {
    setEditingGroup(null);
    setGroupFormData(emptyGroupFormData);
    setIsGroupModalOpen(true);
  };

  const openEditGroupModal = (group: Group) => {
    setEditingGroup(group);
    setGroupFormData({
      name: group.name,
      description: group.description || '',
      circadian_enabled: group.circadian_enabled,
      circadian_profile_id: group.circadian_profile_id?.toString() || '',
    });
    setIsGroupModalOpen(true);
  };

  const handleSaveGroup = async () => {
    if (!groupFormData.name.trim()) {
      setError('Group name is required');
      return;
    }

    setIsSavingGroup(true);
    try {
      const payload = {
        name: groupFormData.name.trim(),
        description: groupFormData.description.trim() || null,
        circadian_enabled: groupFormData.circadian_enabled,
        circadian_profile_id: groupFormData.circadian_profile_id
          ? parseInt(groupFormData.circadian_profile_id)
          : null,
      };

      const url = editingGroup
        ? `${API_URL}/api/groups/${editingGroup.id}`
        : `${API_URL}/api/groups/`;

      const res = await fetch(url, {
        method: editingGroup ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to save group');
      }

      setIsGroupModalOpen(false);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save group');
    } finally {
      setIsSavingGroup(false);
    }
  };

  const handleDeleteGroup = async (groupId: number) => {
    try {
      const res = await fetch(`${API_URL}/api/groups/${groupId}`, {
        method: 'DELETE',
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to delete group');
      }

      setGroupDeleteConfirm(null);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete group');
    }
  };

  // Fixture membership management
  const openFixturesModal = (groupId: number) => {
    setManagingGroupId(groupId);
    setSelectedFixtureIds(new Set(groupFixtures.get(groupId) || []));
    setIsFixturesModalOpen(true);
  };

  const toggleFixtureSelection = (fixtureId: number) => {
    setSelectedFixtureIds(prev => {
      const next = new Set(prev);
      if (next.has(fixtureId)) {
        next.delete(fixtureId);
      } else {
        next.add(fixtureId);
      }
      return next;
    });
  };

  const handleSaveFixtures = async () => {
    if (managingGroupId === null) return;

    try {
      const currentFixtures = new Set(groupFixtures.get(managingGroupId) || []);
      const toAdd = [...selectedFixtureIds].filter(id => !currentFixtures.has(id));
      const toRemove = [...currentFixtures].filter(id => !selectedFixtureIds.has(id));

      // Add new fixtures
      await Promise.all(
        toAdd.map(fixtureId =>
          fetch(`${API_URL}/api/groups/${managingGroupId}/fixtures`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ fixture_id: fixtureId }),
          })
        )
      );

      // Remove fixtures
      await Promise.all(
        toRemove.map(fixtureId =>
          fetch(`${API_URL}/api/groups/${managingGroupId}/fixtures/${fixtureId}`, {
            method: 'DELETE',
          })
        )
      );

      setIsFixturesModalOpen(false);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update fixtures');
    }
  };

  const getProfileName = (profileId: number | null) => {
    if (!profileId) return '—';
    const profile = circadianProfiles.find(p => p.id === profileId);
    return profile?.name || 'Unknown';
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Groups</h1>
          <p className="text-[#636366] mt-1">Organize fixtures into groups for collective control</p>
        </div>
        <button
          onClick={openCreateGroupModal}
          className="px-4 py-2.5 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors flex items-center gap-2"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          New Group
        </button>
      </div>

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
      ) : groups.length === 0 ? (
        <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] p-12 text-center">
          <div className="w-16 h-16 mx-auto mb-4 text-[#636366]">
            <svg fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold mb-2">No Groups Configured</h3>
          <p className="text-[#636366] mb-4">Create a group to organize your fixtures.</p>
          <button
            onClick={openCreateGroupModal}
            className="inline-flex items-center gap-2 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors"
          >
            Create Group
          </button>
        </div>
      ) : (
        /* Groups Table */
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
                <th className="text-left px-4 py-3 text-sm font-medium text-[#a1a1a6]">
                  Description
                </th>
                <th
                  className="text-left px-4 py-3 text-sm font-medium text-[#a1a1a6] cursor-pointer hover:text-white"
                  onClick={() => handleSort('fixtures')}
                >
                  Fixtures <SortIndicator column="fixtures" />
                </th>
                <th
                  className="text-left px-4 py-3 text-sm font-medium text-[#a1a1a6] cursor-pointer hover:text-white"
                  onClick={() => handleSort('circadian')}
                >
                  Circadian <SortIndicator column="circadian" />
                </th>
                <th className="text-left px-4 py-3 text-sm font-medium text-[#a1a1a6]">
                  Profile
                </th>
                <th className="text-right px-4 py-3 text-sm font-medium text-[#a1a1a6]">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedGroups.map((group) => {
                const fixtureCount = groupFixtures.get(group.id)?.length ?? 0;
                return (
                  <tr
                    key={group.id}
                    className="border-b border-[#2a2a2f] last:border-b-0 hover:bg-white/[0.02]"
                  >
                    <td className="px-4 py-3">
                      <span className="font-medium">{group.name}</span>
                    </td>
                    <td className="px-4 py-3 text-[#a1a1a6] text-sm max-w-xs truncate">
                      {group.description || '—'}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => openFixturesModal(group.id)}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-[#2a2a2f] hover:bg-[#3a3a3f] rounded-md text-sm transition-colors"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M12 18v-5.25m0 0a6.01 6.01 0 001.5-.189m-1.5.189a6.01 6.01 0 01-1.5-.189m3.75 7.478a12.06 12.06 0 01-4.5 0m3.75 2.383a14.406 14.406 0 01-3 0M14.25 18v-.192c0-.983.658-1.823 1.508-2.316a7.5 7.5 0 10-7.517 0c.85.493 1.509 1.333 1.509 2.316V18" />
                        </svg>
                        {fixtureCount} fixture{fixtureCount !== 1 ? 's' : ''}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      {group.circadian_enabled ? (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-amber-500/15 text-amber-400 border border-amber-500/30 rounded-full text-xs font-medium">
                          <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M12 2.25a.75.75 0 01.75.75v2.25a.75.75 0 01-1.5 0V3a.75.75 0 01.75-.75zM7.5 12a4.5 4.5 0 119 0 4.5 4.5 0 01-9 0z" />
                          </svg>
                          Enabled
                        </span>
                      ) : (
                        <span className="text-[#636366] text-sm">Disabled</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-sm text-[#a1a1a6]">
                      {getProfileName(group.circadian_profile_id)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => openEditGroupModal(group)}
                          className="p-2 hover:bg-white/5 rounded-lg transition-colors text-[#a1a1a6] hover:text-white"
                          title="Edit"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
                          </svg>
                        </button>
                        {groupDeleteConfirm === group.id ? (
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => handleDeleteGroup(group.id)}
                              className="px-2 py-1 bg-red-500 hover:bg-red-600 text-white text-xs rounded transition-colors"
                            >
                              Confirm
                            </button>
                            <button
                              onClick={() => setGroupDeleteConfirm(null)}
                              className="px-2 py-1 bg-[#2a2a2f] hover:bg-[#3a3a3f] text-white text-xs rounded transition-colors"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setGroupDeleteConfirm(group.id)}
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
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Group Modal */}
      {isGroupModalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] w-full max-w-md mx-4 overflow-hidden">
            <div className="px-6 py-4 border-b border-[#2a2a2f]">
              <h2 className="text-lg font-semibold">
                {editingGroup ? 'Edit Group' : 'Create Group'}
              </h2>
            </div>
            <div className="p-6 space-y-4">
              {/* Name */}
              <div>
                <label className="block text-sm font-medium text-[#a1a1a6] mb-1.5">
                  Name <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={groupFormData.name}
                  onChange={(e) => setGroupFormData({ ...groupFormData, name: e.target.value })}
                  placeholder="e.g., Living Room"
                  className="w-full px-3 py-2 bg-[#0a0a0b] border border-[#2a2a2f] rounded-lg text-white placeholder:text-[#636366] focus:outline-none focus:border-amber-500"
                />
              </div>

              {/* Description */}
              <div>
                <label className="block text-sm font-medium text-[#a1a1a6] mb-1.5">
                  Description
                </label>
                <textarea
                  value={groupFormData.description}
                  onChange={(e) => setGroupFormData({ ...groupFormData, description: e.target.value })}
                  placeholder="Optional description..."
                  rows={2}
                  className="w-full px-3 py-2 bg-[#0a0a0b] border border-[#2a2a2f] rounded-lg text-white placeholder:text-[#636366] focus:outline-none focus:border-amber-500 resize-none"
                />
              </div>

              {/* Circadian Enabled */}
              <div className="flex items-center justify-between">
                <div>
                  <label className="block text-sm font-medium text-white">
                    Circadian Rhythm
                  </label>
                  <p className="text-xs text-[#636366]">Auto-adjust brightness and color temperature</p>
                </div>
                <button
                  type="button"
                  onClick={() => setGroupFormData({ ...groupFormData, circadian_enabled: !groupFormData.circadian_enabled })}
                  className={`relative w-12 h-7 rounded-full transition-colors ${
                    groupFormData.circadian_enabled ? 'bg-amber-500' : 'bg-[#3a3a3f]'
                  }`}
                >
                  <div
                    className={`absolute top-1 w-5 h-5 bg-white rounded-full shadow transition-transform ${
                      groupFormData.circadian_enabled ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>

              {/* Circadian Profile */}
              {groupFormData.circadian_enabled && (
                <div>
                  <label className="block text-sm font-medium text-[#a1a1a6] mb-1.5">
                    Circadian Profile
                  </label>
                  <select
                    value={groupFormData.circadian_profile_id}
                    onChange={(e) => setGroupFormData({ ...groupFormData, circadian_profile_id: e.target.value })}
                    className="w-full px-3 py-2 bg-[#0a0a0b] border border-[#2a2a2f] rounded-lg text-white focus:outline-none focus:border-amber-500"
                  >
                    <option value="">Select a profile...</option>
                    {circadianProfiles.map((profile) => (
                      <option key={profile.id} value={profile.id}>
                        {profile.name}
                      </option>
                    ))}
                  </select>
                  {circadianProfiles.length === 0 && (
                    <p className="text-xs text-[#636366] mt-1">
                      No circadian profiles available. Create one first.
                    </p>
                  )}
                </div>
              )}
            </div>
            <div className="px-6 py-4 border-t border-[#2a2a2f] flex justify-end gap-3">
              <button
                onClick={() => setIsGroupModalOpen(false)}
                className="px-4 py-2 bg-[#2a2a2f] hover:bg-[#3a3a3f] text-white rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSaveGroup}
                disabled={isSavingGroup}
                className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors disabled:opacity-50"
              >
                {isSavingGroup ? 'Saving...' : editingGroup ? 'Save Changes' : 'Create Group'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Fixtures Modal */}
      {isFixturesModalOpen && managingGroupId !== null && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] w-full max-w-lg mx-4 overflow-hidden">
            <div className="px-6 py-4 border-b border-[#2a2a2f]">
              <h2 className="text-lg font-semibold">
                Manage Fixtures
              </h2>
              <p className="text-sm text-[#636366]">
                {groups.find(g => g.id === managingGroupId)?.name}
              </p>
            </div>
            <div className="p-6 max-h-96 overflow-y-auto">
              {fixtures.length === 0 ? (
                <p className="text-center text-[#636366] py-4">No fixtures available</p>
              ) : (
                <div className="space-y-2">
                  {fixtures.map((fixture) => (
                    <label
                      key={fixture.id}
                      className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-colors ${
                        selectedFixtureIds.has(fixture.id)
                          ? 'bg-amber-500/10 border border-amber-500/30'
                          : 'bg-[#0a0a0b] border border-[#2a2a2f] hover:border-[#3a3a3f]'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={selectedFixtureIds.has(fixture.id)}
                        onChange={() => toggleFixtureSelection(fixture.id)}
                        className="w-4 h-4 rounded border-[#3a3a3f] bg-[#0a0a0b] text-amber-500 focus:ring-amber-500 focus:ring-offset-0"
                      />
                      <div className="flex-1">
                        <div className="font-medium">{fixture.name}</div>
                        <div className="text-xs text-[#636366]">DMX {fixture.dmx_channel_start}</div>
                      </div>
                    </label>
                  ))}
                </div>
              )}
            </div>
            <div className="px-6 py-4 border-t border-[#2a2a2f] flex justify-between items-center">
              <span className="text-sm text-[#636366]">
                {selectedFixtureIds.size} fixture{selectedFixtureIds.size !== 1 ? 's' : ''} selected
              </span>
              <div className="flex gap-3">
                <button
                  onClick={() => setIsFixturesModalOpen(false)}
                  className="px-4 py-2 bg-[#2a2a2f] hover:bg-[#3a3a3f] text-white rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveFixtures}
                  className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors"
                >
                  Save
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
