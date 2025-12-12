export default function HomePage() {
  return (
    <main className="container mx-auto px-4 py-8">
      <div className="max-w-4xl mx-auto">
        <header className="mb-8">
          <h1 className="text-4xl font-bold text-gray-900 mb-2">
            Tau Lighting Control
          </h1>
          <p className="text-lg text-gray-600">
            Smart circadian lighting control system
          </p>
        </header>

        <div className="grid gap-6">
          <div className="bg-white rounded-lg shadow-md p-6">
            <h2 className="text-2xl font-semibold mb-4">Welcome to Tau</h2>
            <p className="text-gray-700 mb-4">
              This is the web interface for the Tau smart lighting control system.
              The system is currently initializing...
            </p>
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <div className="w-2 h-2 bg-yellow-500 rounded-full animate-pulse"></div>
              <span>Connecting to daemon...</span>
            </div>
          </div>

          <div className="grid md:grid-cols-3 gap-4">
            <div className="bg-white rounded-lg shadow-md p-6">
              <h3 className="text-lg font-semibold mb-2">Rooms</h3>
              <p className="text-gray-600 text-sm">
                Control lighting by room and zone
              </p>
            </div>
            <div className="bg-white rounded-lg shadow-md p-6">
              <h3 className="text-lg font-semibold mb-2">Scenes</h3>
              <p className="text-gray-600 text-sm">
                Activate preset lighting scenes
              </p>
            </div>
            <div className="bg-white rounded-lg shadow-md p-6">
              <h3 className="text-lg font-semibold mb-2">Schedule</h3>
              <p className="text-gray-600 text-sm">
                View and edit circadian schedules
              </p>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
