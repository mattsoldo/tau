'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';

const API_URL = ''; // Use relative paths for nginx proxy

// === Types ===

interface CircadianKeyframe {
  time: string;      // HH:MM:SS format
  brightness: number; // 0.0-1.0
  cct: number;       // 1000-10000 Kelvin
}

interface CircadianProfile {
  id: number;
  name: string;
  description: string | null;
  keyframes: CircadianKeyframe[];
  created_at: string;
}

interface Group {
  id: number;
  name: string;
  circadian_profile_id: number | null;
}

interface KeyframeFormData {
  time: string;       // HH:MM format for input
  brightness: string; // String for input
  cct: string;        // String for input
}

interface ProfileFormData {
  name: string;
  description: string;
  keyframes: KeyframeFormData[];
}

const emptyKeyframe: KeyframeFormData = {
  time: '12:00',
  brightness: '50',
  cct: '4000',
};

const defaultKeyframes: KeyframeFormData[] = [
  { time: '06:00', brightness: '10', cct: '2700' },
  { time: '08:00', brightness: '80', cct: '4500' },
  { time: '12:00', brightness: '100', cct: '5500' },
  { time: '18:00', brightness: '70', cct: '4000' },
  { time: '21:00', brightness: '30', cct: '2700' },
  { time: '23:00', brightness: '5', cct: '2200' },
];

const emptyFormData: ProfileFormData = {
  name: '',
  description: '',
  keyframes: defaultKeyframes,
};

// Helper to convert HH:MM to HH:MM:SS
function timeToSeconds(time: string): string {
  if (time.length === 5) {
    return `${time}:00`;
  }
  return time;
}

// Helper to convert HH:MM:SS to HH:MM
function timeToMinutes(time: string): string {
  return time.substring(0, 5);
}

// Helper to get time in minutes for sorting
function timeToMinutesValue(time: string): number {
  const parts = time.split(':');
  return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
}

// Helper to format CCT for display
function formatCCT(cct: number): string {
  return `${cct.toLocaleString()}K`;
}

// Helper to get CCT color for preview
function cctToColor(cct: number): string {
  // Approximate CCT to RGB (simplified)
  if (cct <= 2000) return '#ff8a00';
  if (cct <= 2700) return '#ffb347';
  if (cct <= 3500) return '#ffd699';
  if (cct <= 4500) return '#ffecd2';
  if (cct <= 5500) return '#ffffff';
  if (cct <= 6500) return '#e6f2ff';
  return '#cce5ff';
}

