import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom';
import { MainLayout } from '@/app/layouts/MainLayout';
import { useAuthSession } from '@/app/providers/AuthSessionProvider';
import { WorkspacesPage } from '@/features/workspaces/pages/WorkspacesPage';
import { WorkspaceBoardsPage } from '@/features/boards/pages/WorkspaceBoardsPage';
import { BoardPage } from '@/features/boards/pages/BoardPage';
import { UserAppearancePage } from '@/features/appearance/pages/UserAppearancePage';
import { BoardAppearancePage } from '@/features/appearance/pages/BoardAppearancePage';
import { AuthPage } from '@/features/auth/pages/AuthPage';
import { LoadingState } from '@/shared/ui/LoadingState';

function RequireAuth() {
  const { status } = useAuthSession();

  if (status === 'loading') {
    return <LoadingState label="Восстанавливаем session…" />;
  }

  if (status !== 'authenticated') {
    return <Navigate to="/auth" replace />;
  }

  return <Outlet />;
}

export function AppRouter() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/auth" element={<AuthPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<MainLayout />}>
            <Route path="/" element={<WorkspacesPage />} />
            <Route path="/settings/appearance" element={<UserAppearancePage />} />
            <Route path="/workspaces/:workspaceId/boards" element={<WorkspaceBoardsPage />} />
            <Route path="/workspaces/:workspaceId/boards/:boardId" element={<BoardPage />} />
            <Route path="/workspaces/:workspaceId/boards/:boardId/customize" element={<BoardAppearancePage />} />
          </Route>
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
