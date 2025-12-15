import Link from 'next/link';

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
          {/* Dashboard CTA */}
          <Link href="/dashboard" className="block bg-gradient-to-br from-amber-500 to-amber-600 rounded-lg shadow-lg p-6 text-white hover:from-amber-600 hover:to-amber-700 transition-all hover:shadow-xl hover:-translate-y-0.5">
            <h2 className="text-2xl font-semibold mb-2">System Dashboard</h2>
            <p className="text-amber-100">
              View real-time system status, hardware metrics, and fixture states
            </p>
            <div className="mt-4 flex items-center gap-2 text-sm font-medium">
              <span>Open Dashboard</span>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </div>
          </Link>

          {/* LabJack Monitor */}
          <a href="http://localhost:8000/labjack_monitor.html" target="_blank" rel="noopener noreferrer" className="block bg-gradient-to-br from-slate-700 to-slate-800 rounded-lg shadow-lg p-6 text-white hover:from-slate-600 hover:to-slate-700 transition-all hover:shadow-xl hover:-translate-y-0.5">
            <h2 className="text-2xl font-semibold mb-2">LabJack Monitor</h2>
            <p className="text-slate-300">
              Monitor digital I/O channels and test switch behavior with light simulation
            </p>
            <div className="mt-4 flex items-center gap-2 text-sm font-medium">
              <span>Open Monitor</span>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </div>
          </a>

          <div className="bg-white rounded-lg shadow-md p-6">
            <h2 className="text-2xl font-semibold mb-4">Welcome to Tau</h2>
            <p className="text-gray-700 mb-4">
              This is the web interface for the Tau smart lighting control system.
            </p>
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
