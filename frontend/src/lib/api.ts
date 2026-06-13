import axios from 'axios';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const startRun = async (data: { repo_url: string; branch?: string; github_token?: string }) => {
  const res = await axios.post(`${API_URL}/api/v1/runs`, data);
  return res.data;
};

// Added an optional limit parameter to handle listRuns(50) perfectly
export const listRuns = async (limit?: number) => {
  const url = limit ? `${API_URL}/api/v1/runs?limit=${limit}` : `${API_URL}/api/v1/runs`;
  const res = await axios.get(url);
  return res.data;
};

export const getRunDetails = async (runId: string) => {
  const res = await axios.get(`${API_URL}/api/v1/runs/${runId}`);
  return res.data;
};

export const getAFEStats = async () => {
  const res = await axios.get(`${API_URL}/api/v1/afe/stats`);
  return res.data;
};

export const submitFeedback = async (data: { run_id: string; pr_number: number; outcome: string; ml_patterns: string[] }) => {
  const res = await axios.post(`${API_URL}/api/v1/feedback`, data);
  return res.data;
};

export const cancelRun = async (runId: string) => {
  const res = await axios.delete(`${API_URL}/api/v1/runs/${runId}`);
  return res.data;
};

export const getHealth = async () => {
  const res = await axios.get(`${API_URL}/api/v1/health`);
  return res.data;
};
