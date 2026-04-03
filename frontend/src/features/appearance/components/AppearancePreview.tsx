import { useAppearance } from '@/app/providers/AppearanceProvider';
import { Badge } from '@/shared/ui/Badge';
import { getBoardPresetDefinition, getBoardSurfaceStyle } from '@/shared/appearance/theme';
import type { BoardAppearanceSettings, UserAppearancePreferences } from '@/shared/types/api';

export function AppAppearancePreview({ appearance }: { appearance: UserAppearancePreferences }) {
  const { resolvedTheme } = useAppearance();

  return (
    <div className="appearance-preview-card">
      <div className="appearance-preview-card__header">
        <div>
          <h4>App preview</h4>
          <p className="muted">Текущая web shell preview без сохранения на сервер до нажатия Save.</p>
        </div>
        <div className="row-actions">
          <Badge tone={appearance.appTheme}>{appearance.appTheme}</Badge>
          <Badge tone={resolvedTheme}>resolved: {resolvedTheme}</Badge>
          <Badge tone={appearance.density}>{appearance.density}</Badge>
        </div>
      </div>
      <div className="app-preview-shell">
        <aside className="app-preview-shell__sidebar">
          <strong>P2P Planner</strong>
          <span className="muted">Navigation / settings</span>
        </aside>
        <div className="app-preview-shell__main">
          <div className="app-preview-shell__topbar">
            <strong>User appearance</strong>
            <span className="muted">reduceMotion: {appearance.reduceMotion ? 'on' : 'off'}</span>
          </div>
          <div className="app-preview-shell__content">
            <div className="app-preview-shell__panel">
              <strong>Preview panel</strong>
              <p className="muted">Theme and density are applied through app tokens.</p>
            </div>
            <div className="app-preview-shell__panel">
              <strong>Form surface</strong>
              <div className="app-preview-shell__chips">
                <span className="badge badge--default">comfortable</span>
                <span className="badge badge--default">compact</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function BoardAppearancePreview({ appearance }: { appearance: BoardAppearanceSettings }) {
  const { resolvedTheme } = useAppearance();
  const preset = getBoardPresetDefinition(appearance.themePreset);
  const cards = appearance.cardPreviewMode === 'compact' ? 2 : 3;
  return (
    <div className="appearance-preview-card">
      <div className="appearance-preview-card__header">
        <div>
          <h4>Board preview</h4>
          <p className="muted">Отдельный preview canvas для board-level appearance без вмешательства в core editor screen.</p>
        </div>
        <div className="row-actions">
          <Badge tone="default">{preset.label}</Badge>
          <Badge tone={resolvedTheme}>app {resolvedTheme}</Badge>
        </div>
      </div>
      <div className="board-preview-surface" style={getBoardSurfaceStyle(appearance, resolvedTheme)}>
        <div className="board-preview-surface__topbar">
          <strong>Roadmap</strong>
          <div className="row-actions">
            <Badge tone={appearance.columnDensity}>{appearance.columnDensity}</Badge>
            <Badge tone={appearance.cardPreviewMode}>{appearance.cardPreviewMode}</Badge>
          </div>
        </div>
        <div className="board-preview-columns">
          {['Todo', 'Doing', 'Done'].map((title, index) => (
            <section key={title} className="board-preview-column">
              <div className="column-card__header">
                <strong>{title}</strong>
                <span className="muted">{index + 2}</span>
              </div>
              <div className="card-list">
                {Array.from({ length: cards }).map((_, cardIndex) => (
                  <article key={`${title}-${cardIndex}`} className="card-tile">
                    <strong>{cardIndex === 0 ? 'Board appearance draft' : 'Preview card'}</strong>
                    {appearance.showCardDescription ? <p className="muted">Description visibility follows board settings.</p> : null}
                    <div className="card-tile__footer">
                      {appearance.showCardDates ? <Badge tone="default">date</Badge> : null}
                      {appearance.showChecklistProgress ? <Badge tone="done">checklist</Badge> : null}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
