import { Button } from '@/shared/ui/Button';

interface ErrorStateProps {
  title: string;
  description?: string;
  compact?: boolean;
  onRetry?: () => void;
}

export function ErrorState({ title, description, compact = false, onRetry }: ErrorStateProps) {
  return (
    <div className={`error-state ${compact ? 'error-state--compact' : ''}`}>
      <strong>{title}</strong>
      {description ? <p className="muted">{description}</p> : null}
      {onRetry ? <Button iconOnly onClick={onRetry} title="Повторить" aria-label="Повторить">↻</Button> : null}
    </div>
  );
}
