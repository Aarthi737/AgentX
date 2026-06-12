'use client';
import { useQuery } from '@tanstack/react-query';
import { getHealth } from '@/lib/api';
import { CheckCircle, Settings, XCircle } from 'lucide-react';
import { clsx } from 'clsx';

export default function SettingsPage() {
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: 30000,
  });

  const checks = health
    ? [
        { label: 'API Server', status: health.status === 'healthy', detail: health.status },
        { label: 'Database (Supabase)', status: health.database === 'ok', detail: health.database },
        { label: 'Groq API', status: health.groq === 'ok', detail: health.groq },
        { label: 'Environment', status: true, detail: health.environment },
        { label: 'Version', status: true, detail: health.version },
      ]
    : [];

  return (
    <div className="max-w-2xl mx-auto space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Settings size={22} className="text-gray-400" /> Settings & Health
        </h1>
        <p className="text-gray-500 text-sm mt-1">System status and configuration overview.</p>
      </div>

      {/* Health checks */}
      <div className="card space-y-3">
        <h2 className="font-semibold text-white">System Health</h2>
        {checks.map(({ label, status, detail }) => (
          <div key={label} className="flex items-center justify-between py-2 border-b border-gray-800 last:border-0">
            <div className="flex items-center gap-2">
              {status
                ? <CheckCircle size={14} className="text-green-400" />
                : <XCircle size={14} className="text-red-400" />}
              <span className="text-sm text-gray-300">{label}</span>
            </div>
            <span className={clsx(
              'text-xs font-mono px-2 py-0.5 rounded',
              status ? 'text-green-400 bg-green-900/20' : 'text-red-400 bg-red-900/20'
            )}>
              {detail}
            </span>
          </div>
        ))}
        {!health && (
          <p className="text-gray-600 text-sm">Connecting to API...</p>
        )}
      </div>

      {/* Environment vars reference */}
      <div className="card">
        <h2 className="font-semibold text-white mb-3">Configuration Reference</h2>
        <p className="text-xs text-gray-500 mb-4">
          Copy <code className="text-blue-400">.env.example</code> to <code className="text-blue-400">.env</code> and fill in all values.
        </p>
        <div className="space-y-2 font-mono text-xs">
          {[
            ['GROQ_API_KEY', 'Groq API key (free tier: 14,400 req/day)'],
            ['SUPABASE_URL', 'Your Supabase project URL'],
            ['SUPABASE_SERVICE_ROLE_KEY', 'Supabase service role key'],
            ['DATABASE_URL', 'postgresql://... connection string'],
            ['GITHUB_DEFAULT_TOKEN', 'Default GitHub PAT (optional)'],
            ['APP_SECRET_KEY', '64-char random secret for the API'],
          ].map(([key, desc]) => (
            <div key={key} className="flex gap-3">
              <span className="text-blue-400 w-52 flex-shrink-0">{key}</span>
              <span className="text-gray-500">{desc}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Stack info */}
      <div className="card">
        <h2 className="font-semibold text-white mb-3">Technology Stack</h2>
        <div className="grid grid-cols-2 gap-2 text-xs text-gray-400">
          {[
            ['LLM Engine', 'Groq Llama 3.3 70B · Free tier'],
            ['Orchestration', 'LangGraph + LangChain'],
            ['Backend', 'FastAPI + Python 3.11'],
            ['Frontend', 'Next.js 14 + Tailwind CSS'],
            ['Database', 'Supabase PostgreSQL · Free tier'],
            ['Verification', 'Docker · pytest/Jest/JUnit'],
            ['Analysis', 'Bandit + Semgrep + Pylint'],
            ['Total Cost', 'Rs. 0 / month'],
          ].map(([k, v]) => (
            <div key={k} className="bg-gray-800 rounded-lg p-2">
              <div className="text-gray-600 text-xs">{k}</div>
              <div className="text-white font-medium text-xs mt-0.5">{v}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
