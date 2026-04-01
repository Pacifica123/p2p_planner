import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { archiveCard, createCard, deleteCard, getCard, getCards, moveCard, unarchiveCard, updateCard } from '@/features/cards/api/cards';
import { columnsQueryKey } from '@/features/columns/hooks/useColumns';
import { boardActivityQueryKey, cardActivityQueryKey } from '@/features/activity/hooks/useActivity';

export const cardsQueryKey = (boardId?: string) => ['cards', boardId];
export const cardDetailQueryKey = (cardId?: string) => ['card', cardId];

function invalidateBoardSurface(queryClient: ReturnType<typeof useQueryClient>, boardId?: string, cardId?: string) {
  void queryClient.invalidateQueries({ queryKey: cardsQueryKey(boardId) });
  void queryClient.invalidateQueries({ queryKey: columnsQueryKey(boardId) });
  void queryClient.invalidateQueries({ queryKey: boardActivityQueryKey(boardId) });
  if (cardId) {
    void queryClient.invalidateQueries({ queryKey: cardDetailQueryKey(cardId) });
    void queryClient.invalidateQueries({ queryKey: cardActivityQueryKey(cardId) });
  }
}

export function useCardsQuery(boardId?: string) {
  return useQuery({
    queryKey: cardsQueryKey(boardId),
    queryFn: () => getCards(boardId!),
    enabled: Boolean(boardId),
  });
}

export function useCardQuery(cardId?: string) {
  return useQuery({
    queryKey: cardDetailQueryKey(cardId),
    queryFn: () => getCard(cardId!),
    enabled: Boolean(cardId),
  });
}

export function useCreateCardMutation(boardId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { title: string; description?: string; columnId: string }) => createCard(boardId!, input),
    onSuccess: (card) => {
      invalidateBoardSurface(queryClient, boardId, card.id);
    },
  });
}

export function useUpdateCardMutation(boardId?: string, cardId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { title?: string; description?: string | null; status?: string | null; priority?: string | null }) =>
      updateCard(cardId!, input),
    onSuccess: () => {
      invalidateBoardSurface(queryClient, boardId, cardId);
    },
  });
}

export function useMoveCardMutation(boardId?: string, cardId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (targetColumnId: string) => moveCard(cardId!, targetColumnId),
    onSuccess: () => {
      invalidateBoardSurface(queryClient, boardId, cardId);
    },
  });
}

export function useArchiveCardMutation(boardId?: string, cardId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => archiveCard(cardId!),
    onSuccess: () => {
      invalidateBoardSurface(queryClient, boardId, cardId);
    },
  });
}

export function useUnarchiveCardMutation(boardId?: string, cardId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unarchiveCard(cardId!),
    onSuccess: () => {
      invalidateBoardSurface(queryClient, boardId, cardId);
    },
  });
}

export function useDeleteCardMutation(boardId?: string, cardId?: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => deleteCard(cardId!),
    onSuccess: () => {
      invalidateBoardSurface(queryClient, boardId, cardId);
    },
  });
}
