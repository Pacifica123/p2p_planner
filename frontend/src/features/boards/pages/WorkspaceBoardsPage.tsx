import { FormEvent, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { paths } from '@/app/router/paths';
import { useWorkspacesQuery } from '@/features/workspaces/hooks/useWorkspaces';
import { useArchiveBoardMutation, useBoardsQuery, useCreateBoardMutation, useUpdateBoardMutation } from '@/features/boards/hooks/useBoards';
import { Button } from '@/shared/ui/Button';
import { EmptyState } from '@/shared/ui/EmptyState';
import { ErrorState } from '@/shared/ui/ErrorState';
import { TextAreaField, TextField } from '@/shared/ui/Field';
import { LoadingState } from '@/shared/ui/LoadingState';
import { Badge } from '@/shared/ui/Badge';
import { formatDateTime } from '@/shared/lib/date';

export function WorkspaceBoardsPage() {
  const navigate = useNavigate();
  const { workspaceId } = useParams();
  const workspacesQuery = useWorkspacesQuery();
  const boardsQuery = useBoardsQuery(workspaceId);
  const createBoardMutation = useCreateBoardMutation(workspaceId);
  const updateBoardMutation = useUpdateBoardMutation(workspaceId);
  const archiveBoardMutation = useArchiveBoardMutation(workspaceId);

  const workspace = useMemo(
    () => workspacesQuery.data?.items.find((item) => item.id === workspaceId),
    [workspaceId, workspacesQuery.data?.items],
  );

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');

  function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !name.trim()) return;
    createBoardMutation.mutate(
      { name: name.trim(), description: description.trim() || undefined },
      {
        onSuccess: (board) => {
          setName('');
          setDescription('');
          navigate(paths.board(workspaceId, board.id));
        },
      },
    );
  }

  async function handleRename(boardId: string, currentName: string) {
    const next = window.prompt('Новое название board', currentName)?.trim();
    if (!next || next === currentName) return;
    await updateBoardMutation.mutateAsync({ boardId, input: { name: next } });
  }

  async function handleArchive(boardId: string, boardName: string) {
    if (!window.confirm(`Архивировать board «${boardName}»?`)) return;
    await archiveBoardMutation.mutateAsync(boardId);
  }

  if (!workspaceId) {
    return <ErrorState title="Workspace не выбран" description="Выбери workspace в sidebar." />;
  }

  return (
    <div className="page-shell">
      <section className="page-header">
        <div>
          <h2>{workspace?.name || 'Boards'}</h2>
          <p className="muted">Boards list для выбранного workspace и быстрый переход к board screen.</p>
        </div>
        <div className="page-header__actions">
          <Button onClick={() => navigate(paths.home)}>К workspace list</Button>
        </div>
      </section>

      <section className="panel">
        <div className="entity-header">
          <div>
            <h3>Create board</h3>
            <p className="muted">Минимальное создание kanban board внутри выбранного workspace.</p>
          </div>
        </div>
        <form className="inline-form" onSubmit={handleCreate}>
          <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
            <TextField label="Название" value={name} onChange={(event) => setName(event.target.value)} placeholder="Например, Roadmap" />
            <TextAreaField label="Описание" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Необязательное описание board" />
          </div>
          <div className="inline-actions">
            <Button type="submit" variant="primary" disabled={createBoardMutation.isPending}>
              {createBoardMutation.isPending ? 'Создаем…' : 'Создать board'}
            </Button>
          </div>
        </form>
      </section>

      {boardsQuery.isLoading ? <LoadingState label="Загружаем boards…" /> : null}
      {boardsQuery.isError ? <ErrorState title="Не удалось загрузить boards" onRetry={() => void boardsQuery.refetch()} /> : null}

      {!boardsQuery.isLoading && !boardsQuery.isError ? (
        boardsQuery.data?.items.length ? (
          <div className="grid grid--cards">
            {boardsQuery.data.items.map((board) => (
              <article key={board.id} className="board-card">
                <div className="entity-header">
                  <div>
                    <h3>{board.name}</h3>
                    <p className="muted">{board.description || 'Без описания'}</p>
                  </div>
                  <div className="row-actions">
                    <Badge tone={board.boardType}>{board.boardType}</Badge>
                    {board.isArchived ? <Badge tone="warning">archived</Badge> : null}
                  </div>
                </div>

                <div className="grid" style={{ marginTop: 12 }}>
                  <div className="meta-line">updated: {formatDateTime(board.updatedAt)}</div>
                </div>

                <div className="page-header__actions" style={{ marginTop: 16 }}>
                  <Button variant="primary" onClick={() => navigate(paths.board(workspaceId, board.id))}>
                    Открыть board
                  </Button>
                  <Button onClick={() => void handleRename(board.id, board.name)} disabled={updateBoardMutation.isPending}>
                    Переименовать
                  </Button>
                  {!board.isArchived ? (
                    <Button variant="danger" onClick={() => void handleArchive(board.id, board.name)} disabled={archiveBoardMutation.isPending}>
                      Архивировать
                    </Button>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="В этом workspace пока нет boards" description="Создай первую board, чтобы перейти к columns и cards." />
        )
      ) : null}
    </div>
  );
}
