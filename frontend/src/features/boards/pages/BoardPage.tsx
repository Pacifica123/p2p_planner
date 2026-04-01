import { FormEvent, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { paths } from '@/app/router/paths';
import { ActivityFeed } from '@/features/activity/components/ActivityFeed';
import { useBoardActivityQuery } from '@/features/activity/hooks/useActivity';
import { useBoardQuery, useUpdateBoardMutation } from '@/features/boards/hooks/useBoards';
import { useColumnsQuery, useCreateColumnMutation, useDeleteColumnMutation, useUpdateColumnMutation } from '@/features/columns/hooks/useColumns';
import { CardDetailsDrawer } from '@/features/cards/components/CardDetailsDrawer';
import { useCardsQuery, useCreateCardMutation } from '@/features/cards/hooks/useCards';
import type { BoardColumn, Card } from '@/shared/types/api';
import { Button } from '@/shared/ui/Button';
import { Badge } from '@/shared/ui/Badge';
import { EmptyState } from '@/shared/ui/EmptyState';
import { ErrorState } from '@/shared/ui/ErrorState';
import { TextField } from '@/shared/ui/Field';
import { LoadingState } from '@/shared/ui/LoadingState';
import { formatDateTime } from '@/shared/lib/date';

const statusTone: Record<string, string> = {
  todo: 'default',
  in_progress: 'in_progress',
  blocked: 'urgent',
  done: 'done',
};

const priorityTone: Record<string, string> = {
  low: 'low',
  medium: 'medium',
  high: 'high',
  urgent: 'urgent',
};

function CreateCardInlineForm({ columnId, boardId }: { columnId: string; boardId: string }) {
  const createCardMutation = useCreateCardMutation(boardId);
  const [title, setTitle] = useState('');

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!title.trim()) return;
    createCardMutation.mutate(
      { title: title.trim(), columnId },
      {
        onSuccess: () => setTitle(''),
      },
    );
  }

  return (
    <form className="inline-form" onSubmit={handleSubmit}>
      <div className="inline-form__row">
        <input
          className="field__input"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="Новая карточка"
        />
        <Button type="submit" disabled={createCardMutation.isPending}>
          +
        </Button>
      </div>
    </form>
  );
}

