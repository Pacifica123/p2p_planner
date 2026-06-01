# v1 execution roadmap and current truth surface

- Status: canonical planning snapshot after `development-principles-v2`
- Scope: current v1/beta readiness, next safe patches and release naming guardrails
- Supersedes: older blocker/stub notes in this file before the card enrichment, local-first, sync, export and auth-hardening slices were closed
- Related docs: `docs/development/development-planning-and-engineering-principles-v2.md`, `docs/product/v1-remaining-checklist.md`, `docs/product/v1-known-limitations.md`, `docs/product/beta-scope-v1.md`, root `README.md`

This document is not an aspirational architecture map. It is the active answer to:

```text
What can we honestly say is implemented now, what remains partial, and what should the next patch prove?
```

## Planning decision

The next development path should not start with another product feature. The project already closed several product/runtime baselines in a row: card enrichment, local-first runtime, sync baseline, export safety net and auth/security hardening. Under the v2 principles this creates a truth/evidence checkpoint.

Path from here:

1. **Truth-sync checkpoint** — align active docs so old blocker labels no longer drive planning. This is the first patch on the path.
2. **Release evidence checkpoint** — make `release-gates`/UIX prove the real backend browser path and repeatable smoke assumptions, or classify remaining prerequisites honestly.
3. **Beta hardening slices** — only after the evidence checkpoint, choose the next narrow product/safety slice: account-management/auth UX hardening or import-as-copy execution after preview.
4. **Release review** — update release notes/known limitations after the gates produce a trustworthy bundle.

Outcome for this truth-sync patch:

```text
After the patch, active docs agree that labels/checklists/comments, local-first runtime, sync baseline, export backup preview and auth/security hardening are baseline-implemented, while release-gates evidence, invite-grade auth/account UX and destructive/non-destructive import execution remain the next decision points.
```

## Status vocabulary

| Status | Meaning |
| --- | --- |
| `Done baseline` | The v1 slice is implemented enough for the declared beta path and has source-level evidence, but may still have known v1 limitations. |
| `Partial` | A useful slice exists, but release confidence or product semantics are not complete enough to treat as fully closed. |
| `Needs evidence` | Code/docs suggest the path exists, but the next patch must prove it with the appropriate gate before dependent work continues. |
| `Deferred` | Intentionally post-v1 or future-ready only. It must not be presented as a ready user feature. |
| `Out of v1` | Not part of the v1 release promise. |

## Current v1 truth table

| Area | Status | Current truth | v1 decision |
| --- | --- | --- | --- |
| Auth/session | `Partial` | Sign-up/sign-in/refresh/session/sign-out/sign-out-all exist; beta profile guards restrict dev-header auth, default secrets and CORS/cookie posture. | Keep in beta-local path. Next hardening is account-management/invite-preview UX and release evidence, not basic auth existence. |
| Workspace/board/column/card core CRUD | `Done baseline` | Main web flow supports workspace, board, columns, cards, card drawer edits, archive/delete semantics, move/reorder and activity-visible mutations. | Keep as core v1 path and protect with release-gates/UIX evidence. |
| Card details enrichment | `Done baseline` | Labels, checklists and comments are no longer `not_implemented` stubs: backend CRUD/assignment flows, OpenAPI `real_v1` markers and `CardDetailsDrawer` UI exist. | Keep in v1 path. Known limitation: labels/checklists/comments for a locally-created unsynced card unlock after that card syncs. |
| Appearance/customization | `Done baseline` | User appearance and board appearance have backend/frontend/API wiring and smoke/integration context. | Keep in v1 path. Uploaded wallpapers and arbitrary theme editor remain out of v1. |
| Activity/history/audit | `Done baseline` | Board activity, card activity and workspace audit log exist; core mutations and card enrichment events write user-facing history/audit entries. | Keep in v1 path. Rich diff/compliance dashboard remains post-v1. |
| Local-first runtime | `Done baseline` | Frontend has persistent board snapshot, pending card operations queue, warm/offline read, offline card edits and visible `synced/pending/failed` states for core entities. | Keep as v1 baseline, not as final sync architecture. IndexedDB replacement and richer local model remain future hardening. |
| Sync baseline | `Done baseline` | Backend registers replicas, accepts idempotent push events, exposes pull by cursor and records tombstone-aware core delete/archive events; frontend has visible sync baseline state. | Keep as backend-coordinated sync baseline. Full P2P, merge UI and automatic projection replay are not v1 promises. |
| Export / backup safety net | `Partial` | Board/workspace backup export returns a versioned application-level JSON bundle; import preview validates manifest and stays non-destructive. | Keep export and preview in v1. Do not promise destructive restore. Import-as-copy execution is a later slice if selected. |
| Integrations/webhooks | `Deferred` | Provider registry and webhook/import/export job boundaries exist mostly as adapter/stub surfaces. | Do not market as user-ready v1 integrations. |
| Release gates / UI evidence | `Needs evidence` | `devbootstrap release-gates`, managed runtime/test DB and UIX gates exist, but the next release-relevant fact must be proven through a current real-backend evidence run. | Next practical safety patch should make the real backend browser path and repeatability status explicit. |
| P2P / relay / bootstrap | `Out of v1` | Architecture remains future-ready; no mandatory user-facing p2p runtime is promised for v1. | Do not block v1 on full p2p. |
| Mobile | `Out of v1` | Native mobile is a later product line after web/local-first/sync stabilization. | Do not include in v1 gates. |

