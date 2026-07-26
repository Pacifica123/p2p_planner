import type { ActivityEntry } from '@/shared/types/api';
import { formatDateTime } from '@/shared/lib/date';
import { EmptyState } from '@/shared/ui/EmptyState';

interface ActivityFeedProps {
  items: ActivityEntry[];
  emptyTitle?: string;
}

const entityLabels: Record<string, string> = {
  board: 'Доска',
  card: 'Карточка',
  checklist: 'Чек-лист',
  checklist_item: 'Пункт чек-листа',
  column: 'Колонка',
  comment: 'Комментарий',
  label: 'Метка',
  workspace: 'Пространство',
};

const actionLabels: Record<string, string> = {
  archived: 'отправлена в архив',
  completed: 'завершён',
  created: 'создана',
  deleted: 'удалена',
  moved: 'перемещена',
  reordered: 'переставлена',
  restored: 'восстановлена',
  updated: 'изменена',
};

function humanizeKind(value: string) {
  const [entity, action] = value.split('.');
  const subject = entityLabels[entity] || entity.split('_').join(' ');
  const result = actionLabels[action] || action?.split('_').join(' ');
  return result ? `${subject} ${result}` : subject;
}

function changedFields(fieldMask: string[]) {
  const labels: Record<string, string> = {
    columnId: 'колонка',
    description: 'описание',
    dueAt: 'срок',
    isDone: 'состояние',
    name: 'название',
    position: 'положение',
    priority: 'приоритет',
    status: 'статус',
    title: 'название',
  };
  return fieldMask.map((field) => labels[field] || field).join(', ');
}

export function ActivityFeed({ items, emptyTitle = 'Пока нет событий' }: ActivityFeedProps) {
  if (!items.length) {
    return <EmptyState title={emptyTitle} compact description="Изменения появятся здесь автоматически." />;
  }

  return (
    <div className="activity-list">
      {items.map((item) => {
        const hasTechnicalDetails = Object.keys(item.payload || {}).length > 0;
        return (
          <article key={item.id} className="activity-item">
            <div className="activity-item__header">
              <strong>{humanizeKind(item.kind)}</strong>
              <time className="muted">{formatDateTime(item.createdAt)}</time>
            </div>
            <p className="activity-item__actor">
              {item.actor.displayName || item.actor.userId || 'Система'}
              {item.fieldMask.length ? ` · ${changedFields(item.fieldMask)}` : ''}
            </p>
            {hasTechnicalDetails ? (
              <details className="activity-item__details">
                <summary>Технические детали</summary>
                <pre className="code-block">{JSON.stringify(item.payload, null, 2)}</pre>
              </details>
            ) : null}
          </article>
        );
      })}
    </div>
  );
}
