'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function Header() {
  const pathname = usePathname();

  const isActive = (path: string) => {
    if (path === '/') return pathname === '/';
    return pathname.startsWith(path);
  };

  const tabs = [
    { name: 'Dashboard', path: '/dashboard', icon: '📊' },
    { name: 'Test Controls', path: '/test', icon: '🎚️' },
    { name: 'Configuration', path: '/config', icon: '⚙️' },
  ];

  return (
    <header className="sticky top-0 z-50 bg-[#111113] border-b border-[#1f1f24]">
      <div className="flex items-center justify-between px-6 h-16">
        {/* Logo and Title */}
        <Link href="/" className="flex items-center gap-3 hover:opacity-80 transition-opacity">
          <div className="w-9 h-9 bg-gradient-to-br from-amber-500 to-amber-700 rounded-lg flex items-center justify-center">
            <svg className="w-5 h-5 fill-[#0a0a0b]" viewBox="0 0 24 24">
              <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
            </svg>
          </div>
          <div>
            <h1 className="text-lg font-semibold">Tau Lighting</h1>
            <p className="text-xs text-[#636366]">Control System</p>
          </div>
        </Link>

        {/* Navigation Tabs */}
        <nav className="flex items-center gap-2">
          {tabs.map((tab) => {
            const active = isActive(tab.path);
            return (
              <Link
                key={tab.path}
                href={tab.path}
                className={`
                  px-4 py-2 rounded-lg font-medium text-sm transition-all
                  flex items-center gap-2
                  ${active
                    ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                    : 'text-[#a1a1a6] hover:text-white hover:bg-white/5'
                  }
                `}
              >
                <span>{tab.icon}</span>
                <span>{tab.name}</span>
              </Link>
            );
          })}
        </nav>

        {/* Status Indicator */}
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
          <span className="text-xs text-[#636366]">System Active</span>
        </div>
      </div>
    </header>
  );
}
