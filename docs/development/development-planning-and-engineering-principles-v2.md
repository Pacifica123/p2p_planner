# Development planning and engineering principles v2

- Status: canonical working strategy for the next development iterations
- Scope: project-specific planning and implementation principles for `p2p_planner`
- Supersedes: `docs/development/accelerated-development-strategy-v1.md` for day-to-day planning
- Related docs: `docs/product/v1-execution-roadmap.md`, `docs/product/v1-known-limitations.md`, `docs/development/custom-uiux-evidence-runner-implementation-v1.md`, `docs/development/release-stabilization-program-v1.md`, `docs/README.md`

## 1. Decision

The project is no longer mainly proving that patches can be delivered.
`devctl`, `devbootstrap`, release-gates, managed DB/runtime and UIX evidence already form the basic conveyor.

Current phase:

```text
Verified product acceleration
```

Meaning:

```text
Move faster by turning existing backend/domain/tooling surface into verified user facts,
while every discovered risk gets an explicit fate before the next dependent patch.
```

A good patch:

```text
one new truth + cheapest sufficient evidence + no ownerless debt
```

## 2. What changed since accelerated-development-strategy-v1

The v1 strategy remains valid for devctl discipline:

- ship reproducible patch archives, not full project zips;
- keep each patch meaningful and checkable;
- avoid hidden manual steps;
- leave a transferable clean state after success.

The new planning unit is stricter.

Old default question:

```text
Can this patch safely pass through devctl?
```

New default question:

```text
Which user-visible, release-relevant or truth-sync fact becomes verified after this patch?
```

So v2 adds:

- product/safety/truth-sync/cleanup lanes;
- evidence budget selected from the main risk;
- fate policy for every discovered issue;
- source-of-truth stack for documentation drift;
- stop/go rules to avoid both reckless feature pushing and endless tooling epics.

## 3. Current project baseline for planning

Use this baseline when choosing the next patch:

- product shape: web-first Kanban around `workspace -> board -> column -> card`;
- active surfaces: auth/session, appearance, activity/audit, export/backup, local-first/sync and card enrichment;
- evidence shape: `devbootstrap release-gates` produces the main bundle;
- UI evidence direction: project-owned UIX evidence replaces generic framework confidence where Playwright lifecycle becomes noise;
- generated runtime artifacts under `.dev-bootstrap/` are not source truth;
- old phase docs are historical unless the docs index marks them as current.

Planning implication:

```text
When README, latest runtime evidence and code disagree with an older roadmap or phase doc,
the older doc is suspect until a truth-sync patch updates or deprecates it.
```

Do not plan from stale status labels alone. Verify the affected area against code, smoke/UIX evidence and current docs index.

## 4. Unit of work: verified fact

Before implementation, state the outcome as:

```text
After this patch it is true that <specific observable fact>.
```

Good examples:

- a user can create a checklist item in the card drawer and see it after reload;
- a user can export a board backup bundle and open a non-destructive import preview;
- UIX proves `sign-in -> workspace -> board -> card` against managed runtime;
- release-gates classify missing browser binaries as environment prerequisite, not frontend regression;
- `v1-execution-roadmap.md` no longer contradicts root `README.md` for local-first/sync/export status.

Bad examples:

- improve frontend;
- stabilize release;
- clean docs;
- finish sync;
- polish UX.

## 5. Work item card

Every non-trivial patch should have this card in `PATCH_SUMMARY.md`, an issue or the chat request:

```text
Outcome:
Lane:
Patch type:
Main risk:
Evidence budget:
Truth surfaces touched:
Out of scope:
Allowed deferred issues:
Stop condition:
```

Interpretation:

- `Outcome` is the one verified fact.
- `Lane` is product, safety, truth-sync or cleanup.
- `Main risk` is the thing that would hurt later if we were wrong.
- `Evidence budget` is the cheapest check set that proves this patch.
- `Truth surfaces touched` are docs/contracts/tests that must move with the code.
- `Out of scope` prevents expansion by “one more small thing”.
- `Allowed deferred issues` lists only explicitly safe limitations/probes.
- `Stop condition` says when the patch is done and must stop growing.

## 6. Lanes

| Lane | Goal | Examples | Rule |
| --- | --- | --- | --- |
| Product | deliver user-visible facts | card details, labels/checklists/comments, local-first status, sync status, backup/import preview, auth/account UX, appearance, activity UI | add only the safety/tooling needed to prove this slice |
| Safety | keep product acceleration honest | release-gates classification, managed DB/runtime, smoke idempotency, UIX coverage, auth negative checks, migration lifecycle, regression memory | justified when it speeds next product patches or prevents plausible blockers |
| Truth-sync | align code/runtime/docs/contracts | roadmap refresh, known limitations, README commands, OpenAPI route semantics, old-doc deprecation | blocking when drift changes what to build or release next |
| Cleanup/retirement | remove costly noise | Playwright optionalization after UIX parity, stale scripts/configs, doc compaction, duplicated bootstrap paths | must reduce future evidence cost, ambiguity or operational risk |

## 7. Evidence budget v2

Choose checks from the main risk, not from habit.

| Patch type | Main risk | Minimum evidence | Escalate when |
| --- | --- | --- | --- |
| Docs-only | docs become dangerous, stale or misleading | markdown sanity + referenced-file review | startup/release/security policy changes |
| Devctl/tooling | patch cannot apply or check creates junk | Python `ast.parse`, devctl `plan` on temp workspace | apply/delete/archive/check semantics change |
| Devbootstrap/runtime | side effects, teardown, wrong classification | self-check/dry-run + targeted gate | managed DB/runtime/consent boundary changes |
| Backend domain/API | route/schema/migration/auth/data regression | affected Rust/Python smoke + route review | migrations, auth, permissions or data-loss boundary change |
| Frontend product UI | UI renders but user path fails | build/unit + affected UIX scenario | critical route/state/form flow changes |
| Contract parity | backend/frontend/OpenAPI disagree | route inventory + targeted smoke | public API/generated client changes |
| Release candidate | false release confidence | full managed release-gates + UIX real backend | release review only |

Evidence ladder:

```text
syntax/contract -> affected unit/smoke -> managed runtime evidence -> full release-gates
```

If a cheap signal is red, stop and fix/classify that signal before running more expensive gates.

## 8. Engineering principles

1. **Implement vertically, not blindly.** A product slice should include the minimum backend/frontend/docs/test wiring needed for one user path. It must not present a stub as finished.
2. **Align touched contracts.** If API shape changes, update the affected backend route, frontend client/call site, OpenAPI path/schema and smoke/UIX evidence when user-visible.
3. **Keep smoke idempotent.** Shared dev DB checks must not assume clean state unless they create and own that state. Use managed test DB or isolated identifiers when needed.
4. **Respect lifecycle-sensitive state.** Migration embedding, dependency markers, runtime PIDs, ports, DB names and browser profiles need lifecycle evidence or honest environment/tooling classification.
5. **Make UI evidence behavior-first.** UIX should prove browser opens, React boots, route works, controls are actionable and state/API effects are visible.
6. **Keep patches narrow in risk class.** Avoid product feature + release-gates redesign, migration + auth rewrite + UI polish, docs rewrite + runtime behavior change.

## 9. Problem fate policy

Every discovered problem gets exactly one fate.

| Fate | Use when | Required record |
| --- | --- | --- |
| Fix now | breaks main path, data, auth/security, migration, devctl apply or release evidence | patch fixes it and updates evidence |
| Quarantine | feature is not in current scope or is unsafe to expose | hidden/flagged surface + exit trigger |
| Known limitation | risk is understood and safe for current scope | limitation text + user-visible impact + exit trigger |
| Probe | cause is unknown and blind fix would be risky | signal to collect + escalation trigger |
| Environment noise | failure is not product code | classifier/notes + next action |
| Retire/optionalize | check layer creates more noise than confidence | parity replacement or explicit optional status |
| Truth-sync | docs/contracts disagree and affect planning/release | updated canonical doc or deprecation note |

Deferred does not mean forgotten.

Record non-fixed issues like this:

```text
Known limitation / Probe / Quarantine:
- ID:
- Surface:
- What is limited or unknown:
- Why safe for this scope:
- User-visible impact:
- Evidence location:
- Exit trigger:
```

## 10. Definition of safely ignored

A problem may be temporarily ignored only if all are true:

- it does not break the declared outcome;
- it does not risk data loss/corruption;
- it does not weaken auth/security/privacy boundaries;
- it does not make release-gates falsely green;
- it does not show a stub/preview as finished;
- it does not change the next decision through README/current-state conflict;
- it has an exit trigger and is written down.

A problem must not be ignored if smoke is green only because of dirty shared state, skipped/unknown is counted as green, migrations can desync from embedded lists, cleanup can remove non-owned data/processes, docs recommend dangerous commands, or production-like startup can use dev secrets/wildcard CORS/legacy dev auth by accident.

## 11. Source-of-truth stack

Use sources in this order when planning:

| Level | Source | What it proves |
| --- | --- | --- |
| 1 | latest relevant runtime evidence | what actually passed |
| 2 | code, migrations and tests | what is implemented |
| 3 | root README and docs index | current human entry point |
| 4 | v1 roadmap and known limitations | release scope and promises |
| 5 | OpenAPI | external API contract if parity is fresh |
| 6 | ADR/architecture docs | rationale and constraints |
| 7 | old phase/strategy docs | historical context only |

Suspect-doc rule:

```text
If an older doc contradicts newer runtime evidence, code or README,
do not use it for release or roadmap decisions until a truth-sync patch resolves the conflict.
```

## 12. Cadence

Default rhythm:

```text
product -> product -> safety/truth-sync
```

Continue product work when previous outcome is verified, affected evidence is green or honestly classified, unknown ratio on the main path did not increase, no new data/auth/security/migration danger appeared, and docs drift does not change the next decision.

Switch to safety/truth-sync when the same failure family repeats, smoke becomes non-idempotent, release-gates misclassifies product vs environment risk, README/roadmap/code answer “what is ready?” differently, full release review is no longer reproducible, or evidence cost grows faster than product value.

## 13. Stop/go rules

Go to the next product slice only when:

- the declared outcome is true;
- evidence budget has run or limitations are explicit;
- every new issue has a fate;
- main path confidence did not decline;
- no hidden manual steps were added;
- touched truth surfaces are updated.

Stop and stabilize when it is unclear what is true, a green check does not prove the user path, deferred issues lack exit triggers, tool noise hides product risk, project startup again requires manual guessing, or old docs are driving decisions after newer evidence superseded them.

## 14. Project-specific planning queue shape

This is not a full roadmap. It is the preferred shape for upcoming patches.

### First truth-sync target

Align the active truth surfaces before major dependent planning:

- root `README.md`;
- `docs/README.md`;
- `docs/product/v1-execution-roadmap.md`;
- `docs/product/v1-known-limitations.md`;
- OpenAPI route/status notes if affected.

Outcome example:

```text
After the patch, active docs agree on which v1 surfaces are done, partial, preview, internal or out of scope.
```

### Product acceleration targets

Prefer user-visible slices that convert existing surface into confidence:

1. card details enrichment and history around real card work;
2. backup/export/import preview UX and import-as-copy decision boundary;
3. local-first/sync visible status with honest offline/pending/conflict states;
4. auth/account management hardening where it affects real user flow.

Split each target into one verified user fact at a time.

### Safety targets

Use safety patches when they unlock product speed:

1. UIX coverage for the next critical product path;
2. smoke idempotency around shared dev state;
3. contract parity checks for touched API surfaces;
4. release-gates classification for recurring failure families;
5. Playwright retirement/optionalization only after accepted UIX replacement coverage.

## 15. Patch summary template

Every strategic or implementation patch should make these answers easy to find:

```text
What changes:
Why it is needed:
Main files:
Outcome verified:
Evidence run:
Issues found:
Issue fates:
Risks:
Out of scope:
Next safe patch:
```

For docs-only patches, “Evidence run” can be markdown/readability/link sanity plus devctl plan validation.
For runtime/code patches, it must include the affected build/test/smoke/UIX evidence.

## 16. Non-goals

Do not use this strategy to justify:

- rewriting all docs in one mega-patch;
- requiring full release-gates for every small UI change;
- building a new tooling epic without impact on the next 3-5 patches;
- hiding product gaps behind green infrastructure checks;
- presenting preview/internal routes as release-ready user features;
- treating old phase docs as current instructions without a freshness marker.

## 17. Short version

```text
Move faster by delivering verified user facts.
Avoid future pain by giving every problem a fate.
Trust the cheapest sufficient evidence, not the loudest tool.
When docs disagree with runtime/code truth, sync truth before dependent planning.
```

Questions before every patch:

```text
What becomes true?
What is the main risk?
What is the cheapest evidence that proves it?
Which truth surfaces must change?
What are we explicitly not doing?
What fate does every discovered problem get?
```
