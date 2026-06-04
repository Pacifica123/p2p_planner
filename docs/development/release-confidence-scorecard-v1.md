# Release confidence scorecard v1

- Статус: Automated by Phase 6 release confidence gate and preserved by Phase 7 regression memory; manual policy remains canonical
- Дата: 2026-05-27
- Последний зафиксированный checkpoint: 2026-06-04 `full-local-release`, score `89/100`, effective `internal_candidate`
- Родительский документ: `docs/development/release-stabilization-program-v1.md`
- Назначение: зафиксировать политику release confidence; с Phase 6 она считается автоматически в `release-confidence-gate.json/md`.

---


## 0. Automation status

Phase 6 now writes `release-confidence-gate.json` / `.md` and `v1-release-readiness.md` into every `release-gates` bundle. Phase 7 additionally writes `remediation/regression-memory.*` and `remediation/recurring-family-counts.*`, so score changes can be reviewed against problem/probe memory and recurring failure families. This document remains the scoring policy, while the run artifacts contain the current computed score, active hard caps, unknown ratio, classification coverage and final release recommendation.

---

## 1. Score classes

| Score | Class | Meaning | Release decision |
|---:|---|---|---|
| `< 50` | `diagnostic_chaos` | Too much is unknown or hidden behind skipped gates. | Release forbidden. |
| `50-69` | `partial_signal` | Useful diagnostic signal exists, but beta confidence is not proven. | Fix infra/product blockers first. |
| `70-84` | `internal_candidate` | Enough evidence for internal user testing. | External beta still blocked by unknowns. |
| `85-94` | `beta_candidate` | Candidate for limited external beta. | Allowed only with documented known limitations. |
| `95+` | `stable_release_loop` | Mature repeatable release/dev loop. | Routine release cadence possible. |

Hard caps:

| Condition | Maximum class |
|---|---|
| Any unknown release blocker remains | `partial_signal` |
| Required gates are skipped because prerequisites are absent | `partial_signal` |
| No two-run repeatability evidence exists | `internal_candidate` |
| No real-backend product-path evidence exists through `frontend_uiux_real_backend_core_flow` or the legacy no-mock browser gate | `internal_candidate` |
| Artifact bundle is not shareable/redacted | `partial_signal` |
| Product code changed without relevant smoke/check | `partial_signal` |

---

## 2. Weighted blocks

| Block | Weight | Manual scoring question |
|---|---:|---|
| Evidence completeness | 15 | Can a reviewer understand the run from artifacts without terminal scrollback? |
| Gate execution signal | 20 | Did required gates actually run instead of being skipped/not implemented? |
| Repeatability | 15 | Did the same profile pass twice and survive start/stop/start? |
| Isolation safety | 15 | Are DB/runtime/deps/process writes safe, owned, reversible and consented? |
| Cross-platform confidence | 10 | Are Linux and Windows launcher/path realities covered? |
| Product-path confidence | 15 | Are ready product paths tested end-to-end against real backend, with UIX real-backend core flow as the preferred proof? |
| Remediation maturity | 5 | Do failures have IDs, evidence, probes and remediation plans? |
| Artifact quality | 5 | Is the bundle small, redacted, complete and shareable? |

Manual score:

```text
score = evidence + gates + repeatability + isolation + cross_platform + product_path + remediation + artifact_quality
```

Unknown ratio:

```text
unknown_ratio = skipped_or_not_implemented_required_gates / all_required_gates
```

Reproducibility index:

```text
reproducibility_index = passed_repeatability_scenarios / total_repeatability_scenarios
```

---

## 3. Phase 0 provisional baseline

This is not a release decision. It is a starting governance baseline from the current documentation and known run summaries.

