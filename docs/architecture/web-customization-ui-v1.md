# Web customization UI v1

## Статус

Draft v1 / implementation-ready / basic frontend slice implemented

## Контекст

Backend already exposes two separate appearance resources:

- `GET/PUT /me/appearance`
- `GET/PUT /boards/{boardId}/appearance`

At the domain level this split is intentional: user appearance is personal UX state, while board appearance is shared board state. The web client should preserve that boundary instead of hiding everything behind one mixed “theme settings” panel.

This document describes the **web customization surface** only. It does not redefine the long-term cross-platform theme engine, mobile rendering behavior, or full sync semantics between devices.

---

## Цель этапа

Сделать отдельный customization surface для web, который:

- живет отдельно от core kanban editing UI;
- покрывает user appearance screen и board appearance screen;
- фиксирует UI model для presets, themes and wallpapers;
- явно описывает mapping `server appearance model -> UI tokens`;
- вводит predictable preview and optimistic update rules;
- отделяет persisted appearance state от purely local preview state.

---

## Что входит

- user appearance screen;
- board appearance screen;
- preset/theme/wallpaper model на уровне web UI;
- lightweight board preset registry на стороне frontend;
- mapping server model в CSS variables / UI flags;
- local preview rules;
- optimistic save behavior;
- базовая реальная реализация в web frontend.

## Что не входит

- глобальный theme engine для всех платформ на годы вперед;
- mobile-specific behavior;
- full sync/conflict semantics between devices for appearance;
- uploads for wallpaper assets;
- visual theme builder;
- workspace-level inheritance UI.

---

## Главный принцип

**Customization is a separate surface, not a mode of the board editor.**

То есть:

- board screen остается местом для работы с колонками и карточками;
- customization screen остается местом для настройки визуального поведения;
- board screen может отражать persisted board appearance, но не должен превращаться в form-heavy settings surface.

---

## Screen map

### 1. User appearance screen

Route:

- `/settings/appearance`

Purpose:

- app-level personal preferences;
- does not affect other workspace members;
- applies to the current web shell.

Contains:

- app theme selector: `system | light | dark`;
- density selector: `comfortable | compact`;
- reduce motion toggle;
- app preview card;
- save / reset actions;
- short rules block for preview/persistence semantics.

### 2. Board appearance screen

Route:

- `/workspaces/:workspaceId/boards/:boardId/customize`

Purpose:

- shared board-level appearance;
- owned by board state, not by user shell state;
- kept separate from the board editor itself.

Contains:

- theme preset picker;
- wallpaper kind selector;
- wallpaper value input / preset wallpaper selector;
- column density selector;
- card preview mode selector;
- display toggles:
  - show card description;
  - show card dates;
  - show checklist progress;
- board preview canvas;
- save / reset actions.

### 3. Board screen integration point

Route:

- `/workspaces/:workspaceId/boards/:boardId`

Role in customization:

- shows the persisted board appearance;
- provides navigation to board customization;
- is not the place where preview drafts are edited.

---

## UI model

### User appearance UI model

```ts
{
  appTheme: 'system' | 'light' | 'dark';
  density: 'comfortable' | 'compact';
  reduceMotion: boolean;
}
```

### Board appearance UI model

```ts
{
  themePreset: string;
  wallpaper: {
    kind: 'none' | 'solid' | 'gradient' | 'preset';
    value: string | null;
  };
  columnDensity: 'comfortable' | 'compact';
  cardPreviewMode: 'compact' | 'expanded';
  showCardDescription: boolean;
  showCardDates: boolean;
  showChecklistProgress: boolean;
  customProperties: Record<string, unknown>;
}
```

### Frontend preset registry

Frontend keeps a small local registry for known board presets. In the basic implementation it includes:

- `system`
- `midnight-blue`
- `forest-mint`
- `sunrise-coral`
- `plum-ink`

Important boundary:

- backend stores only `themePreset` string;
- frontend resolves that id to local token packs;
- the preset registry is presentation-aware and can resolve a light or dark token variant from the current app theme while keeping the same persisted preset id;
- unknown ids fall back to `system` instead of breaking rendering.

---

## Mapping: server model -> UI tokens

### User appearance

`/me/appearance` maps to root-level web shell tokens.

| Server field | Web mapping |
|---|---|
| `appTheme` | `document.documentElement.dataset.theme` |
| `density` | `document.documentElement.dataset.density` |
| `reduceMotion` | `document.documentElement.dataset.reduceMotion` |

Practical effect:

- `appTheme` switches global light/dark token sets;
- `density` changes paddings, layout gaps and control height;
- `reduceMotion` disables transition-heavy feedback.

### Board appearance

