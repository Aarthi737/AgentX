'use client';
import { useEffect, useState } from 'react';
import { useRunWebSocket } from '@/hooks/useRunWebSocket';
import type { ProgressEvent } from '@/types';
import { CheckCircle, Circle, Loader, XCircle, ExternalLink } from 'lucide-react';
import { clsx } from 'clsx';

const PHASES = [
  { id: 1, name: 'Ingestion',       agent: 'Orchestrator' },
  { id: 2, name: 'Repo Intelligence', agent: 'RepoIntelligence' },
  { id: 3, name: 'Parallel Analysis', agent: 'CodeAnalysis + SecurityScanner' },
  { id: 4, name: 'Rank & Aggregate', agent: 'Orchestrator' },
  { id: 5, name: 'Root Cause Analysis', agent: 'RCA' },
  { id: 6, name: 'Fix Generation',  agent: 'FixGenerator' },
  { id: 7, name: 'Validation Debate', agent: 'Validation' },
  { id: 8, name: 'Docker Verification', agent: 'Verification' },
  { id: 9, name: 'PR Creation',     agent: 'PRCreator' },
];

interface Props {
  runId: string;
  onComplete?: (event: ProgressEvent) => void;
}

export function PipelineProgress({ runId, onComplete }: Props) {
  const [currentPhase, setCurrentPhase] = useState(0);
  const [messages, setMessages] = useState<string[]>([]);
  const [completed, setCompleted] = useState(false);
  const [failed, setFailed] = useState(false);
  const [prUrl, setPrUrl] = useState<string | null>(null);

  const { connected, events } = useRunWebSocket({
    runId,
    onEvent: (event) => {
      if (event.phase !== undefined) setCurrentPhase(event.phase);
      if (event.message) {
        setMessages(prev => [...prev.slice(-50), `[${event.agent || 'pipeline'}] ${event.message}`]);
      }
    },
    onComplete: (event) => {
      setCompleted(true);
      if (event.pr_url) setPrUrl(event.pr_url);
      onComplete?.(event);
    },
    onError: (err) => {
      setFailed(true);
      setMessages(prev => [...prev, `ERROR: ${err}`]);
    },
  });

  return (
    <div className="card space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-white flex items-center gap-2">
          {completed ? (
            <CheckCircle size={16} className="text-green-400" />
          ) : failed ? (
            <XCircle size={16} className="text-red-400" />
          ) : (
            <Loader size={16} className="text-blue-400 animate-spin" />
          )}
          Pipeline {completed ? 'Complete' : failed ? 'Failed' : 'Running'}
        </h3>
        <div className="flex items-center gap-2 text-xs">
          <div className={clsx('w-2 h-2 rounded-full', connected ? 'bg-green-400' : 'bg-gray-500')} />
          <span className="text-gray-400">{connected ? 'Live' : 'Connecting...'}</span>
          <span className="text-gray-600">Run {runId}</span>
        </div>
      </div>

      {/* Phase stepper */}
      <div className="grid grid-cols-3 gap-2">
        {PHASES.map((phase) => {
          const done = currentPhase > phase.id || completed;
          const active = currentPhase === phase.id && !completed && !failed;
          return (
            <div
              key={phase.id}
              className={clsx(
                'flex items-center gap-2 p-2 rounded-lg text-xs border',
                done ? 'border-green-800 bg-green-900/20 text-green-400' :
                active ? 'border-blue-700 bg-blue-900/20 text-blue-300' :
                'border-gray-800 text-gray-600'
              )}
            >
              {done ? (
                <CheckCircle size={12} />
              ) : active ? (
                <Loader size={12} className="animate-spin" />
              ) : (
                <Circle size={12} />
              )}
              <div>
                <div className="font-medium">{phase.name}</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Log stream */}
      <div className="bg-gray-950 rounded-lg p-3 h-32 overflow-y-auto font-mono text-xs text-gray-400">
        {messages.length === 0 ? (
          <span className="text-gray-600">Waiting for pipeline events...</span>
        ) : (
          messages.map((msg, i) => <div key={i}>{msg}</div>)
        )}
      </div>

      {/* PR link */}
      {prUrl && (
        <a
          href={prUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 text-blue-400 hover:text-blue-300 text-sm font-medium"
        >
          <ExternalLink size={14} /> View Pull Request
        </a>
      )}
    </div>
  );
}
