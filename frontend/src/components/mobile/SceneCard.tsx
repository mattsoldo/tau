"use client";

import { Sparkles, Moon, Sun, Coffee, Sunset, Lightbulb } from "lucide-react";

type IconType = "sparkles" | "moon" | "sun" | "coffee" | "sunset" | "lightbulb";

interface SceneCardProps {
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

export function SceneCard({ name, icon = "lightbulb", isActive, onActivate }: SceneCardProps) {
  const Icon = iconMap[icon] || Lightbulb;

  return (
    <button
      onClick={onActivate}
      className={`flex flex-col items-center justify-center p-4 rounded-2xl transition-all active:scale-95 ${
        isActive
          ? "bg-gradient-to-br from-amber-500 to-orange-600 text-white shadow-lg"
          : "bg-white dark:bg-[#1a1a1f] text-gray-700 dark:text-gray-300 shadow-sm border border-gray-100 dark:border-[#2a2a2f] hover:shadow-md"
      }`}
    >
      <div
        className={`w-12 h-12 rounded-full flex items-center justify-center mb-2 ${
          isActive ? "bg-white/20" : "bg-gray-100 dark:bg-[#2a2a2f]"
        }`}
      >
        <Icon className={`w-6 h-6 ${isActive ? "text-white" : "text-gray-600 dark:text-gray-400"}`} />
      </div>
      <span className="text-sm font-medium">{name}</span>
    </button>
  );
}
