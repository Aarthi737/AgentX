import axios from 'axios';

/**
 * AgentX API Client
 * Production-ready (Vercel + Railway)
 */

const API_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// -------------------- RUNS --------------------

export const startRun = async (data: {
  repo_url: string;
  branch?: string;
  github_token?: string;
}) => {
  const res = await api.post('/api/v1/runs', data);
  return res.data;
};

export const listRuns = async (limit?: number) => {
  const res = await api.get('/api/v1/runs', {
    params: limit ? { limit } : {},
  });
  return res.data;
};

export const getRunDetails = async (runId: string) => {
  if (!runId || runId === 'undefined') {
    throw new Error('Run ID is missing or undefined.');
  }

  const res = await api.get(`/api/v1/runs/${runId}`);
  return res.data;
};

export const cancelRun = async (runId: string) => {
  const res = await api.delete(`/api/v1/runs/${runId}`);
  return res.data;
};

// -------------------- AFE --------------------

export const getAFEStats = async () => {
  const res = await api.get('/api/v1/afe/stats');
  return res.data;
};

// -------------------- FEEDBACK --------------------

export const submitFeedback = async (data: {
  run_id: string;
  pr_number: number;
  outcome: string;
  ml_patterns: string[];
}) => {
  const res = await api.post('/api/v1/feedback', data);
  return res.data;
};

// -------------------- HEALTH --------------------

export const getHealth = async () => {
  const res = await api.get('/api/v1/health');
  return res.data;
};

export default api;