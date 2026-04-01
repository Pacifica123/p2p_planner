import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { archiveWorkspace, createWorkspace, getWorkspaces, updateWorkspace } from '@/features/workspaces/api/workspaces';

export const workspacesQueryKey = ['workspaces'];

export function useWorkspacesQuery() {
  return useQuery({
    queryKey: workspacesQueryKey,
    queryFn: getWorkspaces,
  });
}

export function useCreateWorkspaceMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createWorkspace,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: workspacesQueryKey });
    },
  });
}

export function useUpdateWorkspaceMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ workspaceId, input }: { workspaceId: string; input: { name?: string; description?: string; visibility?: 'private' | 'shared' } }) =>
      updateWorkspace(workspaceId, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: workspacesQueryKey });
    },
  });
}

export function useArchiveWorkspaceMutation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: archiveWorkspace,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: workspacesQueryKey });
    },
  });
}