| Block | Weight | Phase 0 provisional value | Reason |
|---|---:|---:|---|
| Evidence completeness | 15 | 8 | Release-gates already produces reports/bundles, but Phase 1 bundle contract is not yet frozen. |
| Gate execution signal | 20 | 9 | Backend/docs signals exist, but frontend/browser/DB gates have recently been blocked by prerequisites in known runs. |
| Repeatability | 15 | 4 | Repeated smoke and start/stop/start are explicit goals, not yet accepted as stable release evidence. |
| Isolation safety | 15 | 8 | Managed DB/runtime concepts exist, but Phase 0 has not revalidated them with fresh evidence. |
| Cross-platform confidence | 10 | 5 | Windows launcher issues are known and partially handled, but matrix confidence is not complete. |
| Product-path confidence | 15 | 8 | Core CRUD, appearance and activity are ready surfaces, but a fresh UIX real-backend core-flow bundle is still needed before beta naming. |
| Remediation maturity | 5 | 3 | Initial Problem Ledger exists; Probe/Decision ledgers are still future phases. |
| Artifact quality | 5 | 3 | Archive trimming and bundle intent exist, but redaction/completeness gates need Phase 1/2 hardening. |
| **Total** | **100** | **48** | Current class: `diagnostic_chaos` by numeric score, close to `partial_signal` but still capped by missing fresh evidence. |

Interpretation:

```text
Current phase 0 confidence is not beta evidence.
The project has useful diagnostic machinery, but this baseline intentionally refuses to award release confidence for skipped or stale evidence.
```

The score should be recalculated after the first Phase 1/2 autopsy bundle run. A successful, shareable, redacted bundle with explicit skips may move the project into `partial_signal`; real beta candidacy requires the later repeatability and product-path gates.

---

## 4. Required evidence before score can exceed caps

| Cap to lift | Required evidence |
|---|---|
| Unknown release blocker cap | Problem Ledger lists every blocker with owner layer and next action. |
| Skipped-gate cap | Required gates either run or are explicitly accepted as non-blocking. |
| Repeatability cap | Same profile runs twice; start -> stop -> start passes or produces known classification. |
| Real-backend cap | `frontend_uiux_real_backend_core_flow` passes against managed frontend/backend/test DB, or the legacy no-mock real-backend browser gate passes with equivalent safe DB/runtime evidence. |
| Artifact cap | Bundle manifest, redaction report and completeness check are present. |

---

## 5. Review questions for every score update

1. Which artifacts justify each non-zero block score?
2. Which skipped gates are counted as unknown rather than pass?
3. Which ready product surfaces were tested against real backend?
4. Which future-ready surfaces were intentionally excluded from score?
5. Which `REL-*` IDs changed status?
6. Which new probes prevent regression?
7. What is the exact reason the score class changed?
8. Which recurring `REL-*` family, if any, requires process review before another tactical patch?


## 6. UIX product-path acceptance checkpoint

As of the release-evidence checkpoint, the scorecard treats `frontend_uiux_real_backend_core_flow` as the preferred real-backend product-path proof. The legacy `browser_real_backend_path` gate remains valid as a transitional no-mock browser signal, but it is no longer the only way to lift the `real-backend-product-path-missing` cap.

Accepted product-path evidence must still be write-safe and runtime-owned:

- managed or explicit disposable test database;
- devbootstrap-owned backend and frontend processes, or equivalent documented runtime ownership;
- no page/API route mocks for the real-backend flow;
- preserved UIX report artifacts under the `release-gates` bundle.

Mocked UIX evidence and legacy mocked browser smoke are useful frontend signals, but they do not lift the real-backend cap by themselves.


## 7. Current checkpoint snapshot: 2026-06-04

The first accepted post-truth-sync evidence checkpoint is documented in `docs/product/release-evidence-checkpoint-2026-06-04.md`. It ran:

```text
python tools/devbootstrap.py release-gates --profile full-local-release
```

Result:

```text
Overall: ok
Classification: release_gates_ok
Score: 89/100
Raw class: beta_candidate
Effective class: internal_candidate
Unknown ratio: 0.0
Accepted real-backend gate: frontend_uiux_real_backend_core_flow
Active hard cap: repeatability-not-proven
```

Policy interpretation: the real-backend product-path cap is lifted for this source state, but external beta remains blocked until the repeatability cap is lifted or explicitly accepted by release review.
