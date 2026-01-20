"use client";

import { useRef, useState } from "react";
import { MoreHorizontal, Plus } from "lucide-react";
import { IndividualLight } from "@/components/mobile/IndividualLight";
import { CompactScene } from "@/components/mobile/CompactScene";

interface FixtureData {
  id: number;
  name: string;
  isOn: boolean;
  brightness: number; // 0-100
}

interface SceneData {
  id: number;
  name: string;
  icon?: "sparkles" | "moon" | "sun" | "coffee" | "sunset" | "lightbulb";
}

interface LightGroupProps {
  name: string;
  description?: string;
  isOn: boolean;
  brightness: number; // 0-100
  fixtures: FixtureData[];
  scenes?: SceneData[];
  activeSceneId?: number | null;
  onToggle: () => void;
  onBrightnessChange: (value: number) => void;
  onFixtureToggle: (fixtureId: number) => void;
  onFixtureBrightnessChange: (fixtureId: number, brightness: number) => void;
  onSceneActivate?: (sceneId: number) => void;
  onCaptureScene?: () => void;
}

// The leftmost portion of the slider is reserved for "off" (0% brightness)
// This makes it easier to turn off lights by tapping the left side
const OFF_ZONE_PERCENT = 10;

export function LightGroup({
  name,
  description,
  isOn,
  brightness,
  fixtures,
  scenes = [],
  activeSceneId,
  onToggle,
  onBrightnessChange,
  onFixtureToggle,
  onFixtureBrightnessChange,
  onSceneActivate,
  onCaptureScene,
}: LightGroupProps) {
  const sliderRef = useRef<HTMLDivElement>(null);
  const [isExpanded, setIsExpanded] = useState(false);

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

  const handleSliderInteraction = (e: React.MouseEvent | React.TouchEvent, isStart: boolean = false) => {
    if (isExpanded) return;
    e.preventDefault();

    const slider = sliderRef.current;
    if (!slider) return;

    const rect = slider.getBoundingClientRect();
    const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX;
    const x = clientX - rect.left;
    const positionPercent = Math.max(0, Math.min(100, (x / rect.width) * 100));
    const newBrightness = positionToBrightness(positionPercent);

    onBrightnessChange(newBrightness);
  };

  const handleMouseMove = (e: MouseEvent) => {
    if (isExpanded) return;
    const slider = sliderRef.current;
    if (!slider) return;

    const rect = slider.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const positionPercent = Math.max(0, Math.min(100, (x / rect.width) * 100));
    const newBrightness = positionToBrightness(positionPercent);

    onBrightnessChange(newBrightness);
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (isExpanded) return;
    e.preventDefault();
    handleSliderInteraction(e, true);

    const handleMouseUp = () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  };

  // Calculate gradient colors based on brightness (dim to warm)
  const getGradientColors = (brightness: number) => {
    // At low brightness (0-40): warm amber/orange
    // At medium brightness (40-70): neutral amber
    // At high brightness (70-100): cool white/blue-tinted
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

  // Calculate the visual position for the brightness indicator
  const visualPosition = brightnessToPosition(brightness);

  return (
    <div className="bg-white dark:bg-[#1a1a1f] rounded-xl shadow-sm border border-gray-100 dark:border-[#2a2a2f]">
      <div className="flex">
        {/* Slider area - takes up most of the width */}
        <div
          ref={sliderRef}
          onMouseDown={handleMouseDown}
          onTouchStart={isExpanded ? undefined : (e) => handleSliderInteraction(e, true)}
          onTouchMove={isExpanded ? undefined : handleSliderInteraction}
          className={`relative overflow-hidden p-4 flex-1 min-w-0 ${
            !isExpanded ? 'cursor-ew-resize' : 'cursor-default'
          }`}
          style={{ touchAction: !isExpanded ? 'none' : 'auto' }}
        >
          {/* Off zone indicator - subtle left border when light is on */}
          {!isExpanded && (
            <div
              className="absolute left-0 top-0 bottom-0 border-r border-dashed border-gray-200 dark:border-gray-700"
              style={{ width: `${OFF_ZONE_PERCENT}%` }}
            />
          )}

          {/* Brightness indicator background - no transition for instant response */}
          {isOn && !isExpanded && (
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

          <div className="relative flex items-center gap-3">
            <div className="flex-1 min-w-0 text-left">
              <h3 className="font-semibold text-gray-900 dark:text-white text-sm truncate">{name}</h3>
              {description && <p className="text-xs text-gray-500 dark:text-gray-400">{description}</p>}
            </div>
            {!isExpanded && (
              <div className="text-sm font-medium text-gray-900 dark:text-white tabular-nums min-w-[3rem] text-right">
                {isOn ? `${brightness}%` : 'Off'}
              </div>
            )}
          </div>
        </div>

        {/* Expand button area - dedicated touch target */}
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className={`flex items-center justify-center w-12 border-l border-gray-100 dark:border-[#2a2a2f] hover:bg-gray-50 dark:hover:bg-[#2a2a2f] active:bg-gray-100 dark:active:bg-[#3a3a3f] transition-colors ${
            isExpanded ? 'bg-gray-50 dark:bg-[#2a2a2f]' : ''
          }`}
        >
          <MoreHorizontal
            className={`w-5 h-5 text-gray-400 dark:text-gray-500 transition-transform ${
              isExpanded ? 'rotate-90' : ''
            }`}
          />
        </button>
      </div>

      {/* Expanded content */}
      {isExpanded && (
        <div className="px-4 pb-4 space-y-3">
          {/* Scenes row with capture button */}
          {(scenes.length > 0 || onCaptureScene) && (
            <div className="flex gap-2 overflow-x-auto pb-1 items-center">
              {scenes.map((scene) => (
                <CompactScene
                  key={scene.id}
                  name={scene.name}
                  icon={scene.icon}
                  isActive={activeSceneId === scene.id}
                  onActivate={() => onSceneActivate?.(scene.id)}
                />
              ))}
              {/* Capture scene button */}
              {onCaptureScene && (
                <button
                  onClick={onCaptureScene}
                  className="flex-shrink-0 w-8 h-8 rounded-lg border-2 border-dashed border-gray-300 dark:border-gray-600 text-gray-400 dark:text-gray-500 flex items-center justify-center hover:border-amber-400 hover:text-amber-500 transition-colors"
                  title="Capture room scene"
                >
                  <Plus className="w-4 h-4" />
                </button>
              )}
            </div>
          )}

          {/* Individual fixtures */}
          <div className="space-y-2">
            {fixtures.map((fixture) => (
              <IndividualLight
                key={fixture.id}
                name={fixture.name}
                isOn={fixture.isOn}
                brightness={fixture.brightness}
                onToggle={() => onFixtureToggle(fixture.id)}
                onBrightnessChange={(value) =>
                  onFixtureBrightnessChange(fixture.id, value)
                }
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
