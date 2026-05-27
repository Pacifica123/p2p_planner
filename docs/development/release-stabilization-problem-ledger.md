# Release stabilization Problem Ledger

- Статус: Initial ledger for Phase 0
- Дата: 2026-05-27
- Родительский документ: `docs/development/release-stabilization-program-v1.md`
- Назначение: хранить стабильные failure-mode IDs для release/dev lifecycle, чтобы следующие патчи не лечили симптомы без классификации.

---

## 1. Ledger policy

Problem Ledger is append-only in spirit: entries may change status and gain evidence, but IDs should not be reused for a different failure class.

A release/dev remediation patch must do at least one of the following:

1. reference an existing `REL-*` ID from this ledger;
2. add a new `REL-*` ID before changing behavior;
3. state that it is a docs/governance-only baseline patch.

A failure cannot move to `closed` unless it has:

- concrete evidence;
- root-cause confidence above `symptom_only`;
- acceptance check;
- regression probe or explicit accepted non-blocking rationale.

---

## 2. Status vocabulary

| Status | Meaning |
|---|---|
| `suspected` | Plausible failure class from design/current evidence, not yet reproduced in current run. |
| `observed` | Seen in logs, reports, previous runs or documented summaries. |
| `reproduced` | Reproduced intentionally under known conditions. |
| `remediation_planned` | Fix strategy chosen but not fully implemented. |
| `patched` | Remediation patch exists, but guard/repeatability still pending. |
| `guarded` | Probe exists and catches regression. |
| `closed` | Guarded and accepted as resolved. |
| `regressed` | Previously closed/guarded issue returned. |
| `accepted_non_blocking` | Known issue, documented and intentionally not blocking current scope. |

---

## 3. Initial known failure modes

