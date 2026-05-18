import { FormEvent, useEffect, useMemo, useState } from 'react';
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
import {
  useCardChecklistsQuery,
  useCreateChecklistItemMutation,
  useCreateChecklistMutation,
  useDeleteChecklistItemMutation,
  useDeleteChecklistMutation,
  useUpdateChecklistItemMutation,
  useUpdateChecklistMutation,
} from '@/features/checklists/hooks/useChecklists';
import {
  useCardCommentsQuery,
  useCreateCommentMutation,
  useDeleteCommentMutation,
  useUpdateCommentMutation,
} from '@/features/comments/hooks/useComments';
import { useColumnsQuery } from '@/features/columns/hooks/useColumns';
import { useOptionalLocalFirstBoard } from '@/features/localFirst/context/LocalFirstBoardContext';
import { isLocalCardId, resolveLocalFirstCardId } from '@/features/localFirst/lib/localBoardStore';
import {
  useBoardLabelsQuery,
  useCreateBoardLabelMutation,
  useDeleteBoardLabelMutation,
  useReplaceCardLabelsMutation,
  useUpdateBoardLabelMutation,
} from '@/features/labels/hooks/useLabels';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { EmptyState } from '@/shared/ui/EmptyState';
import { ErrorState } from '@/shared/ui/ErrorState';
import { SelectField, TextAreaField, TextField } from '@/shared/ui/Field';
import { LoadingState } from '@/shared/ui/LoadingState';
import { formatDateTime } from '@/shared/lib/date';
import type { BoardLabel, CardPriority, CardStatus, Checklist, ChecklistItem, Comment } from '@/shared/types/api';

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
  const localFirst = useOptionalLocalFirstBoard();
  const effectiveCardId = cardId ? resolveLocalFirstCardId(cardId) : null;
  const cardQueryId = effectiveCardId && !isLocalCardId(effectiveCardId) ? effectiveCardId : undefined;

  const cardQuery = useCardQuery(cardQueryId || undefined);
  const columnsQuery = useColumnsQuery(boardId);
  const labelsQuery = useBoardLabelsQuery(boardId);
  const checklistsQuery = useCardChecklistsQuery(cardQueryId || undefined);
  const commentsQuery = useCardCommentsQuery(cardQueryId || undefined);
  const activityQuery = useCardActivityQuery(cardQueryId || undefined);
  const updateCardMutation = useUpdateCardMutation(boardId, cardQueryId || undefined);
  const moveCardMutation = useMoveCardMutation(boardId, cardQueryId || undefined);
  const archiveCardMutation = useArchiveCardMutation(boardId, cardQueryId || undefined);
  const unarchiveCardMutation = useUnarchiveCardMutation(boardId, cardQueryId || undefined);
  const deleteCardMutation = useDeleteCardMutation(boardId, cardQueryId || undefined);
  const createLabelMutation = useCreateBoardLabelMutation(boardId);
  const updateLabelMutation = useUpdateBoardLabelMutation(boardId);
  const deleteLabelMutation = useDeleteBoardLabelMutation(boardId);
  const replaceCardLabelsMutation = useReplaceCardLabelsMutation(boardId, cardQueryId || undefined);
  const createChecklistMutation = useCreateChecklistMutation(boardId, cardQueryId || undefined);
  const updateChecklistMutation = useUpdateChecklistMutation(boardId, cardQueryId || undefined);
  const deleteChecklistMutation = useDeleteChecklistMutation(boardId, cardQueryId || undefined);
  const createChecklistItemMutation = useCreateChecklistItemMutation(boardId, cardQueryId || undefined);
  const updateChecklistItemMutation = useUpdateChecklistItemMutation(boardId, cardQueryId || undefined);
  const deleteChecklistItemMutation = useDeleteChecklistItemMutation(boardId, cardQueryId || undefined);
  const createCommentMutation = useCreateCommentMutation(boardId, cardQueryId || undefined);
  const updateCommentMutation = useUpdateCommentMutation(boardId, cardQueryId || undefined);
  const deleteCommentMutation = useDeleteCommentMutation(boardId, cardQueryId || undefined);

  const localCard = useMemo(() => {
    if (!effectiveCardId || !localFirst || localFirst.boardId !== boardId) return undefined;
    return localFirst.cards.find((item) => item.id === effectiveCardId);
  }, [boardId, effectiveCardId, localFirst]);
  const card = localCard || cardQuery.data;
  const cardSyncStatus = card ? localFirst?.getEntityStatus('card', card.id)?.status ?? 'synced' : 'synced';
  const isLocalPendingCard = Boolean(card && isLocalCardId(card.id));

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [status, setStatus] = useState<CardStatus>(null);
  const [priority, setPriority] = useState<CardPriority>(null);
  const [columnId, setColumnId] = useState('');
  const [newLabelName, setNewLabelName] = useState('');
  const [newLabelColor, setNewLabelColor] = useState('#60a5fa');
  const [newChecklistTitle, setNewChecklistTitle] = useState('');
  const [newItemByChecklist, setNewItemByChecklist] = useState<Record<string, string>>({});
  const [newCommentBody, setNewCommentBody] = useState('');

  useEffect(() => {
    if (!card) return;
    setTitle(card.title);
    setDescription(card.description || '');
    setStatus(card.status || null);
    setPriority(card.priority || null);
    setColumnId(card.columnId);
  }, [card]);

  const columnOptions = useMemo(() => {
    if (localFirst && localFirst.boardId === boardId && localFirst.columns.length) {
      return localFirst.columns;
    }
    return columnsQuery.data?.items ?? [];
  }, [boardId, columnsQuery.data?.items, localFirst]);
  const selectedLabelIds = useMemo(() => card?.labelIds ?? [], [card?.labelIds]);

  useEffect(() => {
    if (!cardId || !effectiveCardId || cardId === effectiveCardId) return;
    const next = new URLSearchParams(searchParams);
    next.set('card', effectiveCardId);
    navigate({ search: next.toString() }, { replace: true });
  }, [cardId, effectiveCardId, navigate, searchParams]);

  function closeDrawer() {
    navigate(workspaceId && boardId ? `/workspaces/${workspaceId}/boards/${boardId}` : '/', { replace: true });
  }

  async function handleSave() {
    if (!card) return;

    const nextCardInput = {
      title: title.trim(),
      description: description.trim() || null,
      status: status || null,
      priority: priority || null,
    };

    if (localFirst && localFirst.boardId === boardId) {
      localFirst.enqueueUpdateCard(card.id, nextCardInput);
      if (columnId && columnId !== card.columnId) {
        localFirst.enqueueMoveCard(card.id, { targetColumnId: columnId });
      }
      return;
    }

    await updateCardMutation.mutateAsync(nextCardInput);

    if (columnId && columnId !== card.columnId) {
      await moveCardMutation.mutateAsync({ targetColumnId: columnId });
    }
  }

  async function handleArchiveToggle() {
    if (!card) return;
    if (card.isArchived) {
      await unarchiveCardMutation.mutateAsync();
      return;
    }
    await archiveCardMutation.mutateAsync();
  }

  async function handleDelete() {
    if (!card) return;
    if (!window.confirm(`Удалить карточку «${card.title}»?`)) return;
    await deleteCardMutation.mutateAsync();
    closeDrawer();
  }

  async function handleCreateLabel(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = newLabelName.trim();
    const color = newLabelColor.trim();
    if (!name || !color) return;
    await createLabelMutation.mutateAsync({ name, color });
    setNewLabelName('');
  }

  async function handleToggleLabel(labelId: string) {
    const nextLabelIds = selectedLabelIds.includes(labelId)
      ? selectedLabelIds.filter((current) => current !== labelId)
      : [...selectedLabelIds, labelId];
    await replaceCardLabelsMutation.mutateAsync(nextLabelIds);
  }

  async function handleRenameLabel(label: BoardLabel) {
    const nextName = window.prompt('Новое название label', label.name)?.trim();
    if (!nextName || nextName === label.name) return;
    await updateLabelMutation.mutateAsync({ labelId: label.id, input: { name: nextName } });
  }

  async function handleDeleteLabel(label: BoardLabel) {
    if (!window.confirm(`Удалить label «${label.name}» и снять его со всех карточек?`)) return;
    await deleteLabelMutation.mutateAsync(label.id);
  }

  async function handleCreateChecklist(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const titleValue = newChecklistTitle.trim();
    if (!titleValue) return;
    await createChecklistMutation.mutateAsync({ title: titleValue });
    setNewChecklistTitle('');
  }

  async function handleRenameChecklist(checklist: Checklist) {
    const nextTitle = window.prompt('Новое название checklist', checklist.title)?.trim();
    if (!nextTitle || nextTitle === checklist.title) return;
    await updateChecklistMutation.mutateAsync({ checklistId: checklist.id, input: { title: nextTitle } });
  }

  async function handleDeleteChecklist(checklist: Checklist) {
    if (!window.confirm(`Удалить checklist «${checklist.title}»?`)) return;
    await deleteChecklistMutation.mutateAsync(checklist.id);
  }

  async function handleCreateChecklistItem(checklistId: string) {
    const titleValue = (newItemByChecklist[checklistId] || '').trim();
    if (!titleValue) return;
    await createChecklistItemMutation.mutateAsync({ checklistId, title: titleValue });
    setNewItemByChecklist((current) => ({ ...current, [checklistId]: '' }));
  }

  async function handleToggleChecklistItem(item: ChecklistItem) {
    await updateChecklistItemMutation.mutateAsync({ itemId: item.id, input: { isDone: !item.isDone } });
  }

  async function handleRenameChecklistItem(item: ChecklistItem) {
    const nextTitle = window.prompt('Новое название item', item.title)?.trim();
    if (!nextTitle || nextTitle === item.title) return;
    await updateChecklistItemMutation.mutateAsync({ itemId: item.id, input: { title: nextTitle } });
  }

  async function handleDeleteChecklistItem(item: ChecklistItem) {
    if (!window.confirm(`Удалить checklist item «${item.title}»?`)) return;
    await deleteChecklistItemMutation.mutateAsync(item.id);
  }

  async function handleCreateComment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const body = newCommentBody.trim();
    if (!body) return;
    await createCommentMutation.mutateAsync(body);
    setNewCommentBody('');
  }

  async function handleEditComment(comment: Comment) {
    const nextBody = window.prompt('Новый текст comment', comment.body)?.trim();
    if (!nextBody || nextBody === comment.body) return;
    await updateCommentMutation.mutateAsync({ commentId: comment.id, body: nextBody });
  }

  async function handleDeleteComment(comment: Comment) {
    if (!window.confirm('Удалить comment?')) return;
    await deleteCommentMutation.mutateAsync(comment.id);
  }

  if (!cardId) return null;

  return (
    <div className="drawer" onClick={closeDrawer}>
      <aside className="drawer__surface" onClick={(event) => event.stopPropagation()}>
        <div className="drawer__header">
          <div>
            <h3>Card details</h3>
            <p className="muted">Минимально полезная карточка: labels, checklists, comments и history.</p>
          </div>
          <Button variant="ghost" iconOnly onClick={closeDrawer} title="Закрыть" aria-label="Закрыть">
            ✕
          </Button>
        </div>

        {cardQuery.isLoading && !card ? <LoadingState label="Загружаем card detail…" /> : null}
        {cardQuery.isError && !card ? <ErrorState title="Не удалось загрузить карточку" onRetry={() => void cardQuery.refetch()} /> : null}

        {card ? (
          <>
            <div className="grid" style={{ gap: 14 }}>
              <TextField label="Title" value={title} onChange={(event) => setTitle(event.target.value)} />
              <TextAreaField label="Description" value={description} onChange={(event) => setDescription(event.target.value)} />
              <SelectField label="Status" value={status ?? ''} onChange={(event) => setStatus(event.target.value ? (event.target.value as CardStatus) : null)}>
                {STATUS_OPTIONS.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </SelectField>
              <SelectField label="Priority" value={priority ?? ''} onChange={(event) => setPriority(event.target.value ? (event.target.value as CardPriority) : null)}>
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
              <div className="key-value"><span className="muted">Created</span><span>{formatDateTime(card.createdAt)}</span></div>
              <div className="key-value"><span className="muted">Updated</span><span>{formatDateTime(card.updatedAt)}</span></div>
              <div className="key-value"><span className="muted">Archived</span><span>{card.isArchived ? 'yes' : 'no'}</span></div>
              <div className="key-value"><span className="muted">Local sync</span><span><Badge tone={cardSyncStatus === 'failed' ? 'urgent' : cardSyncStatus === 'pending' ? 'warning' : 'done'}>{cardSyncStatus === 'pending' ? 'saved locally' : cardSyncStatus === 'failed' ? 'sync failed' : 'synced'}</Badge></span></div>
            </div>

            <div className="inline-actions">
              <Button variant="primary" iconOnly onClick={() => void handleSave()} disabled={updateCardMutation.isPending || moveCardMutation.isPending} title="Сохранить карточку" aria-label="Сохранить карточку">
                {updateCardMutation.isPending || moveCardMutation.isPending ? '…' : '💾'}
              </Button>
              <Button iconOnly onClick={() => void handleArchiveToggle()} disabled={archiveCardMutation.isPending || unarchiveCardMutation.isPending || isLocalPendingCard} title={card.isArchived ? 'Разархивировать карточку' : 'Архивировать карточку'} aria-label={card.isArchived ? 'Разархивировать карточку' : 'Архивировать карточку'}>
                {archiveCardMutation.isPending || unarchiveCardMutation.isPending ? '…' : card.isArchived ? '📤' : '📦'}
              </Button>
              <Button variant="danger" iconOnly onClick={() => void handleDelete()} disabled={deleteCardMutation.isPending || isLocalPendingCard} title="Удалить карточку" aria-label="Удалить карточку">
                {deleteCardMutation.isPending ? '…' : '🗑️'}
              </Button>
            </div>

            {isLocalPendingCard ? (
              <div className="inline-banner">
                <strong>Card saved locally.</strong>
                <span>Labels, checklists, comments and server history will unlock after this new card syncs.</span>
              </div>
            ) : null}

            {!isLocalPendingCard ? (
              <>
                <section className="panel">
                  <div className="entity-header">
                    <div>
                      <h4>Labels</h4>
                  <p className="muted">Создать label на board и назначить/снять его с карточки.</p>
                </div>
              </div>
              <form className="inline-form__row inline-form__row--tight" onSubmit={handleCreateLabel}>
                <TextField label="Label" value={newLabelName} onChange={(event) => setNewLabelName(event.target.value)} placeholder="Например, bug" />
                <TextField label="Color" value={newLabelColor} onChange={(event) => setNewLabelColor(event.target.value)} placeholder="#60a5fa" />
                <Button type="submit" variant="primary" disabled={createLabelMutation.isPending}>＋</Button>
              </form>
              {labelsQuery.isLoading ? <LoadingState label="Загружаем labels…" compact /> : null}
              {labelsQuery.isError ? <ErrorState title="Не удалось загрузить labels" compact /> : null}
              {labelsQuery.data?.items.length ? (
                <div className="grid" style={{ gap: 8 }}>
                  {labelsQuery.data.items.map((label) => {
                    const isChecked = selectedLabelIds.includes(label.id);
                    return (
                      <div key={label.id} className="toggle-row">
                        <label className="inline-actions" style={{ alignItems: 'center' }}>
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={() => void handleToggleLabel(label.id)}
                            disabled={replaceCardLabelsMutation.isPending}
                          />
                          <span className="badge" style={{ borderColor: label.color }}>
                            {label.name}
                          </span>
                        </label>
                        <div className="row-actions">
                          <Button iconOnly onClick={() => void handleRenameLabel(label)} disabled={updateLabelMutation.isPending} title="Переименовать label" aria-label="Переименовать label">✏️</Button>
                          <Button variant="danger" iconOnly onClick={() => void handleDeleteLabel(label)} disabled={deleteLabelMutation.isPending} title="Удалить label" aria-label="Удалить label">🗑️</Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : null}
              {!labelsQuery.isLoading && !labelsQuery.isError && !labelsQuery.data?.items.length ? <EmptyState title="Labels пока нет" compact /> : null}
            </section>

            <section className="panel">
              <div className="entity-header">
                <div>
                  <h4>Checklists</h4>
                  <p className="muted">Минимальный checklist flow: создать список, добавить item, отметить done/undone, удалить item.</p>
                </div>
              </div>
              <form className="inline-form__row inline-form__row--tight" onSubmit={handleCreateChecklist}>
                <TextField label="New checklist" value={newChecklistTitle} onChange={(event) => setNewChecklistTitle(event.target.value)} placeholder="Acceptance criteria" />
                <Button type="submit" variant="primary" disabled={createChecklistMutation.isPending}>＋</Button>
              </form>
              {checklistsQuery.isLoading ? <LoadingState label="Загружаем checklists…" compact /> : null}
              {checklistsQuery.isError ? <ErrorState title="Не удалось загрузить checklists" compact /> : null}
              {checklistsQuery.data?.items.length ? (
                <div className="grid" style={{ gap: 14 }}>
                  {checklistsQuery.data.items.map((checklist) => (
                    <div key={checklist.id} className="activity-item">
                      <div className="entity-header">
                        <div>
                          <strong>{checklist.title}</strong>
                          <p className="muted">{checklist.items.filter((item) => item.isDone).length}/{checklist.items.length} done</p>
                        </div>
                        <div className="row-actions">
                          <Button iconOnly onClick={() => void handleRenameChecklist(checklist)} disabled={updateChecklistMutation.isPending} title="Переименовать checklist" aria-label="Переименовать checklist">✏️</Button>
                          <Button variant="danger" iconOnly onClick={() => void handleDeleteChecklist(checklist)} disabled={deleteChecklistMutation.isPending} title="Удалить checklist" aria-label="Удалить checklist">🗑️</Button>
                        </div>
                      </div>
                      <div className="grid" style={{ gap: 8 }}>
                        {checklist.items.map((item) => (
                          <div key={item.id} className="toggle-row">
                            <label className="inline-actions" style={{ alignItems: 'center' }}>
                              <input
                                type="checkbox"
                                checked={item.isDone}
                                onChange={() => void handleToggleChecklistItem(item)}
                                disabled={updateChecklistItemMutation.isPending}
                              />
                              <span style={{ textDecoration: item.isDone ? 'line-through' : undefined }}>{item.title}</span>
                            </label>
                            <div className="row-actions">
                              <Button iconOnly onClick={() => void handleRenameChecklistItem(item)} disabled={updateChecklistItemMutation.isPending} title="Переименовать item" aria-label="Переименовать item">✏️</Button>
                              <Button variant="danger" iconOnly onClick={() => void handleDeleteChecklistItem(item)} disabled={deleteChecklistItemMutation.isPending} title="Удалить item" aria-label="Удалить item">🗑️</Button>
                            </div>
                          </div>
                        ))}
                        <div className="inline-form__row inline-form__row--tight">
                          <TextField
                            label="New item"
                            value={newItemByChecklist[checklist.id] || ''}
                            onChange={(event) => setNewItemByChecklist((current) => ({ ...current, [checklist.id]: event.target.value }))}
                            placeholder="Сделать smoke"
                          />
                          <Button type="button" variant="primary" onClick={() => void handleCreateChecklistItem(checklist.id)} disabled={createChecklistItemMutation.isPending}>＋</Button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : null}
              {!checklistsQuery.isLoading && !checklistsQuery.isError && !checklistsQuery.data?.items.length ? <EmptyState title="Checklists пока нет" compact /> : null}
            </section>

            <section className="panel">
              <div className="entity-header">
                <div>
                  <h4>Comments</h4>
                  <p className="muted">Comments timeline внутри карточки.</p>
                </div>
              </div>
              <form className="grid" style={{ gap: 10 }} onSubmit={handleCreateComment}>
                <TextAreaField label="New comment" value={newCommentBody} onChange={(event) => setNewCommentBody(event.target.value)} placeholder="Оставить заметку по карточке…" />
                <Button type="submit" variant="primary" disabled={createCommentMutation.isPending}>＋ Comment</Button>
              </form>
              {commentsQuery.isLoading ? <LoadingState label="Загружаем comments…" compact /> : null}
              {commentsQuery.isError ? <ErrorState title="Не удалось загрузить comments" compact /> : null}
              {commentsQuery.data?.items.length ? (
                <div className="grid" style={{ gap: 10 }}>
                  {commentsQuery.data.items.map((comment) => (
                    <article key={comment.id} className="activity-item">
                      <div className="activity-item__header">
                        <div>
                          <strong>Comment</strong>
                          <p className="muted">{formatDateTime(comment.createdAt)}{comment.editedAt ? ` · edited ${formatDateTime(comment.editedAt)}` : ''}</p>
                        </div>
                        <div className="row-actions">
                          <Button iconOnly onClick={() => void handleEditComment(comment)} disabled={updateCommentMutation.isPending} title="Редактировать comment" aria-label="Редактировать comment">✏️</Button>
                          <Button variant="danger" iconOnly onClick={() => void handleDeleteComment(comment)} disabled={deleteCommentMutation.isPending} title="Удалить comment" aria-label="Удалить comment">🗑️</Button>
                        </div>
                      </div>
                      <p>{comment.body}</p>
                    </article>
                  ))}
                </div>
              ) : null}
              {!commentsQuery.isLoading && !commentsQuery.isError && !commentsQuery.data?.items.length ? <EmptyState title="Comments пока нет" compact /> : null}
            </section>

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
          </>
        ) : null}
      </aside>
    </div>
  );
}
