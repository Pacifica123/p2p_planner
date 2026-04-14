export const env = {
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL?.trim() || 'http://127.0.0.1:18080/api/v1').replace(/\/$/, ''),
};
