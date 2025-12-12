import { Home, Settings } from "lucide-react";
import { RoomControl } from "./components/RoomControl";

export default function App() {
  const rooms = [
    { name: "Living Room", brightness: 75, cct: 3000, isOn: true },
    { name: "Bedroom", brightness: 45, cct: 2700, isOn: true },
    { name: "Kitchen", brightness: 100, cct: 4000, isOn: true },
    { name: "Bathroom", brightness: 60, cct: 5000, isOn: false },
    { name: "Office", brightness: 85, cct: 5500, isOn: true },
  ];

  return (
    <div className="min-h-screen bg-gray-50 max-w-md mx-auto">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4 sticky top-0 z-10">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Home className="w-6 h-6 text-gray-700" />
            <h1 className="text-gray-900">Home Lighting</h1>
          </div>
          <button className="p-2 hover:bg-gray-100 rounded-full transition-colors">
            <Settings className="w-5 h-5 text-gray-600" />
          </button>
        </div>
      </div>

      {/* Rooms List */}
      <div className="p-4 space-y-4">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-gray-600">Rooms</h2>
          <span className="text-sm text-gray-500">{rooms.filter(r => r.isOn).length} active</span>
        </div>
        
        {rooms.map((room, index) => (
          <RoomControl
            key={index}
            name={room.name}
            initialBrightness={room.brightness}
            cct={room.cct}
            isOn={room.isOn}
          />
        ))}
      </div>
    </div>
  );
}
