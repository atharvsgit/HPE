import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 15000,
});

function errorMessage(error) {
  const detail = error.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.message) return detail.message;
  if (error.response?.data?.message) return error.response.data.message;
  return error.message || 'Unexpected API error.';
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const normalizedError = {
      ...error,
      status: error.response?.status,
      data: error.response?.data,
      message: errorMessage(error),
    };

    return Promise.reject(normalizedError);
  },
);

export default api;