export default function CircadianPage() {
  // Data state
  const [profiles, setProfiles] = useState<CircadianProfile[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Modal state
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingProfile, setEditingProfile] = useState<CircadianProfile | null>(null);
  const [formData, setFormData] = useState<ProfileFormData>(emptyFormData);
  const [isSaving, setIsSaving] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);

  // Sort state
  type SortColumn = 'name' | 'keyframes' | 'groups';
  type SortDirection = 'asc' | 'desc';
  const [sortColumn, setSortColumn] = useState<SortColumn>('name');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');

  // Fetch data
  const fetchData = useCallback(async () => {
    try {
      const [profilesRes, groupsRes] = await Promise.all([
        fetch(`${API_URL}/api/circadian/`),
        fetch(`${API_URL}/api/groups/`),
      ]);

      if (!profilesRes.ok) throw new Error('Failed to fetch circadian profiles');
      if (!groupsRes.ok) throw new Error('Failed to fetch groups');

      const [profilesData, groupsData] = await Promise.all([
        profilesRes.json(),
        groupsRes.json(),
      ]);

      setProfiles(profilesData);
      setGroups(groupsData);
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

  // Count groups using each profile
  const profileGroupCounts = useMemo(() => {
    const counts = new Map<number, number>();
    groups.forEach((group) => {
      if (group.circadian_profile_id) {
        counts.set(
          group.circadian_profile_id,
          (counts.get(group.circadian_profile_id) || 0) + 1
        );
      }
    });
    return counts;
  }, [groups]);

  // Sort profiles
  const sortedProfiles = [...profiles].sort((a, b) => {
    let comparison = 0;
    switch (sortColumn) {
      case 'name':
        comparison = a.name.localeCompare(b.name);
        break;
      case 'keyframes':
        comparison = a.keyframes.length - b.keyframes.length;
        break;
      case 'groups':
        comparison = (profileGroupCounts.get(a.id) || 0) - (profileGroupCounts.get(b.id) || 0);
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
    setEditingProfile(null);
    setFormData(emptyFormData);
    setIsModalOpen(true);
  };

  const openEditModal = (profile: CircadianProfile) => {
    setEditingProfile(profile);
    setFormData({
      name: profile.name,
      description: profile.description || '',
      keyframes: profile.keyframes.map((kf) => ({
        time: timeToMinutes(kf.time),
        brightness: (kf.brightness * 100).toFixed(0),
        cct: kf.cct.toString(),
      })),
    });
    setIsModalOpen(true);
  };

  // Keyframe management
  const addKeyframe = () => {
    setFormData({
      ...formData,
      keyframes: [...formData.keyframes, { ...emptyKeyframe }],
    });
  };

  const removeKeyframe = (index: number) => {
    if (formData.keyframes.length <= 2) {
      setError('Minimum 2 keyframes required');
      return;
    }
    setFormData({
      ...formData,
      keyframes: formData.keyframes.filter((_, i) => i !== index),
    });
  };

  const updateKeyframe = (index: number, field: keyof KeyframeFormData, value: string) => {
    const newKeyframes = [...formData.keyframes];
    newKeyframes[index] = { ...newKeyframes[index], [field]: value };
    setFormData({ ...formData, keyframes: newKeyframes });
  };

  const sortKeyframesByTime = () => {
    const sorted = [...formData.keyframes].sort(
      (a, b) => timeToMinutesValue(a.time) - timeToMinutesValue(b.time)
    );
    setFormData({ ...formData, keyframes: sorted });
  };

  // Validate form
  const validateForm = (): string | null => {
    if (!formData.name.trim()) {
      return 'Name is required';
    }
    if (formData.keyframes.length < 2) {
      return 'At least 2 keyframes are required';
    }
    for (let i = 0; i < formData.keyframes.length; i++) {
      const kf = formData.keyframes[i];
      const brightness = parseFloat(kf.brightness);
      const cct = parseInt(kf.cct, 10);

      if (!kf.time.match(/^([0-1][0-9]|2[0-3]):[0-5][0-9]$/)) {
        return `Keyframe ${i + 1}: Invalid time format (use HH:MM)`;
      }
      if (isNaN(brightness) || brightness < 0 || brightness > 100) {
        return `Keyframe ${i + 1}: Brightness must be 0-100`;
      }
      if (isNaN(cct) || cct < 1000 || cct > 10000) {
        return `Keyframe ${i + 1}: CCT must be 1000-10000`;
      }
    }
    return null;
  };

  // Save profile
  const handleSave = async () => {
    const validationError = validateForm();
    if (validationError) {
      setError(validationError);
      return;
    }

    setIsSaving(true);
    try {
      const payload = {
        name: formData.name.trim(),
        description: formData.description.trim() || null,
        keyframes: formData.keyframes.map((kf) => ({
          time: timeToSeconds(kf.time),
          brightness: parseFloat(kf.brightness) / 100, // Convert to 0.0-1.0
          cct: parseInt(kf.cct, 10),
        })),
      };

      const url = editingProfile
        ? `${API_URL}/api/circadian/${editingProfile.id}`
        : `${API_URL}/api/circadian/`;

      const res = await fetch(url, {
        method: editingProfile ? 'PATCH' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to save profile');
      }

      setIsModalOpen(false);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save profile');
    } finally {
      setIsSaving(false);
    }
  };

  // Delete profile
  const handleDelete = async (profileId: number) => {
    try {
      const res = await fetch(`${API_URL}/api/circadian/${profileId}`, {
        method: 'DELETE',
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || 'Failed to delete profile');
      }

      setDeleteConfirm(null);
      await fetchData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete profile');
    }
  };

  // Preview curve component
  const CurvePreview = ({ keyframes }: { keyframes: KeyframeFormData[] }) => {
    const sortedKf = [...keyframes].sort(
      (a, b) => timeToMinutesValue(a.time) - timeToMinutesValue(b.time)
    );

    const points = sortedKf.map((kf) => ({
      x: (timeToMinutesValue(kf.time) / 1440) * 100, // Percentage of day
      y: 100 - parseFloat(kf.brightness || '0'), // Invert for SVG
      cct: parseInt(kf.cct, 10) || 4000,
    }));

    // Create SVG path
    const pathD =
      points.length > 0
        ? `M ${points.map((p) => `${p.x},${p.y}`).join(' L ')}`
        : '';

    return (
      <div className="bg-[#0a0a0b] border border-[#2a2a2f] rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-medium text-[#a1a1a6]">Brightness Curve Preview</span>
          <div className="flex items-center gap-4 text-xs text-[#636366]">
            <span>0:00</span>
            <span>6:00</span>
            <span>12:00</span>
            <span>18:00</span>
            <span>24:00</span>
          </div>
        </div>
        <svg className="w-full h-32" viewBox="0 0 100 100" preserveAspectRatio="none">
          {/* Grid lines */}
          <line x1="0" y1="0" x2="100" y2="0" stroke="#2a2a2f" strokeWidth="0.5" />
          <line x1="0" y1="50" x2="100" y2="50" stroke="#2a2a2f" strokeWidth="0.5" />
          <line x1="0" y1="100" x2="100" y2="100" stroke="#2a2a2f" strokeWidth="0.5" />
          <line x1="25" y1="0" x2="25" y2="100" stroke="#2a2a2f" strokeWidth="0.5" />
          <line x1="50" y1="0" x2="50" y2="100" stroke="#2a2a2f" strokeWidth="0.5" />
          <line x1="75" y1="0" x2="75" y2="100" stroke="#2a2a2f" strokeWidth="0.5" />

          {/* Curve line */}
          {pathD && (
            <path
              d={pathD}
              fill="none"
              stroke="#f59e0b"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}

          {/* Points */}
          {points.map((point, i) => (
            <circle
              key={i}
              cx={point.x}
              cy={point.y}
              r="3"
              fill={cctToColor(point.cct)}
              stroke="#0a0a0b"
              strokeWidth="1"
            />
          ))}
        </svg>
        <div className="flex justify-between mt-2 text-xs text-[#636366]">
          <span>100%</span>
          <span className="text-center flex-1">Brightness</span>
          <span>0%</span>
        </div>
      </div>
    );
  };

  // Profile mini curve for table
  const MiniCurve = ({ profile }: { profile: CircadianProfile }) => {
    const sortedKf = [...profile.keyframes].sort(
      (a, b) => timeToMinutesValue(a.time) - timeToMinutesValue(b.time)
    );

    const points = sortedKf.map((kf) => ({
      x: (timeToMinutesValue(kf.time) / 1440) * 100,
      y: 100 - kf.brightness * 100,
      cct: kf.cct,
    }));

    const pathD =
      points.length > 0
        ? `M ${points.map((p) => `${p.x},${p.y}`).join(' L ')}`
        : '';

    return (
      <svg className="w-24 h-8" viewBox="0 0 100 100" preserveAspectRatio="none">
        <rect x="0" y="0" width="100" height="100" fill="#0a0a0b" rx="4" />
        {pathD && (
          <path
            d={pathD}
            fill="none"
            stroke="#f59e0b"
            strokeWidth="4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}
        {points.map((point, i) => (
          <circle
            key={i}
            cx={point.x}
            cy={point.y}
            r="5"
            fill={cctToColor(point.cct)}
          />
        ))}
      </svg>
    );
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Circadian Profiles</h1>
          <p className="text-[#636366] mt-1">
            Define time-based brightness and color temperature curves
          </p>
        </div>
        <button
          onClick={openCreateModal}
          className="px-4 py-2.5 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors flex items-center gap-2"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          New Profile
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
      ) : profiles.length === 0 ? (
        <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] p-12 text-center">
          <div className="w-16 h-16 mx-auto mb-4 text-[#636366]">
            <svg fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold mb-2">No Circadian Profiles</h3>
          <p className="text-[#636366] mb-4">Create a profile to define brightness and CCT curves.</p>
          <button
            onClick={openCreateModal}
            className="inline-flex items-center gap-2 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors"
          >
            Create Profile
          </button>
        </div>
      ) : (
        /* Profiles Table */
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
                <th className="text-left px-4 py-3 text-sm font-medium text-[#a1a1a6]">
                  Curve
                </th>
                <th
                  className="text-left px-4 py-3 text-sm font-medium text-[#a1a1a6] cursor-pointer hover:text-white"
                  onClick={() => handleSort('keyframes')}
                >
                  Keyframes <SortIndicator column="keyframes" />
                </th>
                <th
                  className="text-left px-4 py-3 text-sm font-medium text-[#a1a1a6] cursor-pointer hover:text-white"
                  onClick={() => handleSort('groups')}
                >
                  Groups <SortIndicator column="groups" />
                </th>
                <th className="text-right px-4 py-3 text-sm font-medium text-[#a1a1a6]">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {sortedProfiles.map((profile) => {
                const groupCount = profileGroupCounts.get(profile.id) || 0;
                return (
                  <tr
                    key={profile.id}
                    className="border-b border-[#2a2a2f] last:border-b-0 hover:bg-white/[0.02]"
                  >
                    <td className="px-4 py-3">
                      <span className="font-medium">{profile.name}</span>
                    </td>
                    <td className="px-4 py-3 text-[#a1a1a6] text-sm max-w-xs truncate">
                      {profile.description || '—'}
                    </td>
                    <td className="px-4 py-3">
                      <MiniCurve profile={profile} />
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm text-[#a1a1a6]">
                        {profile.keyframes.length} points
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      {groupCount > 0 ? (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-amber-500/15 text-amber-400 border border-amber-500/30 rounded-full text-xs font-medium">
                          {groupCount} group{groupCount !== 1 ? 's' : ''}
                        </span>
                      ) : (
                        <span className="text-[#636366] text-sm">None</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => openEditModal(profile)}
                          className="p-2 hover:bg-white/5 rounded-lg transition-colors text-[#a1a1a6] hover:text-white"
                          title="Edit"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125M18 14v4.75A2.25 2.25 0 0115.75 21H5.25A2.25 2.25 0 013 18.75V8.25A2.25 2.25 0 015.25 6H10" />
                          </svg>
                        </button>
                        {deleteConfirm === profile.id ? (
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => handleDelete(profile.id)}
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
                            onClick={() => setDeleteConfirm(profile.id)}
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

      {/* Create/Edit Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-[#1a1a1f] rounded-xl border border-[#2a2a2f] w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
            <div className="px-6 py-4 border-b border-[#2a2a2f] flex-shrink-0">
              <h2 className="text-lg font-semibold">
                {editingProfile ? 'Edit Profile' : 'Create Profile'}
              </h2>
            </div>

            <div className="p-6 space-y-6 overflow-y-auto flex-1">
              {/* Name */}
              <div>
                <label className="block text-sm font-medium text-[#a1a1a6] mb-1.5">
                  Name <span className="text-red-400">*</span>
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g., Standard Day"
                  className="w-full px-3 py-2 bg-[#0a0a0b] border border-[#2a2a2f] rounded-lg text-white placeholder:text-[#636366] focus:outline-none focus:border-amber-500"
                />
              </div>

              {/* Description */}
              <div>
                <label className="block text-sm font-medium text-[#a1a1a6] mb-1.5">
                  Description
                </label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  placeholder="Optional description..."
                  rows={2}
                  className="w-full px-3 py-2 bg-[#0a0a0b] border border-[#2a2a2f] rounded-lg text-white placeholder:text-[#636366] focus:outline-none focus:border-amber-500 resize-none"
                />
              </div>

              {/* Curve Preview */}
              <CurvePreview keyframes={formData.keyframes} />

              {/* Keyframes */}
              <div>
                <div className="flex items-center justify-between mb-3">
                  <label className="block text-sm font-medium text-[#a1a1a6]">
                    Keyframes <span className="text-red-400">*</span>
                    <span className="font-normal text-[#636366] ml-2">(min. 2)</span>
                  </label>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={sortKeyframesByTime}
                      className="px-3 py-1.5 text-xs bg-[#2a2a2f] hover:bg-[#3a3a3f] text-white rounded-lg transition-colors"
                    >
                      Sort by Time
                    </button>
                    <button
                      type="button"
                      onClick={addKeyframe}
                      className="px-3 py-1.5 text-xs bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors flex items-center gap-1"
                    >
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                      </svg>
                      Add
                    </button>
                  </div>
                </div>

                <div className="space-y-2">
                  {/* Header */}
                  <div className="grid grid-cols-[100px_1fr_1fr_40px] gap-2 px-2 text-xs text-[#636366]">
                    <span>Time</span>
                    <span>Brightness (%)</span>
                    <span>CCT (K)</span>
                    <span></span>
                  </div>

                  {/* Keyframe rows */}
                  {formData.keyframes.map((kf, index) => (
                    <div
                      key={index}
                      className="grid grid-cols-[100px_1fr_1fr_40px] gap-2 items-center bg-[#0a0a0b] border border-[#2a2a2f] rounded-lg p-2"
                    >
                      <input
                        type="time"
                        value={kf.time}
                        onChange={(e) => updateKeyframe(index, 'time', e.target.value)}
                        className="px-2 py-1.5 bg-[#1a1a1f] border border-[#2a2a2f] rounded text-white text-sm focus:outline-none focus:border-amber-500"
                      />
                      <div className="flex items-center gap-2">
                        <input
                          type="range"
                          min="0"
                          max="100"
                          value={kf.brightness}
                          onChange={(e) => updateKeyframe(index, 'brightness', e.target.value)}
                          className="flex-1 accent-amber-500"
                        />
                        <input
                          type="number"
                          min="0"
                          max="100"
                          value={kf.brightness}
                          onChange={(e) => updateKeyframe(index, 'brightness', e.target.value)}
                          className="w-16 px-2 py-1.5 bg-[#1a1a1f] border border-[#2a2a2f] rounded text-white text-sm text-center focus:outline-none focus:border-amber-500"
                        />
                      </div>
                      <div className="flex items-center gap-2">
                        <div
                          className="w-6 h-6 rounded border border-[#2a2a2f]"
                          style={{ backgroundColor: cctToColor(parseInt(kf.cct, 10) || 4000) }}
                        />
                        <input
                          type="number"
                          min="1000"
                          max="10000"
                          step="100"
                          value={kf.cct}
                          onChange={(e) => updateKeyframe(index, 'cct', e.target.value)}
                          className="flex-1 px-2 py-1.5 bg-[#1a1a1f] border border-[#2a2a2f] rounded text-white text-sm focus:outline-none focus:border-amber-500"
                        />
                      </div>
                      <button
                        type="button"
                        onClick={() => removeKeyframe(index)}
                        className="p-1.5 hover:bg-red-500/10 rounded transition-colors text-[#636366] hover:text-red-400"
                        title="Remove keyframe"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="px-6 py-4 border-t border-[#2a2a2f] flex justify-end gap-3 flex-shrink-0">
              <button
                onClick={() => setIsModalOpen(false)}
                className="px-4 py-2 bg-[#2a2a2f] hover:bg-[#3a3a3f] text-white rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={isSaving}
                className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-black font-medium rounded-lg transition-colors disabled:opacity-50"
              >
                {isSaving ? 'Saving...' : editingProfile ? 'Save Changes' : 'Create Profile'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
