import { DragEvent, FormEvent, ReactNode, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { paths } from '@/app/router/paths';
import { ActivityFeed } from '@/features/activity/components/ActivityFeed';
import { useBoardActivityQuery } from '@/features/activity/hooks/useActivity';
import { useBoardAppearanceQuery } from '@/features/appearance/hooks/useAppearance';
import { useAppearance } from '@/app/providers/AppearanceProvider';
import { useBoardQuery, useUpdateBoardMutation } from '@/features/boards/hooks/useBoards';
import {
  buildColumnReorderItems,
  CardMoveIntent,
  getDropPositionValue,
  groupCardsByColumn,
  reorderBoardPreview,
  sortCardsByPosition,
} from '@/features/boards/lib/cardDnd';
import { useColumnsQuery, useCreateColumnMutation, useDeleteColumnMutation, useUpdateColumnMutation } from '@/features/columns/hooks/useColumns';
import { CardDetailsDrawer } from '@/features/cards/components/CardDetailsDrawer';
import { useCardsQuery, useCreateCardMutation, useMoveCardMutation, useReorderColumnCardsMutation } from '@/features/cards/hooks/useCards';
import { getBoardSurfaceStyle } from '@/shared/appearance/theme';
import { formatDateTime } from '@/shared/lib/date';
import type { BoardColumn, Card } from '@/shared/types/api';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { EmptyState } from '@/shared/ui/EmptyState';
import { ErrorState } from '@/shared/ui/ErrorState';
import { TextField } from '@/shared/ui/Field';
import { LoadingState } from '@/shared/ui/LoadingState';

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

interface DragSessionState extends CardMoveIntent {
  overColumnId: string;
  overIndex: number;
}

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

  const { resolvedTheme } = useAppearance();
  const boardQuery = useBoardQuery(boardId);
  const columnsQuery = useColumnsQuery(boardId);
  const cardsQuery = useCardsQuery(boardId);
  const boardActivityQuery = useBoardActivityQuery(boardId);
  const boardAppearanceQuery = useBoardAppearanceQuery(boardId);
  const createColumnMutation = useCreateColumnMutation(boardId);
  const updateColumnMutation = useUpdateColumnMutation(boardId);
  const deleteColumnMutation = useDeleteColumnMutation(boardId);
  const updateBoardMutation = useUpdateBoardMutation(workspaceId, boardId);
  const moveCardMutation = useMoveCardMutation(boardId);
  const reorderColumnCardsMutation = useReorderColumnCardsMutation(boardId);

  const [newColumnName, setNewColumnName] = useState('');
  const [dragSession, setDragSession] = useState<DragSessionState | null>(null);
  const [optimisticCards, setOptimisticCards] = useState<Card[] | null>(null);
  const [moveError, setMoveError] = useState<string | null>(null);
  const dropHandledRef = useRef(false);

  const hasPendingCardMove = moveCardMutation.isPending || reorderColumnCardsMutation.isPending;

  const orderedColumns = useMemo(
    () => [...(columnsQuery.data?.items || [])].sort((left, right) => left.position - right.position),
    [columnsQuery.data?.items],
  );

  const currentCards = useMemo(
    () => sortCardsByPosition(optimisticCards || cardsQuery.data?.items || []),
    [cardsQuery.data?.items, optimisticCards],
  );

  const groupedCards = useMemo(() => {
    const map = new Map<string, Card[]>();
    orderedColumns.forEach((column) => map.set(column.id, []));
    currentCards.forEach((card) => {
      const items = map.get(card.columnId) || [];
      items.push(card);
      map.set(card.columnId, items);
    });
    return map;
  }, [currentCards, orderedColumns]);

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

  function handleCardDragStart(card: Card, cardsInColumn: Card[], event: DragEvent<HTMLElement>) {
    if (hasPendingCardMove) return;
    const sourceIndex = cardsInColumn.findIndex((item) => item.id === card.id);
    if (sourceIndex === -1) return;

    dropHandledRef.current = false;
    setMoveError(null);
    setDragSession({
      cardId: card.id,
      sourceColumnId: card.columnId,
      sourceIndex,
      targetColumnId: card.columnId,
      targetIndex: sourceIndex,
      overColumnId: card.columnId,
      overIndex: sourceIndex,
    });

    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', card.id);
  }

  function handleCardDragOver(columnId: string, visibleIndex: number, event: DragEvent<HTMLElement>) {
    event.preventDefault();
    event.stopPropagation();

    const bounds = event.currentTarget?.getBoundingClientRect();
    const shouldInsertAfter = bounds ? event.clientY > bounds.top + bounds.height / 2 : false;
    const nextIndex = visibleIndex + (shouldInsertAfter ? 1 : 0);

    setDragSession((current) => {
      if (!current) return current;
      if (current.overColumnId === columnId && current.overIndex === nextIndex) {
        return current;
      }
      return {
        ...current,
        targetColumnId: columnId,
        targetIndex: nextIndex,
        overColumnId: columnId,
        overIndex: nextIndex,
      };
    });
  }

  function handleColumnDragOver(columnId: string, itemCount: number, event: DragEvent<HTMLElement>) {
    event.preventDefault();
    setDragSession((current) => {
      if (!current) return current;
      if (current.overColumnId === columnId && current.overIndex === itemCount) {
        return current;
      }
      return {
        ...current,
        targetColumnId: columnId,
        targetIndex: itemCount,
        overColumnId: columnId,
        overIndex: itemCount,
      };
    });
  }

  function handleCardDragEnd() {
    if (dropHandledRef.current) {
      dropHandledRef.current = false;
      return;
    }
    setDragSession(null);
  }

  async function handleCardDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    event.stopPropagation();
    dropHandledRef.current = true;

    const session = dragSession;
    if (!session || !boardId) {
      setDragSession(null);
      return;
    }

    setDragSession(null);

    if (session.sourceColumnId === session.targetColumnId && session.sourceIndex === session.targetIndex) {
      return;
    }

    const serverCards = sortCardsByPosition(cardsQuery.data?.items || []);
    const optimistic = reorderBoardPreview(serverCards, session);
    setOptimisticCards(optimistic);
    setMoveError(null);

    try {
      if (session.sourceColumnId === session.targetColumnId) {
        const reorderedColumnCards = groupCardsByColumn(optimistic).get(session.targetColumnId) || [];
        await reorderColumnCardsMutation.mutateAsync({
          columnId: session.targetColumnId,
          items: buildColumnReorderItems(reorderedColumnCards),
        });
      } else {
        const targetCardsWithoutDragged = (groupCardsByColumn(serverCards).get(session.targetColumnId) || [])
          .filter((card) => card.id !== session.cardId);
        await moveCardMutation.mutateAsync({
          cardId: session.cardId,
          targetColumnId: session.targetColumnId,
          position: getDropPositionValue(targetCardsWithoutDragged, session.targetIndex),
        });
      }

      await Promise.all([cardsQuery.refetch(), boardActivityQuery.refetch()]);
      setOptimisticCards(null);
    } catch (error) {
      setOptimisticCards(null);
      setMoveError(error instanceof Error ? error.message : 'Не удалось сохранить новое положение карточки.');
    }
  }

  function renderColumnCards(columnId: string, cards: Card[]): ReactNode {
    if (!cards.length && !dragSession) {
      return <EmptyState title="Здесь пока нет карточек" compact description="Добавь card прямо внутри этой колонки." />;
    }

    const dragCardId = dragSession?.cardId;
    const dropIndex = dragSession?.overColumnId === columnId ? dragSession.overIndex : -1;
    const rows: ReactNode[] = [];
    let visibleIndex = 0;

    cards.forEach((card) => {
      const isDraggedCard = dragCardId === card.id;
      if (!isDraggedCard && dropIndex === visibleIndex) {
        rows.push(<div key={`drop-${columnId}-${visibleIndex}`} className="card-drop-indicator">Drop here</div>);
      }

      const currentVisibleIndex = visibleIndex;
      rows.push(
        <div key={card.id} className="card-slot">
          <article
            draggable={!hasPendingCardMove}
            className={`card-tile ${boardAppearance?.cardPreviewMode === 'compact' ? 'card-tile--compact' : ''} ${isDraggedCard ? 'card-tile--ghosted' : ''}`}
            onDragStart={(event) => handleCardDragStart(card, cards, event)}
            onDragOver={(event) => handleCardDragOver(columnId, currentVisibleIndex, event)}
            onDragEnd={handleCardDragEnd}
            onClick={() => {
              if (dragSession) return;
              setSearchParams((prev) => {
                const next = new URLSearchParams(prev);
                next.set('card', card.id);
                return next;
              });
            }}
          >
            <div className="card-tile__header">
              <strong>{card.title}</strong>
              {card.isArchived ? <Badge tone="warning">archived</Badge> : null}
            </div>
            {(boardAppearance?.showCardDescription ?? true) && boardAppearance?.cardPreviewMode !== 'compact' && card.description ? (
              <p className="muted">{card.description}</p>
            ) : null}
            <div className="card-tile__footer">
              {card.status ? <Badge tone={statusTone[card.status] || 'default'}>{card.status}</Badge> : null}
              {card.priority ? <Badge tone={priorityTone[card.priority] || 'default'}>{card.priority}</Badge> : null}
              {(boardAppearance?.showCardDates ?? true) && card.dueAt ? <Badge tone="default">due {formatDateTime(card.dueAt)}</Badge> : null}
              {(boardAppearance?.showCardDates ?? true) && !card.dueAt && card.startAt ? <Badge tone="default">start {formatDateTime(card.startAt)}</Badge> : null}
            </div>
          </article>
        </div>,
      );

      if (!isDraggedCard) {
        visibleIndex += 1;
      }
    });

    if (dropIndex === visibleIndex) {
      rows.push(<div key={`drop-${columnId}-end`} className="card-drop-indicator">Drop here</div>);
    }

    return <div className={`card-list ${dragSession ? 'card-list--dragging' : ''}`}>{rows}</div>;
  }

  if (!boardId || !workspaceId) {
    return <ErrorState title="Board не выбрана" description="Выбери board из workspace." />;
  }

  const isLoading = boardQuery.isLoading || columnsQuery.isLoading || cardsQuery.isLoading;
  const isError = boardQuery.isError || columnsQuery.isError || cardsQuery.isError;
  const boardAppearance = boardAppearanceQuery.data;

  return (
    <div className="page-shell">
      <section className="page-header">
        <div>
          <h2>{boardQuery.data?.name || 'Board screen'}</h2>
          <p className="muted">Columns + cards + card details + board activity поверх уже подтвержденного backend happy-path.</p>
        </div>
        <div className="page-header__actions">
          <Button onClick={() => navigate(paths.workspaceBoards(workspaceId))}>К boards list</Button>
          <Button onClick={() => navigate(paths.boardAppearance(workspaceId, boardId))}>Customize board</Button>
          <Button onClick={() => void handleRenameBoard()} disabled={updateBoardMutation.isPending || !boardQuery.data}>Переименовать board</Button>
          <Button onClick={() => void Promise.all([boardQuery.refetch(), columnsQuery.refetch(), cardsQuery.refetch(), boardActivityQuery.refetch(), boardAppearanceQuery.refetch()])}>Обновить</Button>
        </div>
      </section>

      {moveError ? (
        <div className="inline-banner inline-banner--error">
          <strong>Перемещение карточки не сохранилось.</strong>
          <span>{moveError}</span>
          <Button variant="ghost" onClick={() => setMoveError(null)}>Скрыть</Button>
        </div>
      ) : null}

      {isLoading ? <LoadingState label="Загружаем board surface…" /> : null}
      {isError ? <ErrorState title="Не удалось собрать board surface" description="Проверь backend и доступность выбранной board." /> : null}

      {!isLoading && !isError ? (
        <div className="board-themed-surface" style={boardAppearance ? getBoardSurfaceStyle(boardAppearance, resolvedTheme) : undefined}>
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
                    <Badge tone="default">columns: {orderedColumns.length}</Badge>
                    <Badge tone="default">cards: {currentCards.length}</Badge>
                    {boardAppearance ? <Badge tone="default">preset: {boardAppearance.themePreset}</Badge> : null}
                  </div>
                </div>
                <div className="grid" style={{ marginTop: 14 }}>
                  <div className="meta-line">updated: {formatDateTime(boardQuery.data?.updatedAt)}</div>
                  {boardAppearance ? (
                    <div className="meta-line">
                      preview: {boardAppearance.columnDensity} / {boardAppearance.cardPreviewMode} / wallpaper {boardAppearance.wallpaper.kind}
                    </div>
                  ) : null}
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

              {orderedColumns.length ? (
                <div className="columns-strip">
                  {orderedColumns.map((column) => {
                    const cards = groupedCards.get(column.id) || [];
                    const cardsWithoutDragged = dragSession ? cards.filter((card) => card.id !== dragSession.cardId) : cards;
                    const isDropTarget = dragSession?.overColumnId === column.id;

                    return (
                      <section
                        key={column.id}
                        className={`column-card ${isDropTarget ? 'column-card--drop-target' : ''}`}
                        onDragOver={(event) => handleColumnDragOver(column.id, cardsWithoutDragged.length, event)}
                        onDrop={(event) => void handleCardDrop(event)}
                      >
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
                        {renderColumnCards(column.id, cards)}
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
        </div>
      ) : null}

      <CardDetailsDrawer />
    </div>
  );
}
