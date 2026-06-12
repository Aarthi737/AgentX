// AgentX — API Client
import axios from 'axios';
import type {
  AFEStats, RunDetail, RunListItem, RunStartResponse, StartRunRequest,
} from '@/types';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
});

// ── Runs ────────────────────────────────────────────────────────────────────

export async function startRun(req: StartRunRequest): Promise<RunStartResponse> {
  const { data } = await apiClient.post<RunStartResponse>('/api/v1/runs', req);
  return data;
}

export async function listRuns(limit = 20): Promise<RunListItem[]> {
  const { data } = await apiClient.get<RunListItem[]>('/api/v1/runs', {
    params: { limit },
  });
  return data;
}

export async function getRun(runId: string): Promise<RunDetail> {
  const { data } = await apiClient.get<RunDetail>(`/api/v1/runs/${runId}`);
  return data;
}

export async function cancelRun(runId: string): Promise<void> {
  await apiClient.delete(`/api/v1/runs/${runId}`);
}

export function getReportUrl(runId: string): string {
  return `${API_URL}/api/v1/runs/${runId}/report`;
}

// ── AFE ─────────────────────────────────────────────────────────────────────

export async function getAFEStats(): Promise<AFEStats> {
  const { data } = await apiClient.get<AFEStats>('/api/v1/afe/stats');
  return data;
}

export async function submitFeedback(payload: {
  run_id: string;
  pr_number: number;
  outcome: 'MERGED' | 'MODIFIED' | 'CLOSED';
  ml_patterns?: string[];
  human_modifications?: string;
}): Promise<void> {
  await apiClient.post('/api/v1/feedback', payload);
}

// ── Health ──────────────────────────────────────────────────────────────────

export async function getHealth() {
  const { data } = await apiClient.get('/api/v1/health');
  return data;
}
