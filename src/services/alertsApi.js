import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const api = axios.create({ baseURL: API_BASE });

export async function fetchViolations({ limit = 50, status = null } = {}) {
  const params = { limit };
  if (status) params.status = status;
  const { data } = await api.get('/violations', { params });
  return data;
}

export async function fetchViolation(id) {
  const { data } = await api.get(`/violations/${id}`);
  return data;
}

export async function fetchViolationBatches({ limit = 50, status = null } = {}) {
  const params = { limit };
  if (status) params.status = status;
  const { data } = await api.get('/violation-batches', { params });
  return data;
}

export async function sendBatchNow(batchId) {
  const { data } = await api.post(`/violation-batches/${batchId}/send-now`);
  return data;
}

export async function reEnrichBatch(batchId) {
  const { data } = await api.post(`/violation-batches/${batchId}/re-enrich`);
  return data;
}

export async function submitFeedback(batchId, feedback) {
  const { data } = await api.post(`/violation-batches/${batchId}/feedback`, feedback);
  return data;
}

export async function fetchFeedback(batchId) {
  const { data } = await api.get(`/violation-batches/${batchId}/feedback`);
  return data;
}

