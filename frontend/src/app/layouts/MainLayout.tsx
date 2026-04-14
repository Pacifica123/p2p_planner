import { NavLink, Outlet, useParams } from 'react-router-dom';
import { paths } from '@/app/router/paths';
import { useAuthSession } from '@/app/providers/AuthSessionProvider';
import { useWorkspacesQuery } from '@/features/workspaces/hooks/useWorkspaces';
import { useBoardsQuery } from '@/features/boards/hooks/useBoards';
import { LoadingState } from '@/shared/ui/LoadingState';
import { ErrorState } from '@/shared/ui/ErrorState';
import { Button } from '@/shared/ui/Button';

export function MainLayout() {
  const { workspaceId, boardId } = useParams();
  const { user, signOutCurrent, signOutEverywhere } = useAuthSession();
  const workspacesQuery = useWorkspacesQuery();
  const boardsQuery = useBoardsQuery(workspaceId);

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="app-sidebar__brand">
          <NavLink to={paths.home} className="brand-link">
            P2P Planner
          </NavLink>
          <p className="brand-copy">Web client v0 alpha</p>
        </div>

        <section className="sidebar-section">
          <div className="sidebar-section__header">Workspace switcher</div>
          {workspacesQuery.isLoading ? (
            <LoadingState label="Загружаем workspace list…" compact />
          ) : workspacesQuery.isError ? (
            <ErrorState title="Не удалось загрузить workspaces" compact />
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

        <section className="sidebar-section">
          <div className="sidebar-section__header">Customization</div>
          <nav className="nav-list">
            <NavLink to={paths.userAppearance} className={({ isActive }) => `nav-list__item ${isActive ? 'is-active' : ''}`}>
              <span>User appearance</span>
              <span className="nav-list__meta">app</span>
            </NavLink>
            {workspaceId && boardId ? (
              <NavLink to={paths.boardAppearance(workspaceId, boardId)} className={({ isActive }) => `nav-list__item ${isActive ? 'is-active' : ''}`}>
                <span>Board appearance</span>
                <span className="nav-list__meta">board</span>
              </NavLink>
            ) : null}
          </nav>
        </section>

        {workspaceId ? (
          <section className="sidebar-section sidebar-section--flex">
            <div className="sidebar-section__header">Boards in workspace</div>
            {boardsQuery.isLoading ? (
              <LoadingState label="Загружаем boards…" compact />
            ) : boardsQuery.isError ? (
              <ErrorState title="Не удалось загрузить boards" compact />
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
            <h1 className="topbar__title">P2P Planner: secured session baseline</h1>
            <p className="topbar__subtitle">Auth теперь идет через session/refresh flow, а доступ к API больше не строится вокруг X-User-Id.</p>
          </div>

          <div className="topbar__controls">
            <div className="topbar__hint">
              <strong>{user?.displayName || 'Unknown user'}</strong>
              <div>{user?.email}</div>
            </div>
            <Button onClick={() => void signOutCurrent()}>Sign out</Button>
            <Button variant="danger" onClick={() => void signOutEverywhere()}>
              Sign out all
            </Button>
          </div>
        </header>

        <main className="content-area">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
