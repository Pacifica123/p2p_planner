import { env } from '@/shared/config/env';
import { ApiError } from '@/shared/api/errors';

interface ApiEnvelope<T> {
  data: T;
}

interface ErrorEnvelope {
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
  };
}

let accessToken: string | null = null;

export function setAccessToken(next: string | null) {
  accessToken = next?.trim() || null;
}

export function clearAccessToken() {
  accessToken = null;
}

export function getAccessToken() {
  return accessToken;
}

async function parseJson(response: Response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const hasBody = init.body !== undefined && init.body !== null;

  if (hasBody && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }

  let response: Response;
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, {
      ...init,
      credentials: 'include',
      headers,
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Network request failed';
    throw new ApiError(`Не удалось связаться с backend: ${message}. Проверь CORS, адрес API и запущен ли сервер.`, {
      status: 0,
      code: 'NETWORK_ERROR',
      details: error,
    });
  }

  const payload = await parseJson(response);

  if (!response.ok) {
    const error = (payload as ErrorEnvelope | null)?.error;
    if (response.status === 401) {
      clearAccessToken();
    }
    throw new ApiError(error?.message || `Request failed with ${response.status}`, {
      status: response.status,
      code: error?.code,
      details: error?.details,
    });
  }

  if (payload && typeof payload === 'object' && 'data' in (payload as Record<string, unknown>)) {
    return (payload as ApiEnvelope<T>).data;
  }

  return payload as T;
}
