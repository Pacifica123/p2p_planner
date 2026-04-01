import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { createColumn, deleteColumn, getColumns, updateColumn } from '@/features/columns/api/columns';

export const columnsQueryKey = (boardId?: string) => ['columns', boardId];

export function useColumnsQuery(boardId?: string) {
  return useQuery({
    queryKey: columnsQueryKey(boardId),
    queryFn: () => getColumns(boardId!),
    enabled: Boolean(boardId),
  });
}

export function useCreateColumnMutation(boardId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { name: string; description?: string }) => createColumn(boardId!, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: columnsQueryKey(boardId) });
    },
  });
}

export function useUpdateColumnMutation(boardId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ columnId, input }: { columnId: string; input: { name?: string; description?: string } }) =>
      updateColumn(boardId!, columnId, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: columnsQueryKey(boardId) });
    },
  });
}

export function useDeleteColumnMutation(boardId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (columnId: string) => deleteColumn(boardId!, columnId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: columnsQueryKey(boardId) });
    },
  });
}
