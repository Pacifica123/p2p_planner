import type { LocalFirstBoardRuntime } from '@/features/localFirst/types';
import { Button } from '@/shared/ui/Button';

interface LocalFirstStatusBannerProps {
  runtime: LocalFirstBoardRuntime;
}

export function LocalFirstStatusBanner({ runtime }: LocalFirstStatusBannerProps) {
  const hasPending = runtime.pendingCount > 0;
  const hasFailed = runtime.failedCount > 0;
  const isOffline = !runtime.isOnline;
  const shouldShow = isOffline || hasPending || hasFailed || runtime.hasWarmSnapshot || runtime.isFlushing;

  if (!shouldShow) return null;

  const statusParts: string[] = [];
  if (isOffline) statusParts.push('offline');
  if (runtime.hasWarmSnapshot) statusParts.push('warm start из local snapshot');
  if (runtime.isFlushing) statusParts.push('syncing');
  if (hasPending) statusParts.push(`${runtime.pendingCount} saved locally`);
  if (hasFailed) statusParts.push(`${runtime.failedCount} sync failed`);

  return (
    <div className={`inline-banner local-first-banner ${hasFailed ? 'inline-banner--error' : ''}`}>
      <div>
        <strong>Local-first runtime</strong>
        <span>{statusParts.join(' · ')}</span>
        {runtime.lastError ? <span className="muted">{runtime.lastError}</span> : null}
      </div>
      <div className="row-actions">
        {hasFailed ? (
          <Button variant="primary" onClick={() => void runtime.retryFailedOperations()} disabled={runtime.isFlushing || !runtime.isOnline}>
            Retry failed
          </Button>
        ) : null}
        {hasPending ? (
          <Button variant="ghost" onClick={() => void runtime.flushPendingOperations()} disabled={runtime.isFlushing || !runtime.isOnline}>
            Flush now
          </Button>
        ) : null}
      </div>
    </div>
  );
}
