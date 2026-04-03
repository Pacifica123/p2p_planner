import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { MainLayout } from '@/app/layouts/MainLayout';
import { WorkspacesPage } from '@/features/workspaces/pages/WorkspacesPage';
import { WorkspaceBoardsPage } from '@/features/boards/pages/WorkspaceBoardsPage';
import { BoardPage } from '@/features/boards/pages/BoardPage';
import { UserAppearancePage } from '@/features/appearance/pages/UserAppearancePage';
import { BoardAppearancePage } from '@/features/appearance/pages/BoardAppearancePage';

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<MainLayout />}>
          <Route path="/" element={<WorkspacesPage />} />
          <Route path="/settings/appearance" element={<UserAppearancePage />} />
          <Route path="/workspaces/:workspaceId/boards" element={<WorkspaceBoardsPage />} />
          <Route path="/workspaces/:workspaceId/boards/:boardId" element={<BoardPage />} />
          <Route path="/workspaces/:workspaceId/boards/:boardId/customize" element={<BoardAppearancePage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
