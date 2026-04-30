# Project State

Этот файл — пример короткого state-среза проекта. Его задача: быстро вернуть человека и ассистента в актуальный контекст без перечитывания всех больших документов.

## Current source of truth

**Repository:** `p2p_planner`  
**Main branch:** `main`  
**Current phase:** `v1 release preparation`  
**Current workflow:** assistant-generated manifest patches + local patch conveyor  
**Latest stable commit:** `abc1234`  
**Latest stable archive:** `archives/20260430_231502_release-workflow_7f3a9c/post_p2p_planner_20260430_231502_after_release-workflow_abc1234.zip`

## Current workspace layout

Expected local workspace:

```text
p2p_workspace/
  patches/
  archives/
  p2p_planner/
    backend/
    frontend/
    docs/
    tools/
```

`archives` is the preferred spelling. A compatibility alias for `arhives` may be supported by tooling, but new work should use `archives`.

## Ready / implemented

- Core backend CRUD for workspace, board, column, card.
- Web core UI for workspace/board/card flow.
- Appearance/customization backend and UI basis.
- Activity/history/audit backend surface.
- Auth layer exists, but docs and legacy references may still require cleanup.
- Testing strategy draft exists.
- Deployment/packaging discussion exists, but implementation and release flow need stabilization.

## Current focus

Build the development conveyor before pushing deeper into v1 release work.

Immediate focus:

1. document patch manifest format;
2. implement `tools/devctl.py` v0;
3. make patch application reproducible;
4. reduce multi-machine sync mistakes;
5. make GitHub the practical source of truth after every successful run.

## Active risks

- Manual patch/archive routine is easy to forget or misorder.
- Local machines can drift if commit/push/pull discipline fails.
- Patch archives currently express changed files, but not deletions unless manifest supports them.
- Some checks depend on tools that may not be installed globally.
- Frontend checks may invoke `npx`/Playwright and require environment preparation.
- Windows/Linux behavior must be handled carefully.
- Legacy `X-User-Id` and older docs may still be inconsistent with current auth direction.

## Current development rule

Before starting work on any machine:

```bash
python tools/devctl.py status
```

To apply the newest patch and run the conveyor:

```bash
python tools/devctl.py start
```

The conveyor may apply a patch only from a clean and synced Git state.

## Release v1 intent

v1 release should prioritize a stable, usable, demonstrable product over new conceptual expansion.

v1 should not be blocked by:

- full mobile app;
- complete p2p sync;
- perfect desktop packaging;
- every possible integration.

v1 should be blocked by:

- broken core CRUD flow;
- broken frontend happy path;
- impossible local setup;
- unclear release instructions;
- known data-loss risks in normal use;
- untracked state drift between machines.

## Next best action

Implement `devctl` v0 as a pure-Python patch conveyor with `status` and `start` commands.

## Parking lot

Ideas that matter but should not derail current focus:

- cross-platform packaging: exe/AppImage first, apk later;
- mobile UX and local-first mobile storage;
- p2p/relay production hardening;
- richer automatic environment setup;
- service auto-start for backend/frontend smoke tests.
