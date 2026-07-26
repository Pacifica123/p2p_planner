import { DragEvent, ReactNode } from 'react';
import { CreateCardInlineForm } from '@/features/boards/components/CreateCardInlineForm';
import type { BoardColumn, Card } from '@/shared/types/api';
import { Button } from '@/shared/ui/Button';
import { Icon } from '@/shared/ui/Icon';

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
      data-testid="board-column"
      onDragOver={(event) => onColumnDragOver(column.id, cardsWithoutDragged.length, event)}
      onDrop={onDrop}
    >
      <div className="column-card__header">
        <div>
          <h3>{column.name}</h3>
          <p className="muted">{cards.length} карточек</p>
        </div>
        <div className="row-actions">
          <Button iconOnly onClick={() => onRename(column)} disabled={isMutating} title="Переименовать колонку" aria-label="Переименовать колонку">
            <Icon name="edit" size={16} />
          </Button>
          <Button iconOnly variant="danger" onClick={() => onDelete(column)} disabled={isMutating} title="Удалить колонку" aria-label="Удалить колонку">
            <Icon name="trash" size={16} />
          </Button>
        </div>
      </div>

      <div className="column-card__composer">
        <CreateCardInlineForm columnId={column.id} boardId={boardId} />
      </div>
      {cardsContent}
    </section>
  );
}
