'use client';
import { useQuery } from '@tanstack/react-query';
import { useParams, useRouter } from 'next/navigation';
import { getRun, getReportUrl } from '@/lib/api';
import type { Issue, Patch, RunDetail } from '@/types';
import {
  AlertTriangle, ArrowLeft, CheckCircle, Download, ExternalLink,
  FileCode, GitMerge, Shield, XCircle,
} from 'lucide-react';
import { clsx } from 'clsx';
import { formatDistanceToNow } from 'date-fns';
import { RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer, Tooltip } from 'recharts';

const SEV_CLASS: Record<string, string> = {
  CRITICAL: 'badge-critical',
  HIGH: 'badge-high',
  MEDIUM: 'badge-medium',
  LOW: 'badge-low',
  INFO: 'badge-info',
};

function SeverityBadge({ severity }: { severity: string }) {
  return <span className={SEV_CLASS[severity] || 'badge-info'}>{severity}</span>;
}

function ConfidenceBar({ value }: { value: number }) {
  const color = value >= 90 ? 'bg-green-500' : value >= 70 ? 'bg-amber-500' : 'bg-red-500';
  return (
    <div className="flex items-center gap-2 w-full">
      <div className="flex-1 bg-gray-800 rounded-full h-1.5">
        <div className={clsx('h-1.5 rounded-full', color)} style={{ width: `${value}%` }} />
      </div>
      <span className="text-xs text-gray-400 w-10 text-right">{Math.round(value)}%</span>
    </div>
  );
}

function PatchCard({ patch, issue }: { patch: Patch; issue?: Issue }) {
  const radarData = [
    { subject: 'Correctness', value: patch.validation_correctness },
    { subject: 'Security', value: patch.validation_security },
    { subject: 'Practices', value: patch.validation_best_practices },
    { subject: 'Research', value: patch.validation_research_integrity },
    { subject: 'Contract', value: patch.validation_contract_preservation },
  ];

  return (
    <div className="border border-gray-800 rounded-xl p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-medium text-white text-sm">{issue?.title || 'Fix'}</div>
          <div className="text-xs text-gray-500">{issue?.file_path}{issue?.line_start ? `:${issue.line_start}` : ''}</div>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {issue?.severity && <SeverityBadge severity={issue.severity} />}
          {patch.safe_to_merge === true && (
            <span title="Safe to merge">
              <CheckCircle size={14} className="text-green-400" />
            </span>
          )}
          {patch.safe_to_merge === false && (
            <span title="Review required">
              <AlertTriangle size={14} className="text-amber-400" />
            </span>
          )}
        </div>
      </div>

      <div>
        <div className="text-xs text-gray-500 mb-1">Confidence</div>
        <ConfidenceBar value={patch.validation_confidence} />
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Radar chart */}
        <ResponsiveContainer width="100%" height={120}>
          <RadarChart data={radarData}>
            <PolarGrid stroke="#374151" />
            <PolarAngleAxis dataKey="subject" tick={{ fontSize: 9, fill: '#9ca3af' }} />
            <Radar dataKey="value" stroke="#3b82f6" fill="#3b82f6" fillOpacity={0.2} />
            <Tooltip
              contentStyle={{ background: '#111827', border: '1px solid #374151', fontSize: 11 }}
              formatter={(v: number) => [`${v}%`]}
            />
          </RadarChart>
        </ResponsiveContainer>

        {/* Stats */}
        <div className="text-xs space-y-1.5">
          <div className="flex justify-between">
            <span className="text-gray-500">Tests Passed</span>
            <span className="text-green-400">{patch.tests_passed}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Tests Failed</span>
            <span className={patch.tests_failed > 0 ? 'text-red-400' : 'text-gray-400'}>
              {patch.tests_failed}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Status</span>
            <span className={clsx(
              'font-medium',
              patch.status === 'APPROVED' ? 'text-green-400' :
              patch.status === 'HUMAN_REVIEW' ? 'text-amber-400' : 'text-gray-400'
            )}>{patch.status}</span>
          </div>
        </div>
      </div>

      {patch.fix_explanation && (
        <p className="text-xs text-gray-400 border-t border-gray-800 pt-2">
          {patch.fix_explanation}
        </p>
      )}
    </div>
  );
}

