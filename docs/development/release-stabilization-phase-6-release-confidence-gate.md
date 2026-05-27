# Release stabilization phase 6 release confidence gate

- Статус: Implemented in `tools/devbootstrap.py`
- Дата: 2026-05-27
- Родительский документ: `docs/development/release-stabilization-program-v1.md`
- Связанные failure-mode IDs: `REL-ART-001`, `REL-SMOKE-001`, `REL-BROWSER-001`, `REL-CLEAN-001`, `REL-DOCS-001`
- Назначение: превратить накопленные evidence artifacts из фаз 1–5 в явное release decision, не позволяя skipped/unknown сигналам выглядеть как успешный релиз.

---

## 1. Что закрывает фаза 6

Фаза 6 добавляет обязательные artifacts в каждый `release-gates` bundle:

| Artifact | Purpose |
|---|---|
| `release-confidence-gate.json` / `.md` | Machine/human-readable score, score blocks, hard caps, unknown ratio, classification coverage and final decision. |
| `v1-release-readiness.md` | Короткий reviewer-facing вердикт: можно ли считать текущий прогон beta candidate, internal candidate или только diagnostic signal. |

Phase 6 originally raised the bundle contract to `phase-6`; after Phase 7 the global contract is `phase-7`, while these artifacts remain required. Они включены в:

- `bundle-manifest.json`;
- `artifact-completeness.json/md`;
- release-gates archive;
- `self-check` case `release_gates_phase6_bundle_contract`.

---

## 2. Автоматический score

Score считается по тем же блокам, которые были зафиксированы в `release-confidence-scorecard-v1.md`:

| Block | Max | Source |
|---|---:|---|
| Evidence completeness | 15 | gate ledger + artifact presence |
| Gate execution signal | 20 | required gate statuses |
| Repeatability | 15 | `remediation/repeatability-loop.json` |
| Isolation safety | 15 | `remediation/controlled-mutators.json` |
| Cross-platform confidence | 10 | `command-resolution.json` + `provocation-matrix.json` |
| Product-path confidence | 15 | backend/frontend/real-backend gate outcomes |
| Remediation maturity | 5 | problem/probe/decision ledgers |
| Artifact quality | 5 | redaction + completeness + manifest contract |

Фаза 6 не делает score “оптимистичным”. Если текущий прогон является `--dry-run`, score ограничивается как contract-shape evidence, а не runtime evidence.

---

## 3. Hard caps

Даже высокий числовой score может быть понижен активными hard caps:

| Cap | Maximum class | Trigger |
|---|---|---|
| `unknown-release-blockers` | `partial_signal` | Required gates are infra-blocked, skipped, partial, planned or unknown. |
| `required-gate-failed` | `partial_signal` | Required gate failed. |
| `repeatability-not-proven` | `internal_candidate` | Reproducibility Index below `0.8`. |
| `real-backend-product-path-missing` | `internal_candidate` | Real-backend product path did not pass. |
| `artifact-not-shareable` | `partial_signal` | Redaction or completeness is not accepted. |
| `dry-run` | `partial_signal` | Dry-run validates contract shape only. |

Beta candidate requires:

- score `>= 85`;
- no active hard caps;
- `overallStatus == ok`;
- accepted skips documented as non-blocking.

---

## 4. Unknown Ratio and classification coverage

Phase 6 writes two review metrics:

```text
unknown_ratio = unknown_required_gates / all_required_gates
classification_coverage = gates_with_non_unknown_classification / all_gates
```

Unknown required gates include required gates with normalized status:

- `infra_failed`;
- `skipped_prerequisite`;
- `partial_pass`;
- `planned`;
- `unknown`.

This intentionally treats missing prerequisites as release-confidence blockers rather than as neutral skips.

---

## 5. Reviewer workflow после фазы 6

1. Open `v1-release-readiness.md` first.
2. If the verdict is not beta-allowed, inspect active hard caps.
3. Open `release-confidence-gate.md` for score block details.
4. Use `remediation/problem-ledger.md` for concrete `REL-*` actions.
5. Rerun the same profile after resolving blockers to refresh repeatability and score.

---

## 6. Extraordinary findings during phase 6

### 6.1. Artifact quality needs a two-pass write

`v1-release-readiness.md` must itself be included in `artifact-completeness.json`, but artifact quality should also know whether completeness passed. The implementation therefore writes Phase 6 confidence artifacts once before completeness, writes completeness/manifest, then rewrites Phase 6 artifacts with the final artifact-quality signal; Phase 7 regression-memory artifacts follow the same two-pass pattern.

This avoids a circular dependency while keeping the final archive self-contained.

### 6.2. Release confidence is not a new product gate

Phase 6 deliberately does not launch new backend/frontend/browser checks. It is a decision layer over existing gates and evidence from phases 1–5. Product confidence can only rise when earlier gates produce stronger runtime evidence.
