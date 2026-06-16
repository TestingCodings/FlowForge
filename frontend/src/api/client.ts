import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("ff_access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

let refreshInFlight = false;

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config;
    if (error.response?.status !== 401 || original._retry) {
      return Promise.reject(error);
    }

    const refresh = localStorage.getItem("ff_refresh_token");
    if (!refresh || refreshInFlight) {
      localStorage.removeItem("ff_access_token");
      localStorage.removeItem("ff_refresh_token");
      return Promise.reject(error);
    }

    refreshInFlight = true;
    try {
      const response = await axios.post(`${API_BASE_URL}/auth/refresh/`, { refresh });
      localStorage.setItem("ff_access_token", response.data.access);
      original._retry = true;
      return apiClient(original);
    } finally {
      refreshInFlight = false;
    }
  }
);
