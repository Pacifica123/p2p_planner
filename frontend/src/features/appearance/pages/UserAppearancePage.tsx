import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/shared/ui/Button';
import { ErrorState } from '@/shared/ui/ErrorState';
import { LoadingState } from '@/shared/ui/LoadingState';
import { Panel } from '@/shared/ui/Panel';
import { SelectField } from '@/shared/ui/Field';
import { Badge } from '@/shared/ui/Badge';
import { AppAppearancePreview } from '@/features/appearance/components/AppearancePreview';
import { useMyAppearanceQuery, useUpdateMyAppearanceMutation } from '@/features/appearance/hooks/useAppearance';
import { useAppearance } from '@/app/providers/AppearanceProvider';
import type { Density, UserAppearancePreferences } from '@/shared/types/api';

export function UserAppearancePage() {
  const myAppearanceQuery = useMyAppearanceQuery();
  const updateAppearanceMutation = useUpdateMyAppearanceMutation();
  const { persistedUserAppearance, effectiveUserAppearance, setUserPreview, clearUserPreview } = useAppearance();
  const [draft, setDraft] = useState<UserAppearancePreferences | null>(null);

  useEffect(() => {
    if (!myAppearanceQuery.data) return;
    setDraft(myAppearanceQuery.data);
  }, [myAppearanceQuery.data]);

  useEffect(() => {
    if (draft) {
      setUserPreview({
        appTheme: draft.appTheme,
        density: draft.density,
        reduceMotion: draft.reduceMotion,
      });
    }
    return () => clearUserPreview();
  }, [clearUserPreview, draft, setUserPreview]);

  const hasUnsavedChanges = useMemo(() => {
    if (!draft || !persistedUserAppearance) return false;
    return draft.appTheme !== persistedUserAppearance.appTheme
      || draft.density !== persistedUserAppearance.density
      || draft.reduceMotion !== persistedUserAppearance.reduceMotion;
  }, [draft, persistedUserAppearance]);

  if (myAppearanceQuery.isLoading || !draft || !effectiveUserAppearance) {
    return <LoadingState label="Загружаем user appearance…" />;
  }

  if (myAppearanceQuery.isError) {
    return <ErrorState title="Не удалось загрузить user appearance" onRetry={() => void myAppearanceQuery.refetch()} />;
  }

  const currentDraft = draft;

  async function handleSave() {
    await updateAppearanceMutation.mutateAsync({
      appTheme: currentDraft.appTheme,
      density: currentDraft.density,
      reduceMotion: currentDraft.reduceMotion,
    });
    clearUserPreview();
  }

  function resetDraft() {
    if (!persistedUserAppearance) return;
    setDraft(persistedUserAppearance);
    clearUserPreview();
  }

  return (
    <div className="page-shell">
      <section className="page-header">
        <div>
          <h2>User appearance screen</h2>
          <p className="muted">Персональные app-level preferences. Это не shared board state и не влияет на других участников.</p>
        </div>
        <div className="page-header__actions">
          <Badge tone={hasUnsavedChanges ? 'warning' : 'done'}>{hasUnsavedChanges ? 'preview only' : 'persisted'}</Badge>
          <Button iconOnly onClick={resetDraft} disabled={!hasUnsavedChanges} title="Сбросить изменения" aria-label="Сбросить изменения">↺</Button>
          <Button variant="primary" iconOnly onClick={() => void handleSave()} disabled={updateAppearanceMutation.isPending || !hasUnsavedChanges} title="Сохранить user appearance" aria-label="Сохранить user appearance">
            {updateAppearanceMutation.isPending ? '…' : '💾'}
          </Button>
        </div>
      </section>

      <div className="customization-layout customization-layout--two-columns">
        <div className="grid">
          <Panel title="App-level tokens" description="Server model maps to top-level web tokens: theme, density and motion policy.">
            <div className="grid customization-form-grid">
              <SelectField label="App theme" value={currentDraft.appTheme} onChange={(event) => setDraft({ ...currentDraft, appTheme: event.target.value as UserAppearancePreferences['appTheme'] })}>
                <option value="system">system</option>
                <option value="light">light</option>
                <option value="dark">dark</option>
              </SelectField>
              <SelectField label="Density" value={currentDraft.density} onChange={(event) => setDraft({ ...currentDraft, density: event.target.value as Density })}>
                <option value="comfortable">comfortable</option>
                <option value="compact">compact</option>
              </SelectField>
            </div>

            <div className="setting-row-list">
              <label className="toggle-row">
                <span>
                  <strong>Reduce motion</strong>
                  <span className="muted">Отключает transition-heavy feedback в web shell.</span>
                </span>
                <input type="checkbox" checked={currentDraft.reduceMotion} onChange={(event) => setDraft({ ...currentDraft, reduceMotion: event.target.checked })} />
              </label>
            </div>
          </Panel>

          <Panel title="Rules" description="Preview and persistence boundaries for user customization.">
            <ul className="rules-list">
              <li>Изменения сначала живут как local preview state и применяются только в текущей вкладке.</li>
              <li>После Save UI делает optimistic update для <code>me/appearance</code> и затем подтверждает результат сервером.</li>
              <li>Reset возвращает persisted state и очищает purely local preview.</li>
            </ul>
          </Panel>
        </div>

        <AppAppearancePreview appearance={effectiveUserAppearance} />
      </div>
    </div>
  );
}
