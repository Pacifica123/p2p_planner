import type { ActivityEntry } from '@/shared/types/api';
import { formatDateTime } from '@/shared/lib/date';
import { EmptyState } from '@/shared/ui/EmptyState';

interface ActivityFeedProps {
  items: ActivityEntry[];
  emptyTitle?: string;
}

function humanizeKind(value: string) {
  return value.split('.').join(' · ');
}

export function ActivityFeed({ items, emptyTitle = 'Пока нет событий' }: ActivityFeedProps) {
  if (!items.length) {
    return <EmptyState title={emptyTitle} compact description="История начнет появляться после изменений по сущности." />;
  }

  return (
    <div className="activity-list">
      {items.map((item) => (
        <article key={item.id} className="activity-item">
          <div className="activity-item__header">
            <strong>{humanizeKind(item.kind)}</strong>
            <span className="muted">{formatDateTime(item.createdAt)}</span>
          </div>
          <div className="meta-line">actor: {item.actor.displayName || item.actor.userId || 'system'}</div>
          <div className="meta-line">entity: {item.entityType}</div>
          {item.fieldMask.length ? <div className="meta-line">fields: {item.fieldMask.join(', ')}</div> : null}
          {Object.keys(item.payload || {}).length ? <pre className="code-block">{JSON.stringify(item.payload, null, 2)}</pre> : null}
        </article>
      ))}
    </div>
  );
}