| ID | Status | Severity | Owner layer | Summary | Current evidence | Required acceptance / probe |
|---|---|---|---|---|---|---|
| `REL-FE-001` | observed | blocks_release | devbootstrap / frontend | `node_modules` absent or stale blocks frontend build/test/browser gates. | Prior release-gates analysis records frontend gates stopped before execution when dependencies were absent. | Dependency marker preflight; `prepare-frontend --install-mode=stale`; frontend build/test gates classified as dependency/prerequisite failures when deps are missing. |
| `REL-WIN-001` | observed | blocks_local_start | devbootstrap / Windows launcher | npm/Vite startup through `.cmd` wrapper can hang or lose forwarded args. | Windows frontend startup troubleshooting notes and command-resolution fixes. | Command-resolution self-check captures executable, shell mode and final argv; direct Vite fallback remains available. |
| `REL-DB-001` | observed | blocks_release | devbootstrap / backend tests | DB integration tests are skipped without safe `TEST_DATABASE_URL`. | Release-gates follow-up notes `cargo test` can exit 0 while DB tests are ignored. | Explicit test DB or managed DB gate; skipped DB tests reduce score and never count as pass. |
| `REL-DB-002` | observed | blocks_local_start | devbootstrap / PostgreSQL authority | Configured backend DB user may lack `CREATEDB`; admin override is needed for managed DB. | Managed DB troubleshooting and admin override docs. | Authority ladder probe; explicit maintenance/admin connection support; cleanup instructions for created DBs. |
| `REL-MIG-001` | observed | blocks_release | backend / migrations | `sqlx::migrate!()` can embed stale migration list without rebuild trigger. | Appearance customization phase discovered migration mismatch until `backend/build.rs` with `rerun-if-changed=migrations` was added. | Build.rs presence check; migration disk/applied/embedded integrity guard. |
| `REL-SMOKE-001` | observed | blocks_repeatability | smoke / backend | Fixed-user default-state assumptions fail on dirty shared dev DB. | Activity/history phase found `me/appearance` default assumption failing after prior customization. | Shared-dev smoke must tolerate existing user state; strict default checks only in isolated DB tests; repeated smoke probe. |
| `REL-PROC-001` | observed | blocks_local_start | devbootstrap / runtime | Old backend/frontend process can make new code appear missing. | Appearance route initially looked absent because an old backend process/stale build was still serving. | Owned process identity probe; health endpoint identity; safe stop only for owned PID. |
| `REL-PORT-001` | suspected | blocks_local_start | devbootstrap / runtime | Foreign process can occupy expected backend/frontend ports. | Supported reality includes occupied legacy ports; no current reproduced evidence in this phase. | Port owner classification; fixed-port conflict should be `REL-PORT`, not generic runtime failure. |
| `REL-CFG-001` | suspected | blocks_release | frontend / backend config | Frontend can call an old/wrong backend or be blocked by CORS. | Supported reality and troubleshooting mention API base URL / origin mismatch. | API base URL + backend allowed-origin consistency artifact; managed URLs written to bundle. |
| `REL-BROWSER-001` | suspected | hides_failure | frontend / devbootstrap | Mocked browser smoke can hide real backend integration gap. | Program separates mocked browser smoke from real-backend browser smoke. | Real-backend browser gate with safe DB/runtime; score treats mocked smoke as UI-only. |
| `REL-CLEAN-001` | suspected | hides_failure | devbootstrap / packaging | Clean archive/checkout may not reproduce current dev setup. | Program requires clean-machine dry/deps/runtime profiles. | Clean-machine dry gate and optional runtime sandbox; exclusion report. |
| `REL-ART-001` | observed | degrades_signal | devbootstrap / devctl artifacts | Diagnostics can be incomplete or too large to share. | Release-gates bundle/remediation requirements and archive trimming history. | Required artifact completeness check; archive size/exclusion policy. |
| `REL-VCS-001` | observed | transport_only | devctl / Git remote | Remote push internal error after local apply/check/commit should not invalidate patch contents. | Previous `PUSH_FAILED` due remote internal server error. | Stage-separated devctl report showing validate/apply/check/commit/push; safe reissue protocol. |
| `REL-DOCS-001` | suspected | documentation_gap | docs / devbootstrap | Docs can describe old command behavior. | Release-gates command surface changed frequently across phases. | Docs command examples gate; docs map updated with every behavior change. |
| `REL-SEC-001` | suspected | security_risk | devbootstrap / devctl artifacts | Diagnostic bundle can leak secrets through env, URLs, logs or reports. | Program requires redaction report and secret scan; Phase 0 fixed missing `REL-SEC` taxonomy row. | Redaction report; connection-string masking; env allowlist; archive secret scan. |

---

## 4. Owner-layer quick index

| Owner layer | Failure IDs |
|---|---|
| Backend / migrations | `REL-MIG-001` |
| Backend tests / DB | `REL-DB-001`, `REL-SMOKE-001` |
| Devbootstrap / release-gates | `REL-FE-001`, `REL-WIN-001`, `REL-DB-001`, `REL-DB-002`, `REL-PROC-001`, `REL-PORT-001`, `REL-CFG-001`, `REL-BROWSER-001`, `REL-CLEAN-001`, `REL-ART-001`, `REL-SEC-001` |
| Devctl / Git transport | `REL-VCS-001` |
| Docs | `REL-DOCS-001` |
| Frontend | `REL-FE-001`, `REL-CFG-001`, `REL-BROWSER-001` |

---

## 5. Minimum fields for future expanded entries

When a row becomes the direct target of a remediation patch, expand it into a dedicated subsection with these fields:

```text
id
family
status
severity
ownerLayer
summary
firstObservedAt
lastObservedAt
evidence[]
rootCauseHypothesis
remediationOptions[]
chosenRemediation
acceptanceCheck
regressionProbe
cleanupOrRollback
confidence
relatedIssues[]
```

Until Phase 2 implements machine-readable ledgers, this Markdown table is the canonical human ledger.