export function BoardPage() {
  const navigate = useNavigate();
  const { workspaceId, boardId } = useParams();
  const [, setSearchParams] = useSearchParams();

  const boardQuery = useBoardQuery(boardId);
  const columnsQuery = useColumnsQuery(boardId);
  const cardsQuery = useCardsQuery(boardId);
  const boardActivityQuery = useBoardActivityQuery(boardId);
  const createColumnMutation = useCreateColumnMutation(boardId);
  const updateColumnMutation = useUpdateColumnMutation(boardId);
  const deleteColumnMutation = useDeleteColumnMutation(boardId);
  const updateBoardMutation = useUpdateBoardMutation(workspaceId, boardId);

  const [newColumnName, setNewColumnName] = useState('');

  const groupedCards = useMemo(() => {
    const map = new Map<string, Card[]>();
    (columnsQuery.data?.items || []).forEach((column) => map.set(column.id, []));
    (cardsQuery.data?.items || []).forEach((card) => {
      const items = map.get(card.columnId) || [];
      items.push(card);
      map.set(card.columnId, items);
    });
    return map;
  }, [cardsQuery.data, columnsQuery.data]);

  function handleCreateColumn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!newColumnName.trim()) return;
    createColumnMutation.mutate(
      { name: newColumnName.trim() },
      {
        onSuccess: () => setNewColumnName(''),
      },
    );
  }

  async function handleRenameColumn(column: BoardColumn) {
    const next = window.prompt('Новое название column', column.name)?.trim();
    if (!next || next === column.name) return;
    await updateColumnMutation.mutateAsync({ columnId: column.id, input: { name: next } });
  }

  async function handleDeleteColumn(column: BoardColumn) {
    if (!window.confirm(`Удалить column «${column.name}»?`)) return;
    await deleteColumnMutation.mutateAsync(column.id);
  }

  async function handleRenameBoard() {
    if (!boardQuery.data) return;
    const next = window.prompt('Новое название board', boardQuery.data.name)?.trim();
    if (!next || next === boardQuery.data.name) return;
    await updateBoardMutation.mutateAsync({ input: { name: next } });
  }

  if (!boardId || !workspaceId) {
    return <ErrorState title="Board не выбрана" description="Выбери board из workspace." />;
  }

  const isLoading = boardQuery.isLoading || columnsQuery.isLoading || cardsQuery.isLoading;
  const isError = boardQuery.isError || columnsQuery.isError || cardsQuery.isError;

  return (
    <div className="page-shell">
      <section className="page-header">
        <div>
          <h2>{boardQuery.data?.name || 'Board screen'}</h2>
          <p className="muted">Columns + cards + card details + board activity поверх уже подтвержденного backend happy-path.</p>
        </div>
        <div className="page-header__actions">
          <Button onClick={() => navigate(paths.workspaceBoards(workspaceId))}>К boards list</Button>
          <Button onClick={() => void handleRenameBoard()} disabled={updateBoardMutation.isPending || !boardQuery.data}>Переименовать board</Button>
          <Button onClick={() => void Promise.all([boardQuery.refetch(), columnsQuery.refetch(), cardsQuery.refetch(), boardActivityQuery.refetch()])}>Обновить</Button>
        </div>
      </section>

      {isLoading ? <LoadingState label="Загружаем board surface…" /> : null}
      {isError ? <ErrorState title="Не удалось собрать board surface" description="Проверь backend и доступность выбранной board." /> : null}

      {!isLoading && !isError ? (
        <div className="board-layout">
          <div className="grid">
            <section className="panel">
              <div className="entity-header">
                <div>
                  <h3>Board summary</h3>
                  <p className="muted">{boardQuery.data?.description || 'Без описания'}</p>
                </div>
                <div className="row-actions">
                  <Badge tone="kanban">kanban</Badge>
                  <Badge tone="default">columns: {columnsQuery.data?.items.length ?? 0}</Badge>
                  <Badge tone="default">cards: {cardsQuery.data?.items.length ?? 0}</Badge>
                </div>
              </div>
              <div className="grid" style={{ marginTop: 14 }}>
                <div className="meta-line">updated: {formatDateTime(boardQuery.data?.updatedAt)}</div>
              </div>
            </section>

            <section className="panel">
              <div className="entity-header">
                <div>
                  <h3>Create column</h3>
                  <p className="muted">Минимальный add-column UX.</p>
                </div>
              </div>
              <form className="inline-form__row" onSubmit={handleCreateColumn}>
                <TextField label="Название колонки" value={newColumnName} onChange={(event) => setNewColumnName(event.target.value)} placeholder="Например, Todo" />
                <Button type="submit" variant="primary" disabled={createColumnMutation.isPending}>
                  {createColumnMutation.isPending ? 'Создаем…' : 'Добавить'}
                </Button>
              </form>
            </section>

            {(columnsQuery.data?.items.length ?? 0) ? (
              <div className="columns-strip">
                {columnsQuery.data?.items.map((column) => {
                  const cards = groupedCards.get(column.id) || [];
                  return (
                    <section key={column.id} className="column-card">
                      <div className="column-card__header">
                        <div>
                          <h3>{column.name}</h3>
                          <p className="muted">cards: {cards.length}</p>
                        </div>
                        <div className="row-actions">
                          <Button onClick={() => void handleRenameColumn(column)} disabled={updateColumnMutation.isPending}>Edit</Button>
                          <Button variant="danger" onClick={() => void handleDeleteColumn(column)} disabled={deleteColumnMutation.isPending}>Delete</Button>
                        </div>
                      </div>

                      <CreateCardInlineForm columnId={column.id} boardId={boardId} />

                      {cards.length ? (
                        <div className="card-list">
                          {cards.map((card) => (
                            <article
                              key={card.id}
                              className="card-tile"
                              onClick={() => setSearchParams((prev) => {
                                const next = new URLSearchParams(prev);
                                next.set('card', card.id);
                                return next;
                              })}
                            >
                              <div className="card-tile__header">
                                <strong>{card.title}</strong>
                                {card.isArchived ? <Badge tone="warning">archived</Badge> : null}
                              </div>
                              {card.description ? <p className="muted">{card.description}</p> : null}
                              <div className="card-tile__footer">
                                {card.status ? <Badge tone={statusTone[card.status] || 'default'}>{card.status}</Badge> : null}
                                {card.priority ? <Badge tone={priorityTone[card.priority] || 'default'}>{card.priority}</Badge> : null}
                              </div>
                            </article>
                          ))}
                        </div>
                      ) : (
                        <EmptyState title="Здесь пока нет карточек" compact description="Добавь card прямо внутри этой колонки." />
                      )}
                    </section>
                  );
                })}
              </div>
            ) : (
              <EmptyState title="У board пока нет колонок" description="Сначала создай колонку, после этого появится место для карточек." />
            )}
          </div>

          <section className="panel">
            <div className="entity-header">
              <div>
                <h3>Board activity</h3>
                <p className="muted">Последние user-facing события по board.</p>
              </div>
            </div>
            {boardActivityQuery.isLoading ? <LoadingState label="Загружаем activity…" compact /> : null}
            {boardActivityQuery.isError ? <ErrorState title="Не удалось загрузить board activity" compact /> : null}
            {boardActivityQuery.data ? <ActivityFeed items={boardActivityQuery.data.items} emptyTitle="История board пока пустая" /> : null}
          </section>
        </div>
      ) : null}

      <CardDetailsDrawer />
    </div>
  );
}
