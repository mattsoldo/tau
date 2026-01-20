'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';

interface SystemStatus {
  status: string;
  hardware?: {
    labjack?: { connected: boolean };
    ola?: { connected: boolean };
    overall_healthy: boolean;
  };
  event_loop?: { running: boolean };
}

export default function Header() {
  const pathname = usePathname();
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [currentTime, setCurrentTime] = useState('');

  useEffect(() => {
    const updateTime = () => {
      setCurrentTime(new Date().toLocaleTimeString('en-US', { hour12: false }));
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch('/status');
        if (res.ok) setStatus(await res.json());
      } catch {
        // Ignore errors
      }
    };
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const isActive = (path: string) => {
    if (path === '/') return pathname === '/';
    return pathname.startsWith(path);
  };

  const isHealthy = status?.hardware?.overall_healthy && status?.event_loop?.running;

  // Hide header on home page (mobile UI has its own header)
  if (pathname === '/') {
    return null;
  }

  const tabs = [
    {
      name: 'Dashboard',
      path: '/dashboard',
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
        </svg>
      )
    },
    {
      name: 'LabJack',
      path: '/labjack',
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
          <rect x="4" y="4" width="16" height="16" rx="2" strokeLinecap="round" strokeLinejoin="round"/>
          <circle cx="9" cy="9" r="1" fill="currentColor"/>
          <circle cx="15" cy="9" r="1" fill="currentColor"/>
          <circle cx="9" cy="15" r="1" fill="currentColor"/>
          <circle cx="15" cy="15" r="1" fill="currentColor"/>
        </svg>
      )
    },
    {
      name: 'Test Controls',
      path: '/test',
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M6 13.5V3.75m0 9.75a1.5 1.5 0 010 3m0-3a1.5 1.5 0 000 3m0 3.75V16.5m12-3V3.75m0 9.75a1.5 1.5 0 010 3m0-3a1.5 1.5 0 000 3m0 3.75V16.5m-6-9V3.75m0 3.75a1.5 1.5 0 010 3m0-3a1.5 1.5 0 000 3m0 9.75V10.5" />
        </svg>
      )
    },
    {
      name: 'Configuration',
      path: '/config',
      icon: (
        <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth="1.5" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.324.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 011.37.49l1.296 2.247a1.125 1.125 0 01-.26 1.431l-1.003.827c-.293.24-.438.613-.431.992a6.759 6.759 0 010 .255c-.007.378.138.75.43.99l1.005.828c.424.35.534.954.26 1.43l-1.298 2.247a1.125 1.125 0 01-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.57 6.57 0 01-.22.128c-.331.183-.581.495-.644.869l-.213 1.28c-.09.543-.56.941-1.11.941h-2.594c-.55 0-1.02-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 01-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 01-1.369-.49l-1.297-2.247a1.125 1.125 0 01.26-1.431l1.004-.827c.292-.24.437-.613.43-.992a6.932 6.932 0 010-.255c.007-.378-.138-.75-.43-.99l-1.004-.828a1.125 1.125 0 01-.26-1.43l1.297-2.247a1.125 1.125 0 011.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.087.22-.128.332-.183.582-.495.644-.869l.214-1.281z" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      )
    },
  ];

  return (
    <header className="sticky top-0 z-50 bg-[#0a0a0b]/95 backdrop-blur-xl border-b border-[#1f1f24]">
      <div className="flex items-center justify-between px-6 h-[72px]">
        {/* Logo and Title */}
        <Link href="/" className="flex items-center gap-4 hover:opacity-90 transition-opacity group">
          <div className="relative">
            <div className="w-10 h-10 bg-gradient-to-br from-amber-400 via-amber-500 to-amber-700 rounded-xl flex items-center justify-center shadow-lg shadow-amber-500/20 group-hover:shadow-amber-500/30 transition-shadow">
              <svg className="w-6 h-6 fill-[#0a0a0b]" viewBox="0 0 24 24">
                <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
              </svg>
            </div>
            <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-[#0a0a0b] rounded-full flex items-center justify-center">
              <div className={`w-2 h-2 rounded-full ${isHealthy ? 'bg-green-500' : 'bg-red-500'}`} />
            </div>
          </div>
          <div>
            <h1 className="text-xl font-semibold tracking-tight">
              Tau <span className="text-[#8e8e93]">Lighting</span>
            </h1>
          </div>
        </Link>

        {/* Navigation Tabs */}
        <nav className="flex items-center">
          <div className="flex items-center bg-[#161619] rounded-xl p-1.5 border border-[#2a2a2f]">
            {tabs.map((tab) => {
              const active = isActive(tab.path);
              return (
                <Link
                  key={tab.path}
                  href={tab.path}
                  className={`
                    relative px-4 py-2.5 rounded-lg font-medium text-sm transition-all duration-200
                    flex items-center gap-2.5
                    ${active
                      ? 'bg-gradient-to-b from-amber-500/20 to-amber-600/10 text-amber-400 shadow-sm'
                      : 'text-[#8e8e93] hover:text-white hover:bg-white/5'
                    }
                  `}
                >
                  {active && (
                    <div className="absolute inset-x-0 -top-1.5 h-0.5 bg-gradient-to-r from-transparent via-amber-500 to-transparent rounded-full" />
                  )}
                  {tab.icon}
                  <span>{tab.name}</span>
                </Link>
              );
            })}
          </div>
        </nav>

        {/* Status and Time */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2.5 px-4 py-2 bg-[#161619] border border-[#2a2a2f] rounded-xl">
            <div className={`w-2 h-2 rounded-full ${isHealthy ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.5)]' : 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]'}`} />
            <span className="text-xs font-medium text-[#a1a1a6]">
              {isHealthy ? 'All Systems Operational' : 'Issues Detected'}
            </span>
          </div>
          <div className="font-mono text-sm text-[#636366] tabular-nums">
            {currentTime}
          </div>
        </div>
      </div>
    </header>
  );
}
