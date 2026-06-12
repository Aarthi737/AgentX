'use client';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { listRuns, cancelRun } from '@/lib/api';
import type { RunListItem } from '@/types';
import { formatDistanceToNow } from 'date-fns';
import { Activity, CheckCircle, Clock, ExternalLink, Loader, Trash2, XCircle, AlertTriangle } from 'lucide-react';
import { clsx } from 'clsx';
import toast from 'react-hot-toast';
import { useState } from 'react';

const STATUS_COLORS: Record<string, string> = {
  PR_CREATED:      'text-green-400 bg-green-900/20 border-green-800',
  FAILED:          'text-red-400 bg-red-900/20 border-red-800',
  HUMAN_REVIEW:    'text-amber-400 bg-amber-900/20 border-amber-800',
  PENDING:         'text-gray-400 bg-gray-800 border-gray-700',
  INGESTING:       'text-blue-400 bg-blue-900/20 border-blue-800',
  REPO_INTELLIGENCE:'text-blue-400 bg-blue-900/20 border-blue-800',
  ANALYZING:       'text-blue-400 bg-blue-900/20 border-blue-800',
  RANKING:         'text-blue-400 bg-blue-900/20 border-blue-800',
  RCA:             'text-purple-400 bg-purple-900/20 border-purple-800',
  FIX_GENERATION:  'text-indigo-400 bg-indigo-900/20 border-indigo-800',
  VALIDATION:      'text-cyan-400 bg-cyan-900/20 border-cyan-800',
  VERIFICATION:    'text-teal-400 bg-teal-900/20 border-teal-800',
};

const PHASE_LABELS: Record<string, string> = {
  PENDING: 'Queued',
  INGESTING: 'Phase 1 · Ingesting',
  REPO_INTELLIGENCE: 'Phase 2 · Repo Analysis',
  ANALYZING: 'Phase 3 · Scanning',
  RANKING: 'Phase 4 · Ranking',
  RCA: 'Phase 5 · Root Cause',
  FIX_GENERATION: 'Phase 6 · Generating Fixes',
  VALIDATION: 'Phase 7 · Validating',
  VERIFICATION: 'Phase 8 · Verifying',
  PR_CREATED: 'Complete · PR Created',
  FAILED: 'Failed',
  HUMAN_REVIEW: 'Human Review Required',
};

function StatusBadge({ status }: { status: string }) {
  const isRunning = !['PR_CREATED', 'FAILED', 'HUMAN_REVIEW', 'PENDING'].includes(status);
  return (
    <span className={clsx(
      'inline-flex items-center gap-1.5 px-2 py-0.5 rounded border text-xs font-medium',
      STATUS_COLORS[status] || STATUS_COLORS.PENDING
    )}>
      {isRunning && <Loader size={10} className="animate-spin" />}
      {status === 'PR_CREATED' && <CheckCircle size={10} />}
      {status === 'FAILED' && <XCircle size={10} />}
      {status === 'HUMAN_REVIEW' && <AlertTriangle size={10} />}
      {PHASE_LABELS[status] || status}
    </span>
  );
}

export default function RunsPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [filter, setFilter] = useState<string>('ALL');

  const { data: runs = [], isLoading } = useQuery<RunListItem[]>({
    queryKey: ['runs', 50],
    queryFn: () => listRuns(50),
    refetchInterval: 4000,
  });

  const filtered = filter === 'ALL' ? runs : runs.filter(r => r.status === filter);

  const handleCancel = async (e: React.MouseEvent, runId: string) => {
    e.stopPropagation();
    try {
      await cancelRun(runId);
      toast.success(`Run ${runId} cancelled`);
      qc.invalidateQueries({ queryKey: ['runs'] });
    } catch {
      toast.error('Failed to cancel run');
    }
  };

  const filterOptions = ['ALL', 'PR_CREATED', 'FAILED', 'HUMAN_REVIEW', 'ANALYZING', 'VALIDATION'];

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Activity size={22} className="text-blue-400" /> Pipeline Runs
          </h1>
          <p className="text-gray-500 text-sm mt-1">{runs.length} total runs</p>
        </div>
      </div>

      {/* Filter tabs */}
      <div className="flex gap-2 flex-wrap">
        {filterOptions.map(opt => (
          <button
            key={opt}
            onClick={() => setFilter(opt)}
            className={clsx(
              'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border',
              filter === opt
                ? 'bg-blue-600 border-blue-500 text-white'
                : 'border-gray-700 text-gray-400 hover:text-white hover:border-gray-600'
            )}
          >
            {opt === 'ALL' ? `All (${runs.length})` : opt}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-48 text-gray-500">
          <Loader size={20} className="animate-spin mr-2" /> Loading runs...
        </div>
      ) : filtered.length === 0 ? (
        <div className="card text-center py-12 text-gray-500">
          No runs found for this filter.
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map(run => (
            <div
              key={run.id}
              onClick={() => router.push(`/runs/${run.id}`)}
              className="card hover:border-gray-600 cursor-pointer transition-colors"
            >
              <div className="flex items-center justify-between gap-4">
                {/* Left: repo info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className="font-mono text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded">
                      {run.id}
                    </span>
                    <span className="font-medium text-white truncate">
                      {run.repo_owner}/{run.repo_name || 'repository'}
                    </span>
                    <StatusBadge status={run.status} />
                  </div>
                  <div className="text-xs text-gray-600 mt-1 truncate">{run.repo_url}</div>
                </div>

                {/* Stats */}
                <div className="flex items-center gap-6 text-sm flex-shrink-0">
                  <div className="text-center">
                    <div className="font-bold text-white">{run.total_issues}</div>
                    <div className="text-xs text-gray-600">Issues</div>
                  </div>
                  <div className="text-center">
                    <div className="font-bold text-white">{run.total_fixes}</div>
                    <div className="text-xs text-gray-600">Fixes</div>
                  </div>
                  <div className="text-center">
                    <div className="text-xs text-gray-500 flex items-center gap-1">
                      <Clock size={10} />
                      {formatDistanceToNow(new Date(run.started_at), { addSuffix: true })}
                    </div>
                    {run.completed_at && (
                      <div className="text-xs text-gray-600">
                        {Math.round(
                          (new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()) / 1000
                        )}s
                      </div>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-2">
                    {run.pr_url && (
                      <a
                        href={run.pr_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={e => e.stopPropagation()}
                        className="text-blue-400 hover:text-blue-300 flex items-center gap-1 text-xs"
                      >
                        <ExternalLink size={12} /> PR #{
                          run.pr_url.split('/').pop()
                        }
                      </a>
                    )}
                    {['PENDING', 'INGESTING', 'ANALYZING'].includes(run.status) && (
                      <button
                        onClick={e => handleCancel(e, run.id)}
                        className="text-gray-600 hover:text-red-400 transition-colors"
                        title="Cancel run"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
