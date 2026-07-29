import { useQuery } from '@tanstack/react-query';
import {
  getBoardActivity,
  getBoardProductivity,
  getCardActivity,
} from '@/features/activity/api/activity';

export const boardActivityQueryKey = (boardId?: string) => ['board-activity', boardId];
export const cardActivityQueryKey = (cardId?: string) => ['card-activity', cardId];
export const boardProductivityQueryKey = (boardId?: string) => ['board-productivity', boardId];

export function useBoardActivityQuery(boardId?: string) {
  return useQuery({
    queryKey: boardActivityQueryKey(boardId),
    queryFn: () => getBoardActivity(boardId!),
    enabled: Boolean(boardId),
  });
}

export function useBoardProductivityQuery(boardId?: string) {
  return useQuery({
    queryKey: boardProductivityQueryKey(boardId),
    queryFn: () => getBoardProductivity(boardId!),
    enabled: Boolean(boardId),
    staleTime: 30_000,
  });
}

export function useCardActivityQuery(cardId?: string) {
  return useQuery({
    queryKey: cardActivityQueryKey(cardId),
    queryFn: () => getCardActivity(cardId!),
    enabled: Boolean(cardId),
  });
}