## Current manual happy path

The current realistic manual path is:

1. start PostgreSQL/backend/frontend;
2. sign up or sign in;
3. create workspace;
4. create board;
5. create columns;
6. create cards;
7. open card details drawer;
8. edit title/description/status/priority/dates;
9. move/reorder cards;
10. use labels/checklists/comments;
11. view card history and board activity;
12. change user/board appearance;
13. use local-first visible states during core card work;
14. download board-level backup bundle;
15. run import preview without destructive restore.

Do not present these as finished v1 user promises without release evidence:

- real-backend browser release gate for the full happy path;
- invite-grade auth/account-management UX;
- import-as-copy/apply execution;
- full conflict-resolution UI;
- p2p/relay/bootstrap runtime;
- integrations/webhook delivery.

## API/OpenAPI contract notes

Current OpenAPI already marks the implemented labels/checklists/comments/sync/import-export paths as `real_v1` where applicable. The route inventory should now be treated as follows:

- core CRUD, appearance, activity/audit, labels/checklists/comments and sync baseline routes are active v1 surfaces;
- import/export backup creation and import preview are active preview/safety-net surfaces;
- import execution is a non-destructive boundary until a later import-as-copy slice proves mutation behavior;
- legacy import/export jobs, provider registry and webhooks are adapter/future surfaces;
- raw `not_implemented` responses for declared v1 user features should be treated as regressions, not as expected baseline behavior.

## Remaining release blockers and decision points

### Blocker before release confidence

- A current `release-gates`/UIX bundle must prove or honestly classify backend smoke, frontend build/unit, browser boot and real-backend browser path.
- Smoke/idempotency assumptions must not rely on dirty shared dev state.
- README, known limitations and release notes must match the final gate result.

### Decision points after release evidence

- Whether `beta-local-self-host` is enough for the first beta, or whether `beta-invite-preview` hardening is required first.
- Whether import preview is sufficient for v1, or whether import-as-copy execution must be implemented before release.
- Whether remaining Playwright scripts stay as legacy optional coverage or are retired after UIX parity is accepted.

## Next safe patch

The next patch after this truth-sync update should be a **safety/evidence patch**, not another broad feature patch.

Recommended verified fact:

```text
After the patch, release-gates can prove the real backend browser core flow against a managed runtime/test DB, or the report classifies every missing prerequisite without counting it as product success.
```

Cheapest sufficient evidence for that patch:

- `python -B tools/devbootstrap.py release-gates --dry-run` for plan shape;
- targeted `release-gates` profile with managed runtime/test DB if the environment supports it;
- UIX scenario report for the real backend core flow, or an explicit prerequisite classification if browser/runtime dependencies are absent.

## Release naming guardrail

```text
v1.0.0-beta.1        -> fair only after current release evidence proves web core + card enrichment + local-first baseline + sync baseline + export safety net.
v1.0.0-web-preview.1 -> use if release evidence cannot prove local-first/sync/export as user-relevant beta facts.
```
