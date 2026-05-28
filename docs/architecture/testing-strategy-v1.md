# Testing strategy v1

## Goal

Provide enough automated evidence to decide whether the project is releasable without confusing product regressions with local environment noise.

## Principles

1. Use several small signals instead of one magical end-to-end test.
2. Keep write-capable checks isolated from shared dev state.
3. Preserve reproducible logs and inputs.
4. Classify infra blockers separately from product failures.
5. Prefer deterministic fixtures and explicit user-facing scenarios.

## Layers

| Layer | Purpose | Typical command |
|---|---|---|
| Backend unit/integration | Domain/repo/service correctness. | `cd backend && cargo test` |
| Backend DB integration | Migration/query behavior against disposable DB. | `TEST_DATABASE_URL=... cargo test -- --ignored` |
| Backend smoke | API works as a running service. | `python backend/tests/smoke_core_api.py` via devbootstrap. |
| Frontend build | TypeScript/Vite/import graph. | `cd frontend && npm run build` |
| Frontend unit/integration | Component and state logic. | `cd frontend && npm run test:run` |
| UI/UX evidence | User can open UI and complete critical flow. | Target: custom evidence runner. Legacy: Playwright. |
| Release-gates | Bundle all relevant checks and decisions. | `python -B tools/devbootstrap.py release-gates ...` |

## Mandatory v1 evidence

Before release review:

- `self-check` OK;
- `diagnose` OK or non-blocking warnings only;
- backend cargo default gate OK/accepted partial with DB ignored coverage;
- DB ignored/integration tests run against disposable DB or explicitly deferred;
- backend Python smoke runs twice against isolated runtime/DB;
- frontend build OK;
- frontend unit/integration OK;
- UI/UX critical flow evidence exists;
- docs/release notes/known limitations gates OK;
- clean-machine dry signal collected for final review.

## UI/UX testing direction

Playwright is not the long-term mandatory browser layer. The project will replace it with a lightweight custom UI/UX Evidence Runner that uses a system browser and captures:

- DOM boot proof;
- console/runtime errors;
- route markers;
- visible/enabled controls;
- form interactions;
- network/backend evidence;
- localStorage/sessionStorage before/after state;
- concise JSON/Markdown reports.

Playwright tests may remain only as transitional or optional heavy checks until parity is achieved.

## Fixtures

- Backend tests create disposable IDs/data and clean up where practical.
- Smoke tests must not assume a fixed shared user starts with default mutable preferences.
- UI tests should use stable `data-testid` markers for critical controls.
- Real-backend UI scenarios must run against managed runtime/test DB, not an arbitrary local backend.

## Quality gates by cadence

| Cadence | Required checks |
|---|---|
| Small patch | Syntax + affected unit tests + relevant self-check. |
| Backend patch | Cargo relevant tests + API smoke when runtime behavior changed. |
| Frontend patch | Build + unit/integration + UI evidence if flow changed. |
| Release candidate | Full release-gates profile with managed DB/runtime and clean-machine dry. |

## Anti-patterns

- using `--allow-dev-db-write` as the default path;
- treating missing browser binaries as UI regression;
- committing generated `.dev-bootstrap` evidence;
- expanding one browser test into a hidden product test suite;
- accepting `REL-UNMAPPED` as stable.
