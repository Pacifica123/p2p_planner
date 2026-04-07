import { apiRequest } from '@/shared/api/client';
import type { Card, CardListResponse } from '@/shared/types/api';

export interface MoveCardInput {
  targetColumnId: string;
  position?: number | null;
}

export interface ReorderColumnCardsInput {
  items: Array<{
    cardId: string;
    position: number;
  }>;
}

export function getCards(boardId: string) {
  return apiRequest<CardListResponse>(`/boards/${boardId}/cards`);
}

export function getCard(cardId: string) {
  return apiRequest<Card>(`/cards/${cardId}`);
}

export function createCard(boardId: string, input: {
  title: string;
  description?: string;
  columnId: string;
  status?: Card['status'];
  priority?: Card['priority'];
}) {
  return apiRequest<Card>(`/boards/${boardId}/cards`, {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function updateCard(cardId: string, input: { title?: string; description?: string | null; status?: Card['status']; priority?: Card['priority']; dueAt?: string | null }) {
  return apiRequest<Card>(`/cards/${cardId}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  });
}

export function moveCard(cardId: string, input: MoveCardInput) {
  return apiRequest<Card>(`/cards/${cardId}/move`, {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function reorderColumnCards(columnId: string, input: ReorderColumnCardsInput) {
  return apiRequest<CardListResponse>(`/columns/${columnId}/cards/reorder`, {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function archiveCard(cardId: string) {
  return apiRequest<Card>(`/cards/${cardId}/archive`, {
    method: 'POST',
  });
}

export function unarchiveCard(cardId: string) {
  return apiRequest<Card>(`/cards/${cardId}/unarchive`, {
    method: 'POST',
  });
}

export function deleteCard(cardId: string) {
  return apiRequest<void>(`/cards/${cardId}`, {
    method: 'DELETE',
  });
}
