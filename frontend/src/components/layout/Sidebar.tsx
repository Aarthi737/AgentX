'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Activity, Bot, GitPullRequest, Home, Settings, TrendingUp, Zap } from 'lucide-react';
import { clsx } from 'clsx';

const NAV = [
  { href: '/', label: 'Dashboard', icon: Home },
  { href: '/runs', label: 'Runs', icon: Activity },
  { href: '/afe', label: 'Learning', icon: TrendingUp },
  { href: '/settings', label: 'Settings', icon: Settings },
];

export function Sidebar() {
  const path = usePathname();
  return (
    <aside className="w-56 bg-gray-900 border-r border-gray-800 flex flex-col">
      {/* Logo */}
      <div className="p-5 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <Zap className="text-blue-500" size={22} />
          <div>
            <div className="font-bold text-white text-sm">AgentX</div>
            <div className="text-gray-500 text-xs">TriggeredAGIs</div>
          </div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 p-3 space-y-1">
        {NAV.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={clsx(
              'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors',
              path === href
                ? 'bg-blue-600 text-white'
                : 'text-gray-400 hover:text-white hover:bg-gray-800'
            )}
          >
            <Icon size={16} />
            {label}
          </Link>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-gray-800 text-xs text-gray-600">
        <div>Agentic AI Hackathon 2026</div>
        <div>ASTRA Lab, IIT Madras</div>
      </div>
    </aside>
  );
}
