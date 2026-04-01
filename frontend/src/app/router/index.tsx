import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { MainLayout } from '@/app/layouts/MainLayout';
import { WorkspacesPage } from '@/features/workspaces/pages/WorkspacesPage';
import { WorkspaceBoardsPage } from '@/features/boards/pages/WorkspaceBoardsPage';
import { BoardPage } from '@/features/boards/pages/BoardPage';

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<MainLayout />}>
          <Route path="/" element={<Navigate to="/workspaces" replace />} />
          <Route path="/workspaces" element={<WorkspacesPage />} />
          <Route path="/workspaces/:workspaceId/boards" element={<WorkspaceBoardsPage />} />
          <Route path="/workspaces/:workspaceId/boards/:boardId" element={<BoardPage />} />
          <Route path="*" element={<Navigate to="/workspaces" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
