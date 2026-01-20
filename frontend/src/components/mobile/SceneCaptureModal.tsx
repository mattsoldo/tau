"use client";

import { useState } from "react";
import { X } from "lucide-react";

interface SceneCaptureModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCapture: (name: string, isToggle: boolean) => void;
  groupName?: string; // If provided, this is a room-specific scene
}

export function SceneCaptureModal({
  isOpen,
  onClose,
  onCapture,
  groupName,
}: SceneCaptureModalProps) {
  const [sceneName, setSceneName] = useState("");
  const [isToggle, setIsToggle] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const trimmedName = sceneName.trim();
    if (!trimmedName) {
      setError("Please enter a scene name");
      return;
    }

    onCapture(trimmedName, isToggle);
    setSceneName("");
    setIsToggle(false);
    setError(null);
    onClose();
  };

  const handleClose = () => {
    setSceneName("");
    setIsToggle(false);
    setError(null);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="relative bg-white dark:bg-[#1a1a1f] rounded-2xl shadow-2xl w-[90%] max-w-sm mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100 dark:border-[#2a2a2f]">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            {groupName ? `Capture ${groupName} Scene` : "Capture Scene"}
          </h2>
          <button
            onClick={handleClose}
            className="w-8 h-8 rounded-full bg-gray-100 dark:bg-[#2a2a2f] flex items-center justify-center hover:bg-gray-200 dark:hover:bg-[#3a3a3f] transition-colors"
          >
            <X className="w-4 h-4 text-gray-600 dark:text-gray-400" />
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          <div>
            <label
              htmlFor="scene-name"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5"
            >
              Scene Name
            </label>
            <input
              id="scene-name"
              type="text"
              value={sceneName}
              onChange={(e) => {
                setSceneName(e.target.value);
                setError(null);
              }}
              placeholder="e.g., Movie Night, Dinner Party"
              className="w-full px-4 py-2.5 rounded-xl border border-gray-200 dark:border-[#3a3a3f] bg-white dark:bg-[#0f0f14] focus:border-amber-400 focus:ring-2 focus:ring-amber-100 dark:focus:ring-amber-500/20 outline-none transition-all text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500"
              autoFocus
            />
            {error && <p className="mt-1.5 text-sm text-red-500">{error}</p>}
          </div>

          <div className="flex items-center gap-3">
            <input
              id="toggle-scene"
              type="checkbox"
              checked={isToggle}
              onChange={(e) => setIsToggle(e.target.checked)}
              className="w-4 h-4 rounded border-gray-300 dark:border-gray-600 text-amber-500 focus:ring-amber-400 bg-white dark:bg-[#2a2a2f]"
            />
            <label
              htmlFor="toggle-scene"
              className="text-sm text-gray-700 dark:text-gray-300 cursor-pointer"
            >
              <span className="font-medium">Toggle scene</span>
              <span className="text-gray-500 dark:text-gray-400 ml-1">
                (tap again to turn off)
              </span>
            </label>
          </div>

          {groupName ? (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              This scene will only affect lights in {groupName}.
            </p>
          ) : (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              This scene will capture all lights at their current levels.
            </p>
          )}

          {/* Buttons */}
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={handleClose}
              className="flex-1 px-4 py-2.5 rounded-xl border border-gray-200 dark:border-[#3a3a3f] text-gray-700 dark:text-gray-300 font-medium hover:bg-gray-50 dark:hover:bg-[#2a2a2f] transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex-1 px-4 py-2.5 rounded-xl bg-gradient-to-r from-amber-500 to-orange-500 text-white font-medium hover:from-amber-600 hover:to-orange-600 transition-colors shadow-sm"
            >
              Capture
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
