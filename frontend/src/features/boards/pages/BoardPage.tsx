import { DragEvent, FormEvent, ReactNode, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { paths } from '@/app/router/paths';
import { useAppearance } from '@/app/providers/AppearanceProvider';
import { ActivityFeed } from '@/features/activity/components/ActivityFeed';
import { useBoardActivityQuery } from '@/features/activity/hooks/useActivity';
import { useBoardAppearanceQuery } from '@/features/appearance/hooks/useAppearance';
import { BoardColumnSection } from '@/features/boards/components/BoardColumnSection';
import { BoardOverviewPanel } from '@/features/boards/components/BoardOverviewPanel';
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
import { useCardsQuery, useMoveCardMutation, useReorderColumnCardsMutation } from '@/features/cards/hooks/useCards';
import { getBoardSurfaceStyle } from '@/shared/appearance/theme';
import { formatDateTime } from '@/shared/lib/date';
import type { BoardColumn, Card } from '@/shared/types/api';
import { Badge } from '@/shared/ui/Badge';
import { Button } from '@/shared/ui/Button';
import { EmptyState } from '@/shared/ui/EmptyState';
import { ErrorState } from '@/shared/ui/ErrorState';
import { TextField } from '@/shared/ui/Field';
import { LoadingState } from '@/shared/ui/LoadingState';
import { Panel } from '@/shared/ui/Panel';

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
  const boardAppearance = boardAppearanceQuery.data;

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

    const bounds = (event.currentTarget as HTMLElement | null)?.getBoundingClientRect();
    if (!bounds) return;

    const shouldInsertAfter = event.clientY > bounds.top + bounds.height / 2;
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

  return (
    <div className="page-shell">
      <section className="page-header">
        <div>
          <h2>{boardQuery.data?.name || 'Board screen'}</h2>
          <p className="muted">Рабочая kanban-поверхность с колонками, карточками, drag-and-drop и activity feed.</p>
        </div>
        <div className="page-header__actions">
          <Button onClick={() => navigate(paths.workspaceBoards(workspaceId))}>К boards list</Button>
          <Button iconOnly onClick={() => navigate(paths.boardAppearance(workspaceId, boardId))} title="Настроить board" aria-label="Настроить board">🎨</Button>
          <Button iconOnly onClick={() => void handleRenameBoard()} disabled={updateBoardMutation.isPending || !boardQuery.data} title="Переименовать board" aria-label="Переименовать board">✏️</Button>
          <Button iconOnly onClick={() => void Promise.all([boardQuery.refetch(), columnsQuery.refetch(), cardsQuery.refetch(), boardActivityQuery.refetch(), boardAppearanceQuery.refetch()])} title="Обновить board" aria-label="Обновить board">↻</Button>
        </div>
      </section>

      {moveError ? (
        <div className="inline-banner inline-banner--error">
          <strong>Перемещение карточки не сохранилось.</strong>
          <span>{moveError}</span>
          <Button variant="ghost" iconOnly onClick={() => setMoveError(null)} title="Скрыть сообщение" aria-label="Скрыть сообщение">✕</Button>
        </div>
      ) : null}

      {isLoading ? <LoadingState label="Загружаем board surface…" /> : null}
      {isError ? <ErrorState title="Не удалось собрать board surface" description="Проверь backend и доступность выбранной board." /> : null}

      {!isLoading && !isError ? (
        <div className="board-themed-surface" style={boardAppearance ? getBoardSurfaceStyle(boardAppearance, resolvedTheme) : undefined}>
          <div className="board-layout">
            <div className="board-main">
              <div className="board-top-grid">
                <BoardOverviewPanel
                  board={boardQuery.data}
                  boardAppearance={boardAppearance}
                  columnCount={orderedColumns.length}
                  cardCount={currentCards.length}
                />

                <Panel
                  title="Create column"
                  description="Быстрое добавление новой колонки без ухода со страницы."
                >
                  <form className="inline-form__row inline-form__row--stackable" onSubmit={handleCreateColumn}>
                    <TextField
                      label="Название колонки"
                      value={newColumnName}
                      onChange={(event) => setNewColumnName(event.target.value)}
                      placeholder="Например, Todo"
                    />
                    <Button type="submit" variant="primary" disabled={createColumnMutation.isPending}>
                      {createColumnMutation.isPending ? 'Создаем…' : '＋ Колонка'}
                    </Button>
                  </form>
                </Panel>
              </div>

              {orderedColumns.length ? (
                <div className="columns-strip columns-strip--board-surface">
                  {orderedColumns.map((column) => {
                    const cards = groupedCards.get(column.id) || [];
                    const cardsWithoutDragged = dragSession ? cards.filter((card) => card.id !== dragSession.cardId) : cards;

                    return (
                      <BoardColumnSection
                        key={column.id}
                        boardId={boardId}
                        column={column}
                        cards={cards}
                        cardsWithoutDragged={cardsWithoutDragged}
                        isDropTarget={dragSession?.overColumnId === column.id}
                        isMutating={updateColumnMutation.isPending || deleteColumnMutation.isPending}
                        onRename={(item) => void handleRenameColumn(item)}
                        onDelete={(item) => void handleDeleteColumn(item)}
                        onColumnDragOver={handleColumnDragOver}
                        onDrop={(event) => void handleCardDrop(event)}
                        cardsContent={renderColumnCards(column.id, cards)}
                      />
                    );
                  })}
                </div>
              ) : (
                <EmptyState title="У board пока нет колонок" description="Сначала создай колонку, после этого появится место для карточек." />
              )}
            </div>

            <section className="panel board-sidebar-panel">
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
