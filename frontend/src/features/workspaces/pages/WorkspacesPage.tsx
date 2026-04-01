import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { paths } from '@/app/router/paths';
import { useArchiveWorkspaceMutation, useCreateWorkspaceMutation, useUpdateWorkspaceMutation, useWorkspacesQuery } from '@/features/workspaces/hooks/useWorkspaces';
import { Button } from '@/shared/ui/Button';
import { EmptyState } from '@/shared/ui/EmptyState';
import { ErrorState } from '@/shared/ui/ErrorState';
import { TextAreaField, TextField, SelectField } from '@/shared/ui/Field';
import { LoadingState } from '@/shared/ui/LoadingState';
import { Badge } from '@/shared/ui/Badge';
import { formatDateTime } from '@/shared/lib/date';
import { ApiError } from '@/shared/api/errors';

function getErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return fallback;
}

export function WorkspacesPage() {
  const navigate = useNavigate();
  const workspacesQuery = useWorkspacesQuery();
  const createWorkspaceMutation = useCreateWorkspaceMutation();
  const updateWorkspaceMutation = useUpdateWorkspaceMutation();
  const archiveWorkspaceMutation = useArchiveWorkspaceMutation();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [visibility, setVisibility] = useState<'private' | 'shared'>('private');

  function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!name.trim()) return;
    createWorkspaceMutation.mutate(
      {
        name: name.trim(),
        description: description.trim() || undefined,
        visibility,
      },
      {
        onSuccess: (workspace) => {
          setName('');
          setDescription('');
          setVisibility('private');
          navigate(paths.workspaceBoards(workspace.id));
        },
      },
    );
  }

  async function handleRename(workspaceId: string, currentName: string) {
    const next = window.prompt('Новое название workspace', currentName)?.trim();
    if (!next || next === currentName) return;
    await updateWorkspaceMutation.mutateAsync({ workspaceId, input: { name: next } });
  }

  async function handleArchive(workspaceId: string, nameValue: string) {
    if (!window.confirm(`Архивировать workspace «${nameValue}»?`)) return;
    await archiveWorkspaceMutation.mutateAsync(workspaceId);
  }

  return (
    <div className="page-shell">
      <section className="page-header">
        <div>
          <h2>Workspace list / switcher</h2>
          <p className="muted">Основная точка входа в подтвержденный core flow. Отсюда создаются и выбираются workspaces.</p>
        </div>
      </section>

      <section className="panel">
        <div className="entity-header">
          <div>
            <h3>Create workspace</h3>
            <p className="muted">Минимальный happy-path поверх текущего backend CRUD.</p>
          </div>
        </div>

        <form className="inline-form" onSubmit={handleCreate}>
          <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))' }}>
            <TextField label="Название" value={name} onChange={(event) => setName(event.target.value)} placeholder="Например, Personal" />
            <SelectField label="Visibility" value={visibility} onChange={(event) => setVisibility(event.target.value as 'private' | 'shared')}>
              <option value="private">private</option>
              <option value="shared">shared</option>
            </SelectField>
          </div>
          <TextAreaField label="Описание" value={description} onChange={(event) => setDescription(event.target.value)} placeholder="Короткое описание workspace" />
          <div className="inline-actions">
            <Button type="submit" variant="primary" disabled={createWorkspaceMutation.isPending}>
              {createWorkspaceMutation.isPending ? 'Создаем…' : 'Создать workspace'}
            </Button>
          </div>
          {createWorkspaceMutation.isError ? (
            <ErrorState compact title="Не удалось создать workspace" description={getErrorMessage(createWorkspaceMutation.error, 'Проверь backend и введенные данные.')} />
          ) : null}
        </form>
      </section>

      {workspacesQuery.isLoading ? <LoadingState label="Загружаем workspaces…" /> : null}
      {workspacesQuery.isError ? (
        <ErrorState
          title="Не удалось загрузить список workspaces"
          description={getErrorMessage(workspacesQuery.error, 'Попробуй обновить данные или проверь backend.')}
          onRetry={() => void workspacesQuery.refetch()}
        />
      ) : null}

      {!workspacesQuery.isLoading && !workspacesQuery.isError ? (
        workspacesQuery.data?.items.length ? (
          <div className="grid grid--cards">
            {workspacesQuery.data.items.map((workspace) => (
              <article key={workspace.id} className="workspace-card">
                <div className="entity-header">
                  <div>
                    <h3>{workspace.name}</h3>
                    <p className="muted">{workspace.description || 'Без описания'}</p>
                  </div>
                  <div className="row-actions">
                    <Badge tone={workspace.visibility}>{workspace.visibility}</Badge>
                    {workspace.isArchived ? <Badge tone="warning">archived</Badge> : null}
                  </div>
                </div>

                <div className="grid" style={{ marginTop: 12 }}>
                  <div className="meta-line">updated: {formatDateTime(workspace.updatedAt)}</div>
                  <div className="meta-line">members: {workspace.memberCount ?? 0}</div>
                </div>

                <div className="page-header__actions" style={{ marginTop: 16 }}>
                  <Button variant="primary" onClick={() => navigate(paths.workspaceBoards(workspace.id))}>
                    Открыть boards
                  </Button>
                  <Button onClick={() => void handleRename(workspace.id, workspace.name)} disabled={updateWorkspaceMutation.isPending}>
                    Переименовать
                  </Button>
                  {!workspace.isArchived ? (
                    <Button variant="danger" onClick={() => void handleArchive(workspace.id, workspace.name)} disabled={archiveWorkspaceMutation.isPending}>
                      Архивировать
                    </Button>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState title="Пока нет ни одного workspace" description="Создай первый workspace, чтобы перейти к boards, columns и cards." />
        )
      ) : null}
    </div>
  );
}
