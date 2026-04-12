import { NavLink, Outlet, useParams } from 'react-router-dom';
import { paths } from '@/app/router/paths';
import { useDevSession } from '@/app/providers/DevSessionProvider';
import { env } from '@/shared/config/env';
import { useWorkspacesQuery } from '@/features/workspaces/hooks/useWorkspaces';
import { useBoardsQuery } from '@/features/boards/hooks/useBoards';
import { LoadingState } from '@/shared/ui/LoadingState';
import { ErrorState } from '@/shared/ui/ErrorState';
import { ApiError } from '@/shared/api/errors';

function getErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return fallback;
}

export function MainLayout() {
  const { workspaceId } = useParams();
  const { userId, setUserId } = useDevSession();
  const workspacesQuery = useWorkspacesQuery();
  const boardsQuery = useBoardsQuery(workspaceId);

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="app-sidebar__brand">
          <NavLink to={paths.home} className="brand-link">
            P2P Planner
          </NavLink>
          <p className="brand-copy">Web core UI v1</p>
        </div>

        <section className="sidebar-section">
          <div className="sidebar-section__header">Workspace switcher</div>
          {workspacesQuery.isLoading ? (
            <LoadingState label="Загружаем workspace list…" compact />
          ) : workspacesQuery.isError ? (
            <ErrorState title="Не удалось загрузить workspaces" description={getErrorMessage(workspacesQuery.error, 'Проверь backend и настройки API.')} compact />
          ) : (
            <nav className="nav-list nav-list--scroll">
              <NavLink to={paths.home} className={({ isActive }) => `nav-list__item ${isActive ? 'is-active' : ''}`} end>
                Все workspaces
              </NavLink>
              {workspacesQuery.data?.items.map((workspace) => (
                <NavLink
                  key={workspace.id}
                  to={paths.workspaceBoards(workspace.id)}
                  className={({ isActive }) => `nav-list__item ${isActive ? 'is-active' : ''}`}
                >
                  <span>{workspace.name}</span>
                  <span className="nav-list__meta">{workspace.visibility}</span>
                </NavLink>
              ))}
            </nav>
          )}
        </section>

        {workspaceId ? (
          <section className="sidebar-section sidebar-section--flex">
            <div className="sidebar-section__header">Boards in workspace</div>
            {boardsQuery.isLoading ? (
              <LoadingState label="Загружаем boards…" compact />
            ) : boardsQuery.isError ? (
              <ErrorState title="Не удалось загрузить boards" description={getErrorMessage(boardsQuery.error, 'Проверь backend и настройки API.')} compact />
            ) : (
              <nav className="nav-list nav-list--scroll">
                {boardsQuery.data?.items.map((board) => (
                  <NavLink
                    key={board.id}
                    to={paths.board(workspaceId, board.id)}
                    className={({ isActive }) => `nav-list__item ${isActive ? 'is-active' : ''}`}
                  >
                    <span>{board.name}</span>
                    <span className="nav-list__meta">{board.boardType}</span>
                  </NavLink>
                ))}
              </nav>
            )}
          </section>
        ) : null}
      </aside>

      <div className="app-main">
        <header className="topbar">
          <div>
            <h1 className="topbar__title">Core flow: workspace → board → column → card</h1>
            <p className="topbar__subtitle">Подтвержденный happy-path вокруг существующего backend CRUD.</p>
          </div>

          <div className="topbar__controls">
            <label className="field field--compact">
              <span className="field__label">Dev user id</span>
              <input value={userId} onChange={(event) => setUserId(event.target.value)} className="field__input" />
            </label>
            <div className="topbar__hint">API: {env.apiBaseUrl}</div>
          </div>
        </header>

        <main className="content-area">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
