import { DragEvent, ReactNode } from 'react';
import { CreateCardInlineForm } from '@/features/boards/components/CreateCardInlineForm';
import type { BoardColumn, Card } from '@/shared/types/api';
import { Button } from '@/shared/ui/Button';

interface BoardColumnSectionProps {
  boardId: string;
  column: BoardColumn;
  cards: Card[];
  cardsWithoutDragged: Card[];
  isDropTarget: boolean;
  isMutating: boolean;
  onRename: (column: BoardColumn) => void;
  onDelete: (column: BoardColumn) => void;
  onColumnDragOver: (columnId: string, itemCount: number, event: DragEvent<HTMLElement>) => void;
  onDrop: (event: DragEvent<HTMLElement>) => void;
  cardsContent: ReactNode;
}

export function BoardColumnSection({
  boardId,
  column,
  cards,
  cardsWithoutDragged,
  isDropTarget,
  isMutating,
  onRename,
  onDelete,
  onColumnDragOver,
  onDrop,
  cardsContent,
}: BoardColumnSectionProps) {
  return (
    <section
      className={`column-card ${isDropTarget ? 'column-card--drop-target' : ''}`}
      onDragOver={(event) => onColumnDragOver(column.id, cardsWithoutDragged.length, event)}
      onDrop={onDrop}
    >
      <div className="column-card__header">
        <div>
          <h3>{column.name}</h3>
          <p className="muted">cards: {cards.length}</p>
        </div>
        <div className="row-actions">
          <Button iconOnly onClick={() => onRename(column)} disabled={isMutating} title="Переименовать колонку" aria-label="Переименовать колонку">
            ✏️
          </Button>
          <Button iconOnly variant="danger" onClick={() => onDelete(column)} disabled={isMutating} title="Удалить колонку" aria-label="Удалить колонку">
            🗑️
          </Button>
        </div>
      </div>

      <CreateCardInlineForm columnId={column.id} boardId={boardId} />
      {cardsContent}
    </section>
  );
}
