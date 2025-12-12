import { Lightbulb } from "lucide-react";
import { useState } from "react";

interface RoomControlProps {
  name: string;
  initialBrightness: number;
  cct: number;
  isOn: boolean;
}

export function RoomControl({ name, initialBrightness, cct, isOn: initialIsOn }: RoomControlProps) {
  const [brightness, setBrightness] = useState(initialBrightness);
  const [isOn, setIsOn] = useState(initialIsOn);

  return (
    <div className="border border-gray-300 rounded-lg p-4 bg-white">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-full ${isOn ? 'bg-yellow-100' : 'bg-gray-100'}`}>
            <Lightbulb className={`w-5 h-5 ${isOn ? 'text-yellow-600' : 'text-gray-400'}`} />
          </div>
          <div className="flex items-center gap-4">
            <h3 className="text-gray-900">{name}</h3>
            <div className="flex items-center gap-3 text-sm text-gray-500">
              <span>{brightness}%</span>
              <span>{cct}K</span>
            </div>
          </div>
        </div>
        <button
          onClick={() => setIsOn(!isOn)}
          className={`w-12 h-7 rounded-full transition-colors relative ${
            isOn ? 'bg-blue-500' : 'bg-gray-300'
          }`}
        >
          <div
            className={`absolute top-1 w-5 h-5 bg-white rounded-full transition-transform ${
              isOn ? 'translate-x-6' : 'translate-x-1'
            }`}
          />
        </button>
      </div>

      <input
        type="range"
        min="0"
        max="100"
        value={brightness}
        onChange={(e) => setBrightness(Number(e.target.value))}
        disabled={!isOn}
        className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed accent-blue-500"
      />
    </div>
  );
}