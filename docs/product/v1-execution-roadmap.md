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

1. **Truth-sync checkpoint** — done; active docs no longer let old blocker labels drive planning.
2. **Release evidence checkpoint** — done for the first accepted run: `full-local-release` on 2026-06-04 passed with UIX real-backend product-path evidence.
3. **Repeatability checkpoint** — rerun the same profile and inspect `remediation/repeatability-loop.*`; the current hard cap is `repeatability-not-proven`.
4. **Beta hardening slices** — only after the repeatability decision, choose the next narrow product/safety slice: account-management/auth UX hardening or import-as-copy execution after preview.
5. **Release review** — update release notes/known limitations after the gates and repeatability decision produce a trustworthy bundle.

Outcome after the first evidence checkpoint:

```text
Active docs agree that labels/checklists/comments, local-first runtime, sync baseline, export backup preview and auth/security hardening are baseline-implemented. The 2026-06-04 full-local-release run proved the preferred UIX real-backend product path and moved the next release blocker from missing evidence to repeatability. Invite-grade auth/account UX and import-as-copy execution remain product decision points after repeatability.
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
| Release gates / UI evidence | `Partial` | `full-local-release` passed on 2026-06-04 with managed DB/runtime, backend smoke twice, frontend build/unit, UIX mocked core flow, UIX real-backend core flow, legacy browser smoke and clean-machine sandbox. Score `89/100`; raw class `beta_candidate`, effective class `internal_candidate`. | Real-backend product-path evidence is accepted. External beta remains capped by `repeatability-not-proven`; rerun the same profile before beta naming. |
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

Do not present these as finished v1 user promises beyond the accepted evidence:

- repeatability across same-profile `full-local-release` runs;
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

### Remaining blocker before external beta confidence

- Repeatability is not yet proven at the accepted threshold: the 2026-06-04 scorecard is capped by `repeatability-not-proven`.
- README, known limitations and release notes must match the final repeatability/beta decision.

### Decision points after release evidence

- Whether `beta-local-self-host` is enough for the first beta, or whether `beta-invite-preview` hardening is required first.
- Whether import preview is sufficient for v1, or whether import-as-copy execution must be implemented before release.
- Whether remaining Playwright scripts stay as legacy optional coverage or are retired after UIX parity is accepted.

## Next safe patch

The next patch after the accepted 2026-06-04 evidence checkpoint should be a **repeatability evidence patch**, not another broad feature patch.

Recommended verified fact:

```text
A second same-profile `release-gates --profile full-local-release` run either lifts the repeatability hard cap or produces a precise unstable family to fix.
```

Cheapest sufficient evidence for that patch:

- rerun `python tools/devbootstrap.py release-gates --profile full-local-release` from the same source state;
- inspect `release-confidence-gate.md` and `remediation/repeatability-loop.*`;
- update release notes/known limitations only after the repeatability decision is clear.

## Release naming guardrail

```text
v1.0.0-beta.1        -> fair only after the accepted evidence checkpoint also has repeatability or an explicit decision accepting the cap.
v1.0.0-web-preview.1 -> use if repeatability or beta-profile hardening stays insufficient for external beta naming.
```
