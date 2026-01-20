"use client";

import { useRef } from "react";

interface IndividualLightProps {
  name: string;
  isOn: boolean;
  brightness: number; // 0-100
  onToggle: () => void;
  onBrightnessChange: (value: number) => void;
}

// The leftmost portion of the slider is reserved for "off" (0% brightness)
// This makes it easier to turn off lights by tapping the left side
const OFF_ZONE_PERCENT = 10;

export function IndividualLight({
  name,
  isOn,
  brightness,
  onBrightnessChange,
}: IndividualLightProps) {
  const cardRef = useRef<HTMLDivElement>(null);

  // Convert slider position (0-100% of slider width) to brightness (0-100)
  // The first OFF_ZONE_PERCENT% of the slider maps to 0 brightness
  // The remaining area maps to 1-100% brightness
  const positionToBrightness = (positionPercent: number): number => {
    if (positionPercent <= OFF_ZONE_PERCENT) {
      return 0;
    }
    // Map (OFF_ZONE_PERCENT, 100] to (0, 100]
    const adjustedPercent = ((positionPercent - OFF_ZONE_PERCENT) / (100 - OFF_ZONE_PERCENT)) * 100;
    return Math.max(1, Math.min(100, Math.round(adjustedPercent)));
  };

  // Convert brightness (0-100) to slider position (0-100% of slider width)
  const brightnessToPosition = (brightnessValue: number): number => {
    if (brightnessValue === 0) {
      return 0;
    }
    // Map (0, 100] to (OFF_ZONE_PERCENT, 100]
    return OFF_ZONE_PERCENT + ((brightnessValue / 100) * (100 - OFF_ZONE_PERCENT));
  };

  const handleSliderInteraction = (e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault();
    const card = cardRef.current;
    if (!card) return;

    const rect = card.getBoundingClientRect();
    const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX;
    const x = clientX - rect.left;
    const positionPercent = Math.max(0, Math.min(100, (x / rect.width) * 100));
    const newBrightness = positionToBrightness(positionPercent);

    onBrightnessChange(newBrightness);
  };

  const handleMouseMove = (e: MouseEvent) => {
    const card = cardRef.current;
    if (!card) return;

    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const positionPercent = Math.max(0, Math.min(100, (x / rect.width) * 100));
    const newBrightness = positionToBrightness(positionPercent);

    onBrightnessChange(newBrightness);
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    e.preventDefault();
    handleSliderInteraction(e);

    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  };

  // Calculate gradient colors based on brightness (dim to warm)
  const getGradientColors = (brightnessVal: number) => {
    if (brightnessVal < 40) {
      return 'from-amber-200/70 via-amber-100/50';
    } else if (brightnessVal < 70) {
      return 'from-amber-100/60 via-amber-50/40';
    } else {
      return 'from-sky-50/60 via-slate-50/40';
    }
  };

  const getDividerColor = (brightnessVal: number) => {
    if (brightnessVal < 40) {
      return 'bg-amber-500/50';
    } else if (brightnessVal < 70) {
      return 'bg-amber-400/50';
    } else {
      return 'bg-sky-400/50';
    }
  };

  // Calculate the visual position for the brightness indicator
  const visualPosition = brightnessToPosition(brightness);

  return (
    <div
      ref={cardRef}
      onMouseDown={handleMouseDown}
      onTouchStart={handleSliderInteraction}
      onTouchMove={handleSliderInteraction}
      className="relative overflow-hidden bg-gray-50 dark:bg-[#0f0f14] rounded-lg p-3 cursor-ew-resize"
      style={{ touchAction: 'none' }}
    >
      {/* Off zone indicator - subtle left border */}
      <div
        className="absolute left-0 top-0 bottom-0 border-r border-dashed border-gray-200 dark:border-gray-700"
        style={{ width: `${OFF_ZONE_PERCENT}%` }}
      />

      {/* Brightness indicator background - no transition for instant response */}
      {isOn && (
        <>
          <div
            className={`absolute inset-0 bg-gradient-to-r ${getGradientColors(brightness)} to-transparent`}
            style={{ width: `${visualPosition}%` }}
          />
          {/* Slider divider line */}
          <div
            className={`absolute top-0 bottom-0 w-0.5 ${getDividerColor(brightness)}`}
            style={{ left: `${visualPosition}%` }}
          />
        </>
      )}

      <div className="relative flex items-center justify-between gap-2">
        <div className="flex-1 min-w-0">
          <h4 className="font-medium text-gray-900 dark:text-white text-xs truncate">{name}</h4>
        </div>
        <div className="text-xs font-medium text-gray-700 dark:text-gray-300 tabular-nums min-w-[3rem] text-right">
          {isOn ? `${brightness}%` : 'Off'}
        </div>
      </div>
    </div>
  );
}
