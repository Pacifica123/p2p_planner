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
2. **Release evidence checkpoint** — completed on 2026-06-04: `release-gates --profile full-local-release` passed `Overall: ok`, including UIX mocked and real-backend core flows.
3. **Beta.2 release-prep** — current step: prepare GitHub Pre-release notes and platform artifact contract for Windows `.exe` bundle and Linux AppImage.
4. **Repeatability checkpoint** — rerun the same profile after release-prep; stable `v1.0.0` remains blocked until repeatability evidence is accepted.
5. **Beta hardening slices** — after beta.2 release prep, choose one narrow product/safety slice: account-management/auth UX hardening or import-as-copy execution after preview.

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
| Release gates / UI evidence | `Done baseline` | `release-gates --profile full-local-release` passed on 2026-06-04 with managed DB/runtime, backend smoke twice, frontend build/tests, UIX mocked flow, UIX real-backend core flow, browser smoke and clean-machine sandbox. | Use as beta.2 release evidence. Stable release still needs repeatability evidence. |
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

### Blocker before stable release confidence

- The current release-evidence blocker is lifted for beta.2 by `20260604_050815_release-gates`.
- The active hard cap is now `repeatability-not-proven`; rerun the same `full-local-release` profile after release-prep.
- README, known limitations, release notes and platform artifact docs must match the final gate result.
- Every uploaded Windows/Linux release artifact needs artifact-level smoke, not only source-level gates.

### Decision points after beta.2 release-prep

- Whether another repeatability run is enough for publishing `v1.0.0-beta.2`, or whether artifact-level smoke reveals packaging defects first.
- Whether `beta-local-self-host` remains the release profile, or whether `beta-invite-preview` hardening is required for the next beta.
- Whether import preview is sufficient for v1, or whether import-as-copy execution must be implemented before a later release.
- Whether remaining Playwright scripts stay as legacy optional coverage or are retired after UIX parity is accepted.

## Next safe patch

The next patch after the accepted release-evidence checkpoint should be a **release-prep patch**, not another broad feature patch.

Recommended verified fact:

```text
After the patch, active docs and release templates agree that the next GitHub release line is v1.0.0-beta.2 and that required assets are a Windows self-host executable bundle, a Linux x86_64 AppImage, SHA256SUMS and the final release-gates evidence bundle.
```

Cheapest sufficient evidence for that patch:

- docs sanity check for `v1.0.0-beta.2` naming;
- artifact contract check for Windows `.exe` bundle and Linux `.AppImage`;
- repeat `python tools/devbootstrap.py release-gates --profile full-local-release` after release-prep changes.

## Release naming guardrail

```text
v1.0.0-beta.2        -> current target; beta.1 already existed, and current evidence proves web core + card enrichment + local-first baseline + sync baseline + export safety net.
v1.0.0-beta.2-prep   -> acceptable local working name before platform artifacts are smoke-tested and uploaded.
v1.0.0-web-preview.* -> fallback only if repeatability or artifact smoke invalidates beta packaging claims.
```
