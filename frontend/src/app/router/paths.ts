export const paths = {
  home: '/',
  userAppearance: '/settings/appearance',
  workspaceBoards: (workspaceId: string) => `/workspaces/${workspaceId}/boards`,
  board: (workspaceId: string, boardId: string) => `/workspaces/${workspaceId}/boards/${boardId}`,
  boardAppearance: (workspaceId: string, boardId: string) => `/workspaces/${workspaceId}/boards/${boardId}/customize`,
};
