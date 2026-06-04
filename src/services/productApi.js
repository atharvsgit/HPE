import api from './api';

export const listDatabases = async () => (await api.get('/databases')).data;
export const createDatabase = async (payload) => (await api.post('/databases', payload)).data;
export const testDatabase = async (id) => (await api.post(`/databases/${id}/test`)).data;
export const getDatabaseSchema = async (id) => (await api.get(`/databases/${id}/schema`)).data;
export const deleteDatabase = async (id) => {
  await api.delete(`/databases/${id}`);
};

export const planCommand = async (payload) => (await api.post('/assistant/plan', payload, { timeout: 45000 })).data;
export const approvePlan = async (plan) => (await api.post('/assistant/approve', { plan })).data;

export const getDashboardSummary = async () => (await api.get('/dashboard/summary')).data;
export const listJobs = async () => (await api.get('/orchestrator/jobs')).data;
export const createJob = async (payload) => (await api.post('/orchestrator/jobs', payload)).data;
export const updateJob = async (id, payload) => (await api.patch(`/orchestrator/jobs/${id}`, payload)).data;
export const runJob = async (id) => (await api.post(`/orchestrator/jobs/${id}/run`)).data;
export const pauseJob = async (id) => (await api.post(`/orchestrator/jobs/${id}/pause`)).data;
export const resumeJob = async (id) => (await api.post(`/orchestrator/jobs/${id}/resume`)).data;
export const deleteJob = async (id) => {
  await api.delete(`/orchestrator/jobs/${id}`);
};

export const listAlerts = async () => (await api.get('/alerts')).data;
export const listNotifications = async () => (await api.get('/notifications')).data;

export const getAppSettings = async () => (await api.get('/settings')).data;
export const updateAISettings = async (payload) => (await api.patch('/settings/ai', payload)).data;
export const updateNotificationSettings = async (payload) => (await api.patch('/settings/notifications', payload)).data;
