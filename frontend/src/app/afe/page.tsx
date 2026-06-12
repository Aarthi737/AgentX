'use client';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { getAFEStats, submitFeedback } from '@/lib/api';
import type { AFEStats } from '@/types';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell,
} from 'recharts';
import { Brain, TrendingUp, RefreshCw, Loader } from 'lucide-react';
import { useState } from 'react';
import toast from 'react-hot-toast';

function WeightBar({ name, value }: { name: string; value: number }) {
  const pct = Math.min(100, (value / 2) * 100);
  const color = value > 1.2 ? '#22c55e' : value < 0.8 ? '#ef4444' : '#3b82f6';
  return (
    <div className="flex items-center gap-3">
      <div className="w-44 text-xs text-gray-400 truncate font-mono">{name}</div>
      <div className="flex-1 bg-gray-800 rounded-full h-2">
        <div className="h-2 rounded-full transition-all" style={{ width: `${pct}%`, background: color }} />
      </div>
      <div className="w-12 text-xs text-right font-mono" style={{ color }}>
        {value.toFixed(3)}
      </div>
    </div>
  );
}

export default function AFEPage() {
  const qc = useQueryClient();
  const [feedbackForm, setFeedbackForm] = useState({
    run_id: '', pr_number: '', outcome: 'MERGED', ml_patterns: '',
  });

  const { data: stats, isLoading } = useQuery<AFEStats>({
    queryKey: ['afe-stats'],
    queryFn: getAFEStats,
    refetchInterval: 15000,
  });

  const mutation = useMutation({
    mutationFn: () =>
      submitFeedback({
        run_id: feedbackForm.run_id,
        pr_number: parseInt(feedbackForm.pr_number) || 0,
        outcome: feedbackForm.outcome as 'MERGED' | 'MODIFIED' | 'CLOSED',
        ml_patterns: feedbackForm.ml_patterns
          ? feedbackForm.ml_patterns.split(',').map(s => s.trim()).filter(Boolean)
          : undefined,
      }),
    onSuccess: () => {
      toast.success('Feedback submitted — weights updated');
      qc.invalidateQueries({ queryKey: ['afe-stats'] });
      setFeedbackForm({ run_id: '', pr_number: '', outcome: 'MERGED', ml_patterns: '' });
    },
    onError: () => toast.error('Failed to submit feedback'),
  });

  const chartData = stats
    ? Object.entries(stats.patterns).map(([name, weight]) => ({ name, weight }))
    : [];

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white flex items-center gap-2">
          <Brain size={22} className="text-purple-400" /> Adaptive Feedback Engine
        </h1>
        <p className="text-gray-500 text-sm mt-1">
          Continuous learning from PR outcomes. Weights update after every merge, modification, or close.
        </p>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-40 text-gray-500">
          <Loader size={20} className="animate-spin mr-2" /> Loading AFE stats...
        </div>
      ) : (
        <>
          {/* Summary */}
          <div className="grid grid-cols-3 gap-4">
            {[
              {
                label: 'Patterns Tracked',
                value: stats?.total_patterns_tracked ?? 0,
                icon: TrendingUp,
                color: 'text-purple-400',
              },
              {
                label: 'Pending Feedback',
                value: stats?.pending_feedback ?? 0,
                icon: RefreshCw,
                color: 'text-amber-400',
              },
              {
                label: 'Learning Rate (Merge)',
                value: `+${((stats?.learning_rates['MERGED'] ?? 0.1) * 100).toFixed(0)}%`,
                icon: Brain,
                color: 'text-green-400',
              },
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

          {/* Weight chart */}
          <div className="card">
            <h2 className="font-semibold text-white mb-4">ML Pattern Weights</h2>
            <p className="text-xs text-gray-500 mb-4">
              Weights &gt; 1.0 = reinforced (pattern accepted by humans).
              Weights &lt; 1.0 = deprioritised (pattern closed/rejected).
              Range: [0.1, 2.0].
            </p>
            <div className="space-y-3">
              {Object.entries(stats?.patterns ?? {})
                .sort(([, a], [, b]) => b - a)
                .map(([name, weight]) => (
                  <WeightBar key={name} name={name} value={weight} />
                ))}
            </div>

            {chartData.length > 0 && (
              <div className="mt-6">
                <ResponsiveContainer width="100%" height={180}>
                  <BarChart data={chartData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis dataKey="name" tick={{ fontSize: 9, fill: '#6b7280' }} />
                    <YAxis domain={[0, 2]} tick={{ fontSize: 9, fill: '#6b7280' }} />
                    <Tooltip
                      contentStyle={{ background: '#111827', border: '1px solid #374151', fontSize: 11 }}
                      formatter={(v: number) => [v.toFixed(3), 'weight']}
                    />
                    <Bar dataKey="weight" radius={[4, 4, 0, 0]}>
                      {chartData.map((entry, index) => (
                        <Cell
                          key={index}
                          fill={entry.weight > 1.2 ? '#22c55e' : entry.weight < 0.8 ? '#ef4444' : '#3b82f6'}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* Learning rates legend */}
          <div className="card">
            <h2 className="font-semibold text-white mb-3">Learning Rate Configuration</h2>
            <div className="grid grid-cols-3 gap-4 text-sm">
              {[
                { outcome: 'MERGED', rate: stats?.learning_rates?.MERGED ?? 0.1, color: 'text-green-400', label: 'Reinforce' },
                { outcome: 'MODIFIED', rate: stats?.learning_rates?.MODIFIED ?? 0.03, color: 'text-amber-400', label: 'Partial learn' },
                { outcome: 'CLOSED', rate: stats?.learning_rates?.CLOSED ?? -0.15, color: 'text-red-400', label: 'Deprioritise' },
              ].map(({ outcome, rate, color, label }) => (
                <div key={outcome} className="bg-gray-800 rounded-lg p-3">
                  <div className={`font-bold ${color}`}>{outcome}</div>
                  <div className="text-xs text-gray-500 mt-0.5">{label}</div>
                  <div className="font-mono text-sm mt-1">
                    Δ = {rate > 0 ? '+' : ''}{rate}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Manual feedback submission */}
          <div className="card">
            <h2 className="font-semibold text-white mb-4">Submit Manual Feedback</h2>
            <p className="text-xs text-gray-500 mb-4">
              Manually record a PR outcome to train the AFE (normally triggered via GitHub webhook).
            </p>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs text-gray-400 mb-1">Run ID</label>
                <input
                  value={feedbackForm.run_id}
                  onChange={e => setFeedbackForm(p => ({ ...p, run_id: e.target.value }))}
                  placeholder="e.g. 22f07458"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                             text-white text-sm placeholder-gray-600 focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">PR Number</label>
                <input
                  type="number"
                  value={feedbackForm.pr_number}
                  onChange={e => setFeedbackForm(p => ({ ...p, pr_number: e.target.value }))}
                  placeholder="1"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                             text-white text-sm placeholder-gray-600 focus:outline-none focus:border-blue-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">Outcome</label>
                <select
                  value={feedbackForm.outcome}
                  onChange={e => setFeedbackForm(p => ({ ...p, outcome: e.target.value }))}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                             text-white text-sm focus:outline-none focus:border-blue-500"
                >
                  <option value="MERGED">MERGED — Reinforce</option>
                  <option value="MODIFIED">MODIFIED — Partial learn</option>
                  <option value="CLOSED">CLOSED — Deprioritise</option>
                </select>
              </div>
              <div>
                <label className="block text-xs text-gray-400 mb-1">ML Patterns (comma-separated)</label>
                <input
                  value={feedbackForm.ml_patterns}
                  onChange={e => setFeedbackForm(p => ({ ...p, ml_patterns: e.target.value }))}
                  placeholder="missing_random_seed, data_leakage"
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2
                             text-white text-sm placeholder-gray-600 focus:outline-none focus:border-blue-500"
                />
              </div>
            </div>
            <button
              onClick={() => mutation.mutate()}
              disabled={!feedbackForm.run_id || mutation.isPending}
              className="btn-primary mt-4 flex items-center gap-2"
            >
              {mutation.isPending ? <Loader size={14} className="animate-spin" /> : <Brain size={14} />}
              Submit Feedback
            </button>
          </div>
        </>
      )}
    </div>
  );
}
