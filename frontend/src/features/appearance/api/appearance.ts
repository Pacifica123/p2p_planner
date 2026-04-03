import { apiRequest } from '@/shared/api/client';
import type {
  BoardAppearanceSettings,
  UpdateBoardAppearanceRequest,
  UpdateUserAppearancePreferencesRequest,
  UserAppearancePreferences,
} from '@/shared/types/api';

export function getMyAppearance() {
  return apiRequest<UserAppearancePreferences>('/me/appearance');
}

export function updateMyAppearance(input: UpdateUserAppearancePreferencesRequest) {
  return apiRequest<UserAppearancePreferences>('/me/appearance', {
    method: 'PUT',
    body: JSON.stringify(input),
  });
}

export function getBoardAppearance(boardId: string) {
  return apiRequest<BoardAppearanceSettings>(`/boards/${boardId}/appearance`);
}

export function updateBoardAppearance(boardId: string, input: UpdateBoardAppearanceRequest) {
  return apiRequest<BoardAppearanceSettings>(`/boards/${boardId}/appearance`, {
    method: 'PUT',
    body: JSON.stringify(input),
  });
}
