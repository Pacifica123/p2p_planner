import { apiRequest } from '@/shared/api/client';
import type { Workspace, WorkspaceListResponse } from '@/shared/types/api';

export function getWorkspaces() {
  return apiRequest<WorkspaceListResponse>('/workspaces');
}

export function createWorkspace(input: { name: string; visibility: 'private' | 'shared'; description?: string }) {
  return apiRequest<Workspace>('/workspaces', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function updateWorkspace(workspaceId: string, input: Partial<Pick<Workspace, 'name' | 'description' | 'visibility'>>) {
  return apiRequest<Workspace>(`/workspaces/${workspaceId}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  });
}

export function archiveWorkspace(workspaceId: string) {
  return apiRequest<Workspace>(`/workspaces/${workspaceId}/archive`, {
    method: 'POST',
  });
}
