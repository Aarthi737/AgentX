'use client';
import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import toast from 'react-hot-toast';
import { GitBranch, Play, ExternalLink, Clock, CheckCircle, XCircle, AlertTriangle } from 'lucide-react';
import { startRun, listRuns } from '../lib/api';
import { useRunStore } from '../store/runStore';
import type { RunListItem } from '@/types';
import { formatDistanceToNow } from 'date-fns';
import { PipelineProgress } from '@/components/agents/PipelineProgress';

const STATUS_ICON: Record<string, React.ReactNode> = {
  PR_CREATED: <CheckCircle size={14} className="text-green-400" />,
  FAILED: <XCircle size={14} className="text-red-400" />,
  HUMAN_REVIEW: <AlertTriangle size={14} className="text-amber-400" />,
};

export default function DashboardPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const { setActiveRunId, isSubmitting, setIsSubmitting } = useRunStore();

  const [repoUrl, setRepoUrl] = useState('');
  const [githubToken, setGithubToken] = useState('');
  const [branch, setBranch] = useState('main');
  const [activeRunId, setLocalRunId] = useState<string | null>(null);

  const { data: runs = [] } = useQuery<RunListItem[]>({
    queryKey: ['runs'],
    queryFn: () => listRuns(10),
    refetchInterval: 5000,
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!repoUrl.trim()) return;

    setIsSubmitting(true);
    try {
      const res = await startRun({
        repo_url: repoUrl.trim(),
        github_token: githubToken || undefined,
        branch: branch || 'main',
      });
      setActiveRunId(res.run_id);
      setLocalRunId(res.run_id);
      toast.success(`Pipeline started — Run ID: ${res.run_id}`);
      qc.invalidateQueries({ queryKey: ['runs'] });
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to start pipeline');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">AgentX Dashboard</h1>
        <p className="text-gray-400 text-sm mt-1">
          LangGraph 9-Agent Autonomous Code Review Pipeline · Cost: Rs. 0
        </p>
      </div>

      {/* Run form */}
      <div className="card">
        <h2 className="font-semibold text-white mb-4 flex items-center gap-2">
          <Play size={16} className="text-blue-400" /> Start New Run
        </h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">GitHub Repository URL *</label>
            <input
              type="url"
              value={repoUrl}
              onChange={e => setRepoUrl(e.target.value)}
              placeholder="https://github.com/owner/repo"
              required
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5
                         text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-400 mb-1">GitHub Token (optional)</label>
              <input
                type="password"
                value={githubToken}
                onChange={e => setGithubToken(e.target.value)}
                placeholder="ghp_xxxx (for private repos)"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5
                           text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-400 mb-1">Branch</label>
              <input
                type="text"
                value={branch}
                onChange={e => setBranch(e.target.value)}
                placeholder="main"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5
                           text-white placeholder-gray-500 focus:outline-none focus:border-blue-500"
              />
            </div>
          </div>
          <button type="submit" disabled={isSubmitting} className="btn-primary flex items-center gap-2">
            <Play size={14} />
            {isSubmitting ? 'Starting...' : 'Run AgentX Pipeline'}
          </button>
        </form>
      </div>

      {/* Live progress */}
      {activeRunId && (
        <PipelineProgress
          runId={activeRunId}
          onComplete={() => {
            qc.invalidateQueries({ queryKey: ['runs'] });
            router.push(`/runs/${activeRunId}`);
          }}
        />
      )}

      {/* Recent runs */}
      <div className="card">
        <h2 className="font-semibold text-white mb-4">Recent Runs</h2>
        {runs.length === 0 ? (
          <p className="text-gray-500 text-sm">No runs yet. Start your first pipeline above.</p>
        ) : (
          <div className="space-y-2">
            {runs.map(run => (
              <div
                key={run.id}
                className="flex items-center justify-between p-3 bg-gray-800 rounded-lg hover:bg-gray-750 cursor-pointer"
                onClick={() => router.push(`/runs/${run.id}`)}
              >
                <div className="flex items-center gap-3">
                  {STATUS_ICON[run.status] || <Clock size={14} className="text-blue-400" />}
                  <div>
                    <div className="text-sm font-medium text-white">
                      {run.repo_owner}/{run.repo_name || 'unknown'}
                    </div>
                    <div className="text-xs text-gray-500">
                      Run {run.id} ·{' '}
                      {formatDistanceToNow(new Date(run.started_at), { addSuffix: true })}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-4 text-xs text-gray-400">
                  <span>{run.total_issues} issues</span>
                  <span>{run.total_fixes} fixes</span>
                  {run.pr_url && (
                    <a
                      href={run.pr_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-400 hover:text-blue-300 flex items-center gap-1"
                      onClick={e => e.stopPropagation()}
                    >
                      <ExternalLink size={12} /> PR
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
