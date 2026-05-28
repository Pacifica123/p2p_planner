import type { SyncBaselineRuntime } from '@/features/sync/hooks/useSyncBaseline';
import { Button } from '@/shared/ui/Button';

interface SyncBaselineStatusProps {
  runtime: SyncBaselineRuntime;
}

export function SyncBaselineStatus({ runtime }: SyncBaselineStatusProps) {
  if (runtime.state === 'idle') return null;

  const parts = [`state: ${runtime.state}`];
  if (runtime.replica?.id) parts.push(`replica: ${runtime.replica.id.slice(0, 8)}`);
  if (runtime.status?.maxServerOrder !== undefined && runtime.status?.maxServerOrder !== null) {
    parts.push(`server order: ${runtime.status.maxServerOrder}`);
  }
  if (runtime.lastPulledAt) parts.push(`pulled: ${new Date(runtime.lastPulledAt).toLocaleTimeString()}`);

  return (
    <div className={`inline-banner sync-baseline-banner ${runtime.state === 'error' ? 'inline-banner--error' : ''}`} data-testid="sync-baseline-status">
      <div>
        <strong>Sync baseline</strong>
        <span>{parts.join(' · ')}</span>
        {runtime.lastError ? <span className="muted">{runtime.lastError}</span> : null}
      </div>
      <div className="row-actions">
        <Button variant="ghost" onClick={() => void runtime.refreshStatus()} disabled={!runtime.replica?.id || runtime.state === 'registering'}>
          Status
        </Button>
        <Button variant="ghost" onClick={() => void runtime.pullWorkspace()} disabled={!runtime.replica?.id || runtime.state === 'registering' || runtime.state === 'pulling'}>
          Pull
        </Button>
      </div>
    </div>
  );
}
