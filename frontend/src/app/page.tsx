'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import toast from 'react-hot-toast';
import { GitBranch, Play, ExternalLink, Clock, CheckCircle, XCircle, AlertTriangle } from 'lucide-react';
import { startRun, listRuns } from '@/lib/api';

export default function Dashboard() {
  const router = useRouter();
  const [repoUrl, setRepoUrl] = useState('');
  const [branch, setBranch] = useState('main');
  const [githubToken, setGithubToken] = useState('');
  const [loading, setLoading] = useState(false);
  const [runs, setRuns] = useState<any[]>([]); // Using explicit type-bypass to avoid strict property mismatched errors

  useEffect(() => {
    fetchRuns();
  }, []);

  const fetchRuns = async () => {
    try {
      const data = await listRuns();
      setRuns(data || []);
    } catch (err) {
      console.error(err);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!repoUrl) return toast.error('Please enter a repository URL');
    setLoading(true);
    try {
      const res = await startRun({ repo_url: repoUrl, branch, github_token: githubToken || undefined });
      toast.success('Pipeline orchestration triggered!');
      const targetId = res.run_id || res.id;
      if (targetId) router.push(`/runs/${targetId}`);
    } catch (err: any) {
      toast.error(err.response?.data?.message || 'Failed to start run');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-8 p-6 max-w-6xl mx-auto text-gray-200">
      <div className="flex justify-between items-center border-b border-gray-800 pb-4">
        <div>
          <h1 className="text-3xl font-bold text-white bg-gradient-to-r from-blue-400 to-indigo-500 bg-clip-text text-transparent">AgentX Dashboard</h1>
          <p className="text-gray-400 text-sm mt-1">Autonomous multi-agent code analysis & patch orchestration.</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4 shadow-xl">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2"><Play className="w-4 h-4 text-emerald-400" /> Start Repository Run</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <input type="text" placeholder="GitHub Repo URL (e.g., https://github.com/owner/repo)" value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} className="bg-black border border-gray-800 rounded-lg p-3 text-sm focus:outline-none focus:border-indigo-500 text-white md:col-span-2" />
          <input type="text" placeholder="Branch (default: main)" value={branch} onChange={(e) => setBranch(e.target.value)} className="bg-black border border-gray-800 rounded-lg p-3 text-sm focus:outline-none focus:border-indigo-500 text-white" />
        </div>
        <input type="password" placeholder="GitHub PAT Token (Optional for public repos)" value={githubToken} onChange={(e) => setGithubToken(e.target.value)} className="w-full bg-black border border-gray-800 rounded-lg p-3 text-sm focus:outline-none focus:border-indigo-500 text-white" />
        <button type="submit" disabled={loading} className="w-full bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-3 rounded-lg text-sm transition-all shadow-lg flex justify-center items-center gap-2 disabled:opacity-50">
          {loading ? 'Initializing Agents...' : 'Trigger Agentic Pipeline'}
        </button>
      </form>

      <div className="space-y-4">
        <h2 className="text-xl font-semibold text-white flex items-center gap-2"><Clock className="w-5 h-5 text-indigo-400" /> Recent Executions</h2>
        <div className="grid grid-cols-1 gap-3">
          {runs.length === 0 ? (
            <div className="text-center py-12 text-gray-500 border border-dashed border-gray-800 rounded-xl">No active or previous runs found.</div>
          ) : (
            runs.map((run, idx) => {
              const currentRunId = run.run_id || run.id || `run-${idx}`;
              return (
                <div key={currentRunId} onClick={() => router.push(`/runs/${currentRunId}`)} className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 hover:border-gray-700 transition-all cursor-pointer shadow-md">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-indigo-400 bg-indigo-950/50 px-2 py-1 rounded border border-indigo-900">
                        {String(currentRunId).slice(0, 8)}
                      </span>
                      <span className="font-medium text-white text-sm truncate max-w-xs sm:max-w-md">
                        {run.repo_url ? run.repo_url.replace('https://github.com/', '') : 'Unknown Repository'}
                      </span>
                    </div>
                    <div className="flex items-center gap-4 text-xs text-gray-400">
                      <span className="flex items-center gap-1"><GitBranch className="w-3 h-3" /> {run.branch || 'main'}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 w-full sm:w-auto justify-between sm:justify-end">
                    <span className={`text-xs px-2.5 py-1 rounded-full font-medium border flex items-center gap-1 ${
                      run.status === 'PR_CREATED' ? 'bg-emerald-950/40 text-emerald-400 border-emerald-900' :
                      run.status === 'FAILED' ? 'bg-rose-950/40 text-rose-400 border-rose-900' :
                      'bg-amber-950/40 text-amber-400 border-amber-900'
                    }`}>
                      {run.status === 'PR_CREATED' && <CheckCircle className="w-3 h-3" />}
                      {run.status === 'FAILED' && <XCircle className="w-3 h-3" />}
                      {['PENDING', 'RUNNING'].includes(run.status || '') && <AlertTriangle className="w-3 h-3 animate-pulse" />}
                      {run.status || 'PENDING'}
                    </span>
                    <ExternalLink className="w-4 h-4 text-gray-500 hover:text-white" />
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