export default function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const router = useRouter();

  const { data: run, isLoading } = useQuery<RunDetail>({
    queryKey: ['run', runId],
    queryFn: () => getRun(runId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && ['PR_CREATED', 'FAILED'].includes(status) ? false : 5000;
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500">
        Loading run details...
      </div>
    );
  }
  if (!run) {
    return <div className="text-red-400">Run not found</div>;
  }

  const issuesById = Object.fromEntries(run.issues.map(i => [i.id, i]));
  const approved = run.patches.filter(p => p.status === 'APPROVED').length;
  const humanReview = run.patches.filter(p => p.status === 'HUMAN_REVIEW').length;

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <button onClick={() => router.back()} className="btn-ghost flex items-center gap-1 mb-2 -ml-1">
            <ArrowLeft size={14} /> Back
          </button>
          <h1 className="text-xl font-bold text-white">
            {run.repo_owner}/{run.repo_name}
          </h1>
          <div className="text-gray-500 text-sm flex items-center gap-3 mt-1">
            <span>Run {run.id}</span>
            <span>·</span>
            <span>{formatDistanceToNow(new Date(run.started_at), { addSuffix: true })}</span>
            <span>·</span>
            <span className={clsx(
              'font-medium',
              run.status === 'PR_CREATED' ? 'text-green-400' :
              run.status === 'FAILED' ? 'text-red-400' : 'text-blue-400'
            )}>{run.status}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {run.pr_url && (
            <a href={run.pr_url} target="_blank" rel="noopener noreferrer"
               className="btn-primary flex items-center gap-2 text-sm">
              <ExternalLink size={14} /> View PR #{run.pr_number}
            </a>
          )}
          {run.pdf_report_path && (
            <a href={getReportUrl(run.id)} download
               className="btn-ghost flex items-center gap-2 text-sm border border-gray-700">
              <Download size={14} /> PDF Report
            </a>
          )}
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-4 gap-4">
        {[
          { label: 'Issues Found', value: run.total_issues, icon: AlertTriangle, color: 'text-amber-400' },
          { label: 'Fixes Applied', value: run.total_fixes, icon: GitMerge, color: 'text-blue-400' },
          { label: 'Approved', value: approved, icon: CheckCircle, color: 'text-green-400' },
          { label: 'Human Review', value: humanReview, icon: Shield, color: 'text-amber-400' },
        ].map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="card flex items-center gap-3">
            <Icon size={24} className={color} />
            <div>
              <div className="text-2xl font-bold text-white">{value}</div>
              <div className="text-xs text-gray-500">{label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Issues table */}
      {run.issues.length > 0 && (
        <div className="card">
          <h2 className="font-semibold text-white mb-4 flex items-center gap-2">
            <AlertTriangle size={16} className="text-amber-400" /> Detected Issues ({run.issues.length})
          </h2>
          <div className="space-y-2">
            {run.issues.map(issue => (
              <div key={issue.id} className="flex items-start gap-3 p-3 bg-gray-800 rounded-lg">
                <div className="flex-shrink-0 pt-0.5">
                  <span className="text-gray-500 text-xs font-mono">#{issue.rank}</span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <SeverityBadge severity={issue.severity} />
                    {issue.ml_pattern && (
                      <span className="text-xs text-purple-400 bg-purple-900/30 border border-purple-800 px-1.5 py-0.5 rounded">
                        {issue.ml_pattern}
                      </span>
                    )}
                    <span className="text-sm text-white font-medium">{issue.title}</span>
                  </div>
                  <div className="text-xs text-gray-500 mt-1 flex items-center gap-2">
                    <FileCode size={10} />
                    {issue.file_path}{issue.line_start ? `:${issue.line_start}` : ''}
                  </div>
                  <p className="text-xs text-gray-400 mt-1 line-clamp-2">{issue.description}</p>
                </div>
                <div className="text-xs text-gray-600 text-right flex-shrink-0">
                  <div>Score: {issue.composite_score.toFixed(2)}</div>
                  <div>CVSS: {issue.cvss_score}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Patches */}
      {run.patches.length > 0 && (
        <div>
          <h2 className="font-semibold text-white mb-4 flex items-center gap-2">
            <GitMerge size={16} className="text-blue-400" /> Generated Fixes ({run.patches.length})
          </h2>
          <div className="grid grid-cols-2 gap-4">
            {run.patches.map(patch => (
              <PatchCard
                key={patch.id}
                patch={patch}
                issue={issuesById[patch.issue_id]}
              />
            ))}
          </div>
        </div>
      )}

      {/* Audit log */}
      {run.audit_logs.length > 0 && (
        <div className="card">
          <h2 className="font-semibold text-white mb-3 text-sm">Audit Trail</h2>
          <div className="space-y-1 max-h-64 overflow-y-auto font-mono text-xs">
            {run.audit_logs.map(log => (
              <div key={log.id} className="flex items-start gap-3 text-gray-500">
                <span className="text-gray-700 flex-shrink-0">{new Date(log.created_at).toLocaleTimeString()}</span>
                <span className={clsx(
                  'flex-shrink-0 font-semibold',
                  log.status === 'SUCCESS' ? 'text-green-600' :
                  log.status === 'FAILURE' ? 'text-red-500' : 'text-amber-500'
                )}>{log.status}</span>
                <span className="text-blue-600">[{log.agent_name}]</span>
                <span className="text-gray-400">{log.action}</span>
                {log.message && <span className="text-gray-500 truncate">{log.message}</span>}
                {log.duration_ms && <span className="text-gray-700 ml-auto flex-shrink-0">{log.duration_ms}ms</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
