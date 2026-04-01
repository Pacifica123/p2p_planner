import { Button } from '@/shared/ui/Button';

interface ErrorStateProps {
  title?: string;
  description?: string;
  compact?: boolean;
  onRetry?: () => void;
}

export function ErrorState({
  title = 'Что-то пошло не так',
  description = 'Попробуй обновить данные или проверь backend.',
  compact = false,
  onRetry,
}: ErrorStateProps) {
  return (
    <div className={`error-state ${compact ? 'error-state--compact' : ''}`}>
      <strong>{title}</strong>
      {description ? <p className="muted">{description}</p> : null}
      {onRetry ? <Button onClick={onRetry}>Повторить</Button> : null}
    </div>
  );
}
