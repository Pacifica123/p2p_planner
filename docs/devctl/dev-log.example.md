# Development Log

Этот файл — пример журнала разработки. Он не заменяет Git history, а дает человеческое объяснение: что делали, зачем, какие проверки прошли и что дальше.

## 2026-04-30 — Release workflow automation

**Patch:** `2026-04-30-release-workflow`  
**Patch archive:** `patch_20260430_231502_release-workflow.zip`  
**Patch SHA-256:** `example-7f3a9c...`  
**Commit:** `abc1234`  
**Commit message:** `chore(dev): add release workflow automation`  
**Status:** `applied`  
**Archive folder:** `archives/20260430_231502_release-workflow_7f3a9c/`

### Goal

Добавить операционный слой для разработки патчами: project state, dev-log, manifest-based patch format и будущий `devctl` patch conveyor.

### Changed

- Added `docs/project-state.md` as current project cockpit.
- Added `docs/dev-log.md` as human-readable development journal.
- Added `docs/release-workflow.md` describing patch workflow.
- Added `tools/devctl.py` skeleton.
- Added example patch manifest format.

### Checks

| Check | Result | Log |
|---|---:|---|
| `cargo check` | pass | `logs/backend-cargo-check.log` |
| `npm run build` | pass | `logs/frontend-build.log` |
| `python tests/smoke_core_api.py` | skipped | backend service was not auto-started in v0 |

### Result

Development workflow became more reproducible. The project now has a documented path for applying assistant-generated patches with backup, checks, archives, commit and push.

### Notes

- v0 does not auto-start backend/frontend services.
- v0 does not auto-install frontend or Python test dependencies.
- Future version should add manifest `setup` and `services` sections.

### Next best action

Create `release-v1-gate.md` and define what blocks the real v1 release.

---

## 2026-05-01 — Example failed run

**Patch:** `2026-05-01-browser-smoke-runner`  
**Patch archive:** `patch_20260501_101500_browser-smoke-runner.zip`  
**Patch SHA-256:** `example-bad91e...`  
**Commit:** none  
**Status:** `failed`  
**Archive folder:** `archives/20260501_101500_browser-smoke-runner_bad91e/`

### Goal

Add browser smoke checks to the patch conveyor.

### Changed

- Applied files from patch.
- No commit was created because checks failed.

### Checks

| Check | Result | Log |
|---|---:|---|
| `npm run test:browser` | fail | `logs/frontend-browser-smoke.log` |

### Failure summary

Browser smoke failed because Playwright browsers were not installed in the local environment.

### Result

The working tree was left dirty for analysis. A failed-state archive was created. Push was not attempted.

### Next best action

Add explicit manifest setup step for Playwright installation or keep browser smoke as manual until service/setup support exists.
