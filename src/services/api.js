import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 15000,
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const normalizedError = {
      ...error,
      status: error.response?.status,
      data: error.response?.data,
      message:
        error.response?.data?.detail ||
        error.response?.data?.message ||
        error.message ||
        'Unexpected API error.',
    };

    return Promise.reject(normalizedError);
  },
);

export default api;
