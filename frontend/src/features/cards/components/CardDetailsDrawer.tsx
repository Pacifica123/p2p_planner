import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useCardActivityQuery } from '@/features/activity/hooks/useActivity';
import { ActivityFeed } from '@/features/activity/components/ActivityFeed';
import {
  useArchiveCardMutation,
  useCardQuery,
  useDeleteCardMutation,
  useMoveCardMutation,
  useUnarchiveCardMutation,
  useUpdateCardMutation,
} from '@/features/cards/hooks/useCards';
import { useColumnsQuery } from '@/features/columns/hooks/useColumns';
import { Button } from '@/shared/ui/Button';
import { EmptyState } from '@/shared/ui/EmptyState';
import { ErrorState } from '@/shared/ui/ErrorState';
import { SelectField, TextAreaField, TextField } from '@/shared/ui/Field';
import { LoadingState } from '@/shared/ui/LoadingState';
import { formatDateTime } from '@/shared/lib/date';

const STATUS_OPTIONS = [
  { value: '', label: '—' },
  { value: 'todo', label: 'todo' },
  { value: 'in_progress', label: 'in_progress' },
  { value: 'blocked', label: 'blocked' },
  { value: 'done', label: 'done' },
];

const PRIORITY_OPTIONS = [
  { value: '', label: '—' },
  { value: 'low', label: 'low' },
  { value: 'medium', label: 'medium' },
  { value: 'high', label: 'high' },
  { value: 'urgent', label: 'urgent' },
];

export function CardDetailsDrawer() {
  const navigate = useNavigate();
  const { boardId, workspaceId } = useParams();
  const [searchParams] = useSearchParams();
  const cardId = searchParams.get('card');

  const cardQuery = useCardQuery(cardId || undefined);
  const columnsQuery = useColumnsQuery(boardId);
  const activityQuery = useCardActivityQuery(cardId || undefined);
  const updateCardMutation = useUpdateCardMutation(boardId, cardId || undefined);
  const moveCardMutation = useMoveCardMutation(boardId, cardId || undefined);
  const archiveCardMutation = useArchiveCardMutation(boardId, cardId || undefined);
  const unarchiveCardMutation = useUnarchiveCardMutation(boardId, cardId || undefined);
  const deleteCardMutation = useDeleteCardMutation(boardId, cardId || undefined);

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [status, setStatus] = useState('');
  const [priority, setPriority] = useState('');
  const [columnId, setColumnId] = useState('');

  useEffect(() => {
    const card = cardQuery.data;
    if (!card) return;
    setTitle(card.title);
    setDescription(card.description || '');
    setStatus(card.status || '');
    setPriority(card.priority || '');
    setColumnId(card.columnId);
  }, [cardQuery.data]);

  const columnOptions = useMemo(() => columnsQuery.data?.items ?? [], [columnsQuery.data?.items]);

  function closeDrawer() {
    navigate(workspaceId && boardId ? `/workspaces/${workspaceId}/boards/${boardId}` : '/', { replace: true });
  }

  async function handleSave() {
    if (!cardQuery.data) return;

    await updateCardMutation.mutateAsync({
      title: title.trim(),
      description: description.trim() || null,
      status: status || null,
      priority: priority || null,
    });

    if (columnId && columnId !== cardQuery.data.columnId) {
      await moveCardMutation.mutateAsync(columnId);
    }
  }

  async function handleArchiveToggle() {
    if (!cardQuery.data) return;
    if (cardQuery.data.isArchived) {
      await unarchiveCardMutation.mutateAsync();
      return;
    }
    await archiveCardMutation.mutateAsync();
  }

  async function handleDelete() {
    if (!cardQuery.data) return;
    if (!window.confirm(`Удалить карточку «${cardQuery.data.title}»?`)) return;
    await deleteCardMutation.mutateAsync();
    closeDrawer();
  }

  if (!cardId) return null;

  return (
    <div className="drawer" onClick={closeDrawer}>
      <aside className="drawer__surface" onClick={(event) => event.stopPropagation()}>
        <div className="drawer__header">
          <div>
            <h3>Card details</h3>
            <p className="muted">Edit / move / archive / delete поверх стабильного card CRUD.</p>
          </div>
          <Button variant="ghost" onClick={closeDrawer}>
            Закрыть
          </Button>
        </div>

        {cardQuery.isLoading ? <LoadingState label="Загружаем card detail…" /> : null}
        {cardQuery.isError ? <ErrorState title="Не удалось загрузить карточку" onRetry={() => void cardQuery.refetch()} /> : null}

        {cardQuery.data ? (
          <>
            <div className="grid" style={{ gap: 14 }}>
              <TextField label="Title" value={title} onChange={(event) => setTitle(event.target.value)} />
              <TextAreaField label="Description" value={description} onChange={(event) => setDescription(event.target.value)} />
              <SelectField label="Status" value={status} onChange={(event) => setStatus(event.target.value)}>
                {STATUS_OPTIONS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </SelectField>
              <SelectField label="Priority" value={priority} onChange={(event) => setPriority(event.target.value)}>
                {PRIORITY_OPTIONS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </SelectField>
              <SelectField label="Column" value={columnId} onChange={(event) => setColumnId(event.target.value)}>
                {columnOptions.map((column) => (
                  <option key={column.id} value={column.id}>
                    {column.name}
                  </option>
                ))}
              </SelectField>
            </div>

            <div className="grid">
              <div className="key-value"><span className="muted">Created</span><span>{formatDateTime(cardQuery.data.createdAt)}</span></div>
              <div className="key-value"><span className="muted">Updated</span><span>{formatDateTime(cardQuery.data.updatedAt)}</span></div>
              <div className="key-value"><span className="muted">Archived</span><span>{cardQuery.data.isArchived ? 'yes' : 'no'}</span></div>
            </div>

            <div className="inline-actions">
              <Button variant="primary" onClick={() => void handleSave()} disabled={updateCardMutation.isPending || moveCardMutation.isPending}>
                {updateCardMutation.isPending || moveCardMutation.isPending ? 'Сохраняем…' : 'Сохранить'}
              </Button>
              <Button onClick={() => void handleArchiveToggle()} disabled={archiveCardMutation.isPending || unarchiveCardMutation.isPending}>
                {cardQuery.data.isArchived ? 'Разархивировать' : 'Архивировать'}
              </Button>
              <Button variant="danger" onClick={() => void handleDelete()} disabled={deleteCardMutation.isPending}>
                Удалить
              </Button>
            </div>

            <section className="panel">
              <div className="entity-header">
                <div>
                  <h4>Card history</h4>
                  <p className="muted">User-facing timeline из activity read-model.</p>
                </div>
              </div>
              {activityQuery.isLoading ? <LoadingState label="Загружаем card history…" compact /> : null}
              {activityQuery.isError ? <ErrorState title="Не удалось загрузить историю карточки" compact /> : null}
              {activityQuery.data ? <ActivityFeed items={activityQuery.data.items} emptyTitle="История карточки пока пустая" /> : null}
              {!activityQuery.isLoading && !activityQuery.isError && !activityQuery.data ? <EmptyState title="История карточки пока пустая" compact /> : null}
            </section>
          </>
        ) : null}
      </aside>
    </div>
  );
}