`/boards/{boardId}/appearance` maps to board-scoped variables and rendering flags.

| Server field | Web mapping |
|---|---|
| `themePreset` | resolved through local board preset registry, then mapped to light/dark token variant from current app theme |
| `wallpaper.kind/value` | background for `.board-themed-surface` and preview canvas |
| `columnDensity` | `--board-column-width` and tighter/looser column rendering |
| `cardPreviewMode` | compact vs expanded card tile rendering |
| `showCardDescription` | description visibility on board cards |
| `showCardDates` | date badges visibility |
| `showChecklistProgress` | preview flag reserved for card chips / future board UI |

Important boundary:

- board appearance overrides are scoped to the board surface and preview canvas;
- they do not redefine the whole app shell.

---

## Preview rules

### User appearance preview

User appearance preview is allowed to affect the current web shell immediately, but only as **purely local preview state** until Save.

Rule set:

1. User edits form values on `/settings/appearance`.
2. Draft values are pushed into a preview layer in memory.
3. Preview layer updates root datasets and therefore updates the current web shell.
4. Save persists the draft to `/me/appearance`.
5. Reset clears the local preview and restores persisted server state.

This gives a real “live preview” feeling without pretending the server has already accepted the change.

### Board appearance preview

Board appearance preview stays local to the board customization screen.

Rule set:

1. User edits board appearance form.
2. Draft is rendered into a dedicated preview canvas.
3. Draft does **not** temporarily hijack the real board editor screen.
4. Save persists the draft to `/boards/{boardId}/appearance`.
5. The actual board screen reflects the new appearance after the mutation settles.

Reason:

- board appearance is shared state;
- letting an unsaved local draft leak into the real board screen would blur the line between “preview for me” and “persisted for everyone”.

---

## Optimistic UX rules

### User appearance save

On Save:

- the client commits the new appearance into local persisted state immediately;
- the web shell already visually matches the draft because preview was active;
- pending sync status is shown separately from the appearance value itself;
- if the request fails, the operation becomes `failed/retryable` by default instead of forcing an immediate hard rollback;
- reset/refresh may later restore the last server-confirmed state if the user explicitly discards the failed local change.

### Board appearance save

On Save:

- the client commits the new board appearance into local persisted state immediately;
- the dedicated preview screen already matches the draft;
- board page can pick up the locally committed appearance before server confirmation;
- on failure, the operation moves into `failed/retryable` unless the UI explicitly chooses discard-and-rollback.

Important limitation for v1:

- optimistic behavior is only client-local;
- no multi-device sync semantics are implied here.

---

## Persisted vs purely local state

### Persisted state

Persisted state is what already lives in the client's durable local store and is either hydrated from or later confirmed by the backend:

- local persisted `me/appearance`;
- local persisted `board appearance`.

### Purely local preview state

Purely local preview state exists only in the current browser tab during editing.

Examples:

- unsaved user theme selection on `/settings/appearance`;
- unsaved wallpaper draft on board customization screen.

### Boundary rules

1. Local preview state never silently mutates backend state.
2. Board preview draft must not be treated as shared state until Save succeeds.
3. User preview draft may affect only the current shell session, not other devices or users.
4. Closing or resetting the screen may discard local preview state.
5. Successful Save moves the value from preview state into local persisted state even before server confirmation.

---

## Basic implementation plan

### Frontend structure

```text
frontend/
  src/
    app/
      providers/
        AppearanceProvider.tsx
    features/
      appearance/
        api/
          appearance.ts
        hooks/
          useAppearance.ts
        components/
          AppearancePreview.tsx
          PresetPicker.tsx
        pages/
          UserAppearancePage.tsx
          BoardAppearancePage.tsx
    shared/
      appearance/
        theme.ts
      types/
        api.ts
```

### Implemented integration points

- `AppearanceProvider` applies user appearance datasets to the root element;
- user appearance screen manages live local preview;
- board appearance screen renders a separate preview canvas;
- board screen consumes persisted board appearance and applies it to the board surface;
- routes and sidebar links expose both customization screens.

---

## Interaction rules to keep

### Do

- keep settings in dedicated screens;
- show visible preview before save;
- keep optimistic save local and reversible;
- map backend appearance strings to frontend token registries rather than storing token blobs in DB.

### Do not

- mix customization forms into the main board editing layout;
- let board draft preview hijack the real board before save;
- introduce asset upload workflow into this phase;
- overengineer a cross-platform theme engine here.

---

## Result of v1

After this step the web client has:

- a real user appearance screen;
- a real board appearance screen;
- a frontend preset registry for board themes;
- live local preview rules;
- optimistic save behavior;
- a clear boundary between personal appearance, shared board appearance and unsaved local drafts.
