const CONTROL_ORIGIN = 'http://127.0.0.1:8765';

export interface GitHubCommitInfo {
  sha: string;
  shortSha: string;
  message: string;
  committedAt: string | null;
  url: string;
}

export interface UpdateJobState {
  id: string;
  status: 'idle' | 'queued' | 'running' | 'succeeded' | 'failed';
  phase: string;
  progress: number;
  message: string;
  targetSha: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  error: string | null;
  verified: boolean;
}

export interface UpdateControlState {
  available: true;
  sessionToken: string;
  repository: string;
  branch: string;
  installedRevision: string | null;
  latest: GitHubCommitInfo | null;
  job: UpdateJobState;
}

export function isLocalUpdateSurface() {
  return ['127.0.0.1', 'localhost', '::1'].includes(window.location.hostname);
}

async function controlRequest<T>(
  path: string,
  init: RequestInit = {},
  token?: string,
) {
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  if (token) headers.set('X-P2PKanban-Control', token);
  const response = await fetch(`${CONTROL_ORIGIN}${path}`, { ...init, headers });
  const payload = await response.json().catch(() => null) as { error?: string } | null;
  if (!response.ok) throw new Error(payload?.error || `Control plane: HTTP ${response.status}`);
  return payload as T;
}

export function getUpdateControlState() {
  return controlRequest<UpdateControlState>('/v1/status');
}

export function checkForSourceUpdate(token: string) {
  return controlRequest<UpdateControlState>('/v1/check', { method: 'POST' }, token);
}

export function startSourceUpdate(token: string, targetSha: string) {
  return controlRequest<UpdateControlState>(
    '/v1/update',
    {
      method: 'POST',
      body: JSON.stringify({ targetSha }),
      headers: { 'Content-Type': 'application/json' },
    },
    token,
  );
}
