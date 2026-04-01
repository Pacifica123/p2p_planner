export const env = {
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL?.trim() || 'http://127.0.0.1:18080/api/v1').replace(/\/$/, ''),
  defaultDevUserId: import.meta.env.VITE_DEV_USER_ID?.trim() || '11111111-1111-7111-8111-111111111111',
};
