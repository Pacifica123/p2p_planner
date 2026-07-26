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
import { Icon } from '@/shared/ui/Icon';

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
    return <ErrorState title="Не удалось открыть оформление доски" />;
  }

  if (boardAppearanceQuery.isLoading || !draft) {
    return <LoadingState label="Загружаем оформление доски…" />;
  }

  if (boardAppearanceQuery.isError) {
    return <ErrorState title="Не удалось загрузить оформление доски" onRetry={() => void boardAppearanceQuery.refetch()} />;
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
          <h2>Вид доски</h2>
          <p className="muted">Общие настройки этой доски — их увидят все участники.</p>
        </div>
        <div className="page-header__actions">
          <Badge tone={hasUnsavedChanges ? 'warning' : 'done'}>{hasUnsavedChanges ? 'есть изменения' : 'сохранено'}</Badge>
          <Button iconOnly onClick={resetDraft} disabled={!hasUnsavedChanges} title="Сбросить изменения" aria-label="Сбросить изменения"><Icon name="refresh" /></Button>
          <Button variant="primary" onClick={() => void handleSave()} disabled={updateBoardAppearanceMutation.isPending || !hasUnsavedChanges}>
            {updateBoardAppearanceMutation.isPending ? 'Сохраняем…' : <><Icon name="save" size={16} /> Сохранить</>}
          </Button>
          <Link className="button" to={paths.board(workspaceId, boardId)}><Icon name="back" size={16} /> К доске</Link>
        </div>
      </section>

      <div className="customization-layout customization-layout--two-columns">
        <div className="grid">
          <Panel title="Цветовая схема" description="Готовая палитра для фона, колонок и карточек.">
            <PresetPicker value={currentDraft.themePreset} onChange={(next) => setDraft({ ...currentDraft, themePreset: next })} />
          </Panel>

          <Panel title="Фон" description="Готовый фон, сплошной цвет или CSS-градиент.">
            <div className="grid customization-form-grid">
              <SelectField label="Тип фона" value={currentDraft.wallpaper.kind} onChange={(event) => setDraft({ ...currentDraft, wallpaper: { ...currentDraft.wallpaper, kind: event.target.value as BoardAppearanceSettings['wallpaper']['kind'], value: event.target.value === 'none' ? null : currentDraft.wallpaper.value } })}>
                <option value="none">По схеме</option>
                <option value="solid">Цвет</option>
                <option value="gradient">Градиент</option>
                <option value="preset">Готовый фон</option>
              </SelectField>

              {currentDraft.wallpaper.kind === 'preset' ? (
                <SelectField label="Готовый фон" value={currentDraft.wallpaper.value || 'aurora'} onChange={(event) => setDraft({ ...currentDraft, wallpaper: { kind: 'preset', value: event.target.value } })}>
                  {presetWallpaperOptions.map((option) => (
                    <option key={option} value={option}>{option}</option>
                  ))}
                </SelectField>
              ) : currentDraft.wallpaper.kind !== 'none' ? (
                <TextField
                  label={currentDraft.wallpaper.kind === 'solid' ? 'CSS-цвет' : 'CSS-градиент'}
                  value={currentDraft.wallpaper.value || ''}
                  onChange={(event) => setDraft({ ...currentDraft, wallpaper: { kind: currentDraft.wallpaper.kind, value: event.target.value } })}
                  placeholder={currentDraft.wallpaper.kind === 'solid' ? '#0f172a' : 'linear-gradient(135deg, #1e293b, #0f172a)'}
                />
              ) : null}
            </div>
          </Panel>

          <Panel title="Отображение карточек">
            <div className="grid customization-form-grid">
              <SelectField label="Плотность колонок" value={currentDraft.columnDensity} onChange={(event) => setDraft({ ...currentDraft, columnDensity: event.target.value as Density })}>
                <option value="comfortable">Свободная</option>
                <option value="compact">Компактная</option>
              </SelectField>
              <SelectField label="Вид карточек" value={currentDraft.cardPreviewMode} onChange={(event) => setDraft({ ...currentDraft, cardPreviewMode: event.target.value as BoardAppearanceSettings['cardPreviewMode'] })}>
                <option value="compact">Компактный</option>
                <option value="expanded">Расширенный</option>
              </SelectField>
            </div>
            <div className="setting-row-list">
              <label className="toggle-row">
                <span>
                  <strong>Показывать описание</strong>
                </span>
                <input type="checkbox" checked={currentDraft.showCardDescription} onChange={(event) => setDraft({ ...currentDraft, showCardDescription: event.target.checked })} />
              </label>
              <label className="toggle-row">
                <span>
                  <strong>Показывать даты</strong>
                </span>
                <input type="checkbox" checked={currentDraft.showCardDates} onChange={(event) => setDraft({ ...currentDraft, showCardDates: event.target.checked })} />
              </label>
              <label className="toggle-row">
                <span>
                  <strong>Показывать прогресс чек-листа</strong>
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
