"use client";

import { Switch } from "@/components/ui/switch";
import { useRef } from "react";

interface IndividualLightProps {
  name: string;
  isOn: boolean;
  brightness: number; // 0-100
  onToggle: () => void;
  onBrightnessChange: (value: number) => void;
}

export function IndividualLight({
  name,
  isOn,
  brightness,
  onToggle,
  onBrightnessChange,
}: IndividualLightProps) {
  const cardRef = useRef<HTMLDivElement>(null);

  const handleSliderInteraction = (e: React.MouseEvent | React.TouchEvent) => {
    if (!isOn) return;

    e.preventDefault();
    const card = cardRef.current;
    if (!card) return;

    const rect = card.getBoundingClientRect();
    const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX;
    const x = clientX - rect.left;
    const percentage = Math.max(0, Math.min(100, (x / rect.width) * 100));

    onBrightnessChange(Math.round(percentage));
  };

  const handleMouseMove = (e: MouseEvent) => {
    if (!isOn) return;
    const card = cardRef.current;
    if (!card) return;

    const rect = card.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const percentage = Math.max(0, Math.min(100, (x / rect.width) * 100));

    onBrightnessChange(Math.round(percentage));
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (!isOn) return;
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
  const getGradientColors = (brightness: number) => {
    if (brightness < 40) {
      return 'from-amber-200/70 via-amber-100/50';
    } else if (brightness < 70) {
      return 'from-amber-100/60 via-amber-50/40';
    } else {
      return 'from-sky-50/60 via-slate-50/40';
    }
  };

  const getDividerColor = (brightness: number) => {
    if (brightness < 40) {
      return 'bg-amber-500/50';
    } else if (brightness < 70) {
      return 'bg-amber-400/50';
    } else {
      return 'bg-sky-400/50';
    }
  };

  return (
    <div
      ref={cardRef}
      onMouseDown={handleMouseDown}
      onTouchStart={handleSliderInteraction}
      onTouchMove={handleSliderInteraction}
      className={`relative overflow-hidden bg-gray-50 rounded-lg p-3 transition-all ${
        isOn ? 'cursor-ew-resize' : 'cursor-default'
      }`}
      style={{ touchAction: isOn ? 'none' : 'auto' }}
    >
      {/* Brightness indicator background - no transition for instant response */}
      {isOn && (
        <>
          <div
            className={`absolute inset-0 bg-gradient-to-r ${getGradientColors(brightness)}`}
            style={{ width: `${brightness}%` }}
          />
          {/* Slider divider line */}
          <div
            className={`absolute top-0 bottom-0 w-0.5 ${getDividerColor(brightness)}`}
            style={{ left: `${brightness}%` }}
          />
        </>
      )}

      <div className="relative flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 flex-1 pointer-events-none">
          <div className="flex-1 min-w-0">
            <h4 className="font-medium text-gray-900 text-xs truncate">{name}</h4>
          </div>
          {isOn && (
            <div className="text-xs font-medium text-gray-700 tabular-nums">
              {brightness}%
            </div>
          )}
        </div>
        <div className="pointer-events-auto" onClick={(e) => e.stopPropagation()}>
          <Switch checked={isOn} onCheckedChange={onToggle} />
        </div>
      </div>
    </div>
  );
}
