import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Button } from '@/shared/ui/Button';
import { ErrorState } from '@/shared/ui/ErrorState';
import { LoadingState } from '@/shared/ui/LoadingState';
import { Panel } from '@/shared/ui/Panel';
import { SelectField, TextField } from '@/shared/ui/Field';
import { Badge } from '@/shared/ui/Badge';
import { BoardAppearancePreview } from '@/features/appearance/components/AppearancePreview';
import { PresetPicker } from '@/features/appearance/components/PresetPicker';
import { useBoardAppearanceQuery, useUpdateBoardAppearanceMutation } from '@/features/appearance/hooks/useAppearance';
import { paths } from '@/app/router/paths';
import type { BoardAppearanceSettings, Density } from '@/shared/types/api';

const presetWallpaperOptions = ['aurora', 'blueprint', 'canopy', 'sunrise', 'nebula'];

export function BoardAppearancePage() {
  const { workspaceId, boardId } = useParams();
  const boardAppearanceQuery = useBoardAppearanceQuery(boardId);
  const updateBoardAppearanceMutation = useUpdateBoardAppearanceMutation(boardId);
  const [draft, setDraft] = useState<BoardAppearanceSettings | null>(null);

  useEffect(() => {
    if (!boardAppearanceQuery.data) return;
    setDraft(boardAppearanceQuery.data);
  }, [boardAppearanceQuery.data]);

  const hasUnsavedChanges = useMemo(() => JSON.stringify(draft) !== JSON.stringify(boardAppearanceQuery.data), [draft, boardAppearanceQuery.data]);

  if (!workspaceId || !boardId) {
    return <ErrorState title="Board appearance screen не может открыться без boardId" />;
  }

  if (boardAppearanceQuery.isLoading || !draft) {
    return <LoadingState label="Загружаем board appearance…" />;
  }

  if (boardAppearanceQuery.isError) {
    return <ErrorState title="Не удалось загрузить board appearance" onRetry={() => void boardAppearanceQuery.refetch()} />;
  }

  const currentDraft = draft;

  async function handleSave() {
    await updateBoardAppearanceMutation.mutateAsync({
      themePreset: currentDraft.themePreset,
      wallpaper: currentDraft.wallpaper,
      columnDensity: currentDraft.columnDensity,
      cardPreviewMode: currentDraft.cardPreviewMode,
      showCardDescription: currentDraft.showCardDescription,
      showCardDates: currentDraft.showCardDates,
      showChecklistProgress: currentDraft.showChecklistProgress,
      customProperties: currentDraft.customProperties,
    });
  }

  function resetDraft() {
    if (!boardAppearanceQuery.data) return;
    setDraft(boardAppearanceQuery.data);
  }

  return (
    <div className="page-shell">
      <section className="page-header">
        <div>
          <h2>Board appearance screen</h2>
          <p className="muted">Shared board-level customization surface. Экран отдельный от core kanban UI и не смешивает editing c board content.</p>
        </div>
        <div className="page-header__actions">
          <Badge tone={hasUnsavedChanges ? 'warning' : 'done'}>{hasUnsavedChanges ? 'draft preview' : 'persisted'}</Badge>
          <Button onClick={resetDraft} disabled={!hasUnsavedChanges}>Reset</Button>
          <Button variant="primary" onClick={() => void handleSave()} disabled={updateBoardAppearanceMutation.isPending || !hasUnsavedChanges}>
            {updateBoardAppearanceMutation.isPending ? 'Saving…' : 'Save board appearance'}
          </Button>
          <Link className="button" to={paths.board(workspaceId, boardId)}>Back to board</Link>
        </div>
      </section>

      <div className="customization-layout customization-layout--two-columns">
        <div className="grid">
          <Panel title="Theme preset" description="Backend stores only preset id; web maps it to local token packs.">
            <PresetPicker value={currentDraft.themePreset} onChange={(next) => setDraft({ ...currentDraft, themePreset: next })} />
          </Panel>

          <Panel title="Wallpaper" description="Wallpaper model stays UI-safe: none, solid, gradient or preset. No asset uploads in v1.">
            <div className="grid customization-form-grid">
              <SelectField label="Wallpaper kind" value={currentDraft.wallpaper.kind} onChange={(event) => setDraft({ ...currentDraft, wallpaper: { ...currentDraft.wallpaper, kind: event.target.value as BoardAppearanceSettings['wallpaper']['kind'], value: event.target.value === 'none' ? null : currentDraft.wallpaper.value } })}>
                <option value="none">none</option>
                <option value="solid">solid</option>
                <option value="gradient">gradient</option>
                <option value="preset">preset</option>
              </SelectField>

              {currentDraft.wallpaper.kind === 'preset' ? (
                <SelectField label="Preset wallpaper" value={currentDraft.wallpaper.value || 'aurora'} onChange={(event) => setDraft({ ...currentDraft, wallpaper: { kind: 'preset', value: event.target.value } })}>
                  {presetWallpaperOptions.map((option) => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </SelectField>
              ) : currentDraft.wallpaper.kind !== 'none' ? (
                <TextField
                  label={currentDraft.wallpaper.kind === 'solid' ? 'Solid CSS color' : 'Gradient CSS value'}
                  value={currentDraft.wallpaper.value || ''}
                  onChange={(event) => setDraft({ ...currentDraft, wallpaper: { kind: currentDraft.wallpaper.kind, value: event.target.value } })}
                  placeholder={currentDraft.wallpaper.kind === 'solid' ? '#0f172a' : 'linear-gradient(135deg, #1e293b, #0f172a)'}
                />
              ) : null}
            </div>
          </Panel>

          <Panel title="Board rendering controls" description="Exactly the surface that affects board rendering, not app shell rendering.">
            <div className="grid customization-form-grid">
              <SelectField label="Column density" value={currentDraft.columnDensity} onChange={(event) => setDraft({ ...currentDraft, columnDensity: event.target.value as Density })}>
                <option value="comfortable">comfortable</option>
                <option value="compact">compact</option>
              </SelectField>
              <SelectField label="Card preview mode" value={currentDraft.cardPreviewMode} onChange={(event) => setDraft({ ...currentDraft, cardPreviewMode: event.target.value as BoardAppearanceSettings['cardPreviewMode'] })}>
                <option value="compact">compact</option>
                <option value="expanded">expanded</option>
              </SelectField>
            </div>
            <div className="setting-row-list">
              <label className="toggle-row">
                <span>
                  <strong>Show card description</strong>
                  <span className="muted">Board-level visibility toggle.</span>
                </span>
                <input type="checkbox" checked={currentDraft.showCardDescription} onChange={(event) => setDraft({ ...currentDraft, showCardDescription: event.target.checked })} />
              </label>
              <label className="toggle-row">
                <span>
                  <strong>Show card dates</strong>
                  <span className="muted">Controls date chips on cards.</span>
                </span>
                <input type="checkbox" checked={currentDraft.showCardDates} onChange={(event) => setDraft({ ...currentDraft, showCardDates: event.target.checked })} />
              </label>
              <label className="toggle-row">
                <span>
                  <strong>Show checklist progress</strong>
                  <span className="muted">Future-ready visual toggle kept inside board appearance state.</span>
                </span>
                <input type="checkbox" checked={currentDraft.showChecklistProgress} onChange={(event) => setDraft({ ...currentDraft, showChecklistProgress: event.target.checked })} />
              </label>
            </div>
          </Panel>
        </div>

        <BoardAppearancePreview appearance={currentDraft} />
      </div>
    </div>
  );
}
