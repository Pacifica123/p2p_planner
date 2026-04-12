export const paths = {
  home: '/workspaces',
  workspaceBoards: (workspaceId: string) => `/workspaces/${workspaceId}/boards`,
  board: (workspaceId: string, boardId: string) => `/workspaces/${workspaceId}/boards/${boardId}`,
};
