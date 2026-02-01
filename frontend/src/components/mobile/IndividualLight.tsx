"use client";

import { useRef } from "react";
import { Lock } from "lucide-react";
import {
  useUnlockGesture,
  PROGRESS_RING_CIRCUMFERENCE_SMALL,
} from "@/hooks/useUnlockGesture";

interface IndividualLightProps {
  name: string;
  isOn: boolean;
  brightness: number; // 0-100
  locked?: boolean;  // Whether the control is locked (passed from parent group)
  onToggle: () => void;
  onBrightnessChange: (value: number) => void;
  onUnlock?: () => void;  // Callback when unlock gesture completes
}

// The leftmost portion of the slider is reserved for "off" (0% brightness)
// This makes it easier to turn off lights by tapping the left side
const OFF_ZONE_PERCENT = 10;

export function IndividualLight({
  name,
  isOn,
  brightness,
  locked = false,
  onBrightnessChange,
  onUnlock,
}: IndividualLightProps) {
  const cardRef = useRef<HTMLDivElement>(null);

  // Use the shared unlock gesture hook
  const {
    unlockProgress,
    isHoldingToUnlock,
    startUnlockHold,
    cancelUnlockHold,
  } = useUnlockGesture({
    isLocked: locked,
    onUnlock,
    // Individual lights don't manage unlock duration - parent handles it
    unlockDurationMinutes: 0,
    lockActive: locked,
  });

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
    if (locked) return;
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
    if (locked) return;
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

    // If locked, start unlock hold gesture
    if (locked) {
      startUnlockHold();
      const handleMouseUp = () => {
        cancelUnlockHold();
        document.removeEventListener('mouseup', handleMouseUp);
      };
      document.addEventListener('mouseup', handleMouseUp);
      return;
    }

    handleSliderInteraction(e);

    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  };

  const handleTouchStart = (e: React.TouchEvent) => {
    if (locked) {
      e.preventDefault();
      startUnlockHold();
      return;
    }
    handleSliderInteraction(e);
  };

  const handleTouchEnd = () => {
    if (isHoldingToUnlock) {
      cancelUnlockHold();
    }
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
      onTouchStart={handleTouchStart}
      onTouchMove={locked ? undefined : handleSliderInteraction}
      onTouchEnd={handleTouchEnd}
      className={`relative overflow-hidden bg-gray-50 dark:bg-[#0f0f14] rounded-lg p-3 ${
        locked ? 'cursor-pointer' : 'cursor-ew-resize'
      }`}
      style={{ touchAction: 'none' }}
    >
      {/* Off zone indicator - subtle left border */}
      {!locked && (
        <div
          className="absolute left-0 top-0 bottom-0 border-r border-dashed border-gray-200 dark:border-gray-700"
          style={{ width: `${OFF_ZONE_PERCENT}%` }}
        />
      )}

      {/* Brightness indicator background - no transition for instant response */}
      {isOn && !locked && (
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

      {/* Locked overlay */}
      {locked && (
        <div className="absolute inset-0 bg-gray-900/40 dark:bg-gray-900/60 flex items-center justify-center">
          {isHoldingToUnlock ? (
            <div className="relative w-8 h-8">
              <svg className="w-8 h-8 -rotate-90" viewBox="0 0 32 32">
                <circle
                  cx="16"
                  cy="16"
                  r="12"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  className="text-gray-600"
                />
                <circle
                  cx="16"
                  cy="16"
                  r="12"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  className="text-amber-500"
                  strokeDasharray={`${unlockProgress * PROGRESS_RING_CIRCUMFERENCE_SMALL} ${PROGRESS_RING_CIRCUMFERENCE_SMALL}`}
                />
              </svg>
              <Lock className="absolute inset-0 m-auto w-3 h-3 text-amber-500" />
            </div>
          ) : (
            <Lock className="w-3 h-3 text-gray-400" />
          )}
        </div>
      )}

      {/* Dimmed brightness indicator when locked */}
      {isOn && locked && (
        <div
          className="absolute inset-0 bg-gradient-to-r from-gray-400/30 via-gray-300/20 to-transparent"
          style={{ width: `${visualPosition}%` }}
        />
      )}

      <div className="relative flex items-center justify-between gap-2">
        <div className="flex-1 min-w-0">
          <h4 className={`font-medium text-xs truncate ${
            locked ? 'text-gray-500 dark:text-gray-400' : 'text-gray-900 dark:text-white'
          }`}>{name}</h4>
        </div>
        <div className={`text-xs font-medium tabular-nums min-w-[3rem] text-right ${
          locked ? 'text-gray-500 dark:text-gray-400' : 'text-gray-700 dark:text-gray-300'
        }`}>
          {isOn ? `${brightness}%` : 'Off'}
        </div>
      </div>
    </div>
  );
}
