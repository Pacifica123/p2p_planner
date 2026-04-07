import type { Board, BoardAppearanceSettings } from '@/shared/types/api';
import { formatDateTime } from '@/shared/lib/date';
import { Badge } from '@/shared/ui/Badge';

interface BoardOverviewPanelProps {
  board: Board | undefined;
  boardAppearance?: BoardAppearanceSettings;
  columnCount: number;
  cardCount: number;
}

export function BoardOverviewPanel({ board, boardAppearance, columnCount, cardCount }: BoardOverviewPanelProps) {
  return (
    <section className="panel board-overview-panel">
      <div className="entity-header board-overview-panel__header">
        <div>
          <h3>Board summary</h3>
          <p className="muted">{board?.description || 'Без описания'}</p>
        </div>
        <div className="row-actions">
          <Badge tone="kanban">kanban</Badge>
          {boardAppearance ? <Badge tone="default">preset: {boardAppearance.themePreset}</Badge> : null}
        </div>
      </div>

      <div className="board-stats-grid">
        <article className="board-stat-card">
          <span className="meta-line">Columns</span>
          <strong>{columnCount}</strong>
        </article>
        <article className="board-stat-card">
          <span className="meta-line">Cards</span>
          <strong>{cardCount}</strong>
        </article>
        <article className="board-stat-card">
          <span className="meta-line">Updated</span>
          <strong>{formatDateTime(board?.updatedAt)}</strong>
        </article>
        {boardAppearance ? (
          <article className="board-stat-card">
            <span className="meta-line">Preview</span>
            <strong>
              {boardAppearance.columnDensity} / {boardAppearance.cardPreviewMode}
            </strong>
            <span className="meta-line">wallpaper {boardAppearance.wallpaper.kind}</span>
          </article>
        ) : null}
      </div>
    </section>
  );
}
