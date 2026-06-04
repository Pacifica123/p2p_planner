# Документация проекта P2P Planner

Этот каталог фиксирует текущие архитектурные, продуктовые и release/dev решения проекта web-first local-first Kanban planner.

## Как читать

1. Product baseline:
   - `product/v1-execution-roadmap.md`
   - `product/mvp-scope-v1.md`
   - `product/beta-scope-v1.md`
   - `product/v1-known-limitations.md`
   - `product/release-evidence-checkpoint-2026-06-04.md`
   - `product/v1.0.0-beta.2-release-notes.md`
   - `product/v1.0.0-beta.2-release-artifacts.md`
2. Domain and sync vocabulary:
   - `domain/`
   - `sync/`
   - `adr/`
3. Architecture:
   - `architecture/project-structure.md`
   - `architecture/backend-modules.md`
   - `architecture/database-structure-v2.md`
   - `architecture/auth-and-identity-v1.md`
   - `architecture/activity-history-audit-v1.md`
   - `architecture/appearance-customization-v1.md`
   - `architecture/local-first-data-layer-v1.md`
   - `architecture/sync-model-implementation-plan-v1.md`
   - `architecture/conflict-resolution-v1.md`
   - `architecture/testing-strategy-v1.md`
4. API contract:
   - `api/openapi.yaml`
5. Local dev automation:
   - `dev-bootstrap/dev-autodeployer-manifesto.md`
   - `dev-bootstrap/dev-autodeployer-v1-development-plan.md`
   - `dev-bootstrap/devbootstrap-v1-operations.md`
   - `dev-bootstrap/devbootstrap-v2-release-gates-plan.md`
   - `dev-bootstrap/release-gates-test-database.md`
6. Stabilization and development process:
   - `development/development-planning-and-engineering-principles-v2.md`
   - `development/release-stabilization-program-v1.md`
   - `development/systemic-release-stabilization-manifesto-v1.md`
   - `development/release-stabilization-problem-ledger.md`
   - `development/release-confidence-scorecard-v1.md`
   - `development/release-stabilization-profile-side-effects-v1.md`
   - `development/custom-uiux-evidence-manifesto-v1.md`
   - `development/custom-uiux-evidence-runner-development-plan-v1.md`
   - `development/custom-uiux-evidence-runner-implementation-v1.md`
   - `development/documentation-weight-budget-v1.md`

## Current decisions

| Area | Decision |
|---|---|
| Product | MVP is web-first Kanban with workspaces, boards, columns, cards, labels/checklists/comments, appearance, activity/audit and backup/export preview surface. |
| Current v1 status | Read `product/v1-execution-roadmap.md` first; it is the active truth surface for done/partial/deferred/out-of-scope status. |
| Local-first | Local-first runtime and backend-coordinated sync are baseline-implemented for core web flow; `20260604_050815_release-gates` proved the beta.2 real-backend product path, while stable release still needs repeatability evidence. |
| P2P | Future-ready, not mandatory for v1 release. |
| Development planning | Current mode is verified product acceleration: one user/release/truth fact per patch, cheapest sufficient evidence, no ownerless debt. |
| Devctl | Patch conveyor applies small reproducible devctl patches, not full project archives. |
| Devbootstrap | Project-owned diagnostic/release-gates tool; generated `.dev-bootstrap` artifacts are not source. |
| Release gates | Evidence-first bundle with ledgers, classifications, confidence gate and regression memory; current beta.2 checkpoint passed `full-local-release` with effective cap `repeatability-not-proven`. |
| UI evidence | Playwright is legacy transition; target is custom lightweight UI/UX Evidence Runner. |
| Documentation size | Long manifestos are compacted after decisions are accepted; source archives should stay small. |

## Important commands

```bash
python -B tools/devbootstrap.py self-check --no-write-report
python -B tools/devbootstrap.py diagnose --no-write-report
python -B tools/devbootstrap.py release-gates --dry-run
python -B tools/devbootstrap.py release-gates --profile diagnostic --prepare-deps
python -B tools/devbootstrap.py release-gates --managed-test-db --managed-runtime --prepare-deps
```

## Artifact policy

Keep in source:

- architecture/product/process docs;
- source code;
- migrations;
- OpenAPI;
- examples and stable fixtures.

Keep out of source snapshots:

- `.dev-bootstrap/` generated runs and state;
- `node_modules/`, `target/`, `dist/`, `build/`;
- logs, caches, bytecode;
- env files and secrets;
- large release/browser/test artifacts.

Release-gates bundles should be shared separately when diagnosing a run.
