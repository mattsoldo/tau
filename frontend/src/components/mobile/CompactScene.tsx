"use client";

import { Sparkles, Moon, Sun, Coffee, Sunset, Lightbulb } from "lucide-react";

type IconType = "sparkles" | "moon" | "sun" | "coffee" | "sunset" | "lightbulb";

interface CompactSceneProps {
  name: string;
  icon?: IconType;
  isActive: boolean;
  onActivate: () => void;
}

const iconMap = {
  sparkles: Sparkles,
  moon: Moon,
  sun: Sun,
  coffee: Coffee,
  sunset: Sunset,
  lightbulb: Lightbulb,
};

export function CompactScene({ name, icon = "lightbulb", isActive, onActivate }: CompactSceneProps) {
  const Icon = iconMap[icon] || Lightbulb;

  return (
    <button
      onClick={onActivate}
      className={`flex items-center gap-2 px-3 py-2 rounded-lg transition-all active:scale-95 text-xs font-medium ${
        isActive
          ? "bg-amber-500 text-white"
          : "bg-gray-100 text-gray-700 hover:bg-gray-200"
      }`}
    >
      <Icon className="w-3.5 h-3.5" />
      <span>{name}</span>
    </button>
  );
}
