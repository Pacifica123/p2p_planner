# devbootstrap v2 release gates plan

## Formula

`release-gates` is a keep-going evidence runner: run every safe gate that can run, classify each result, preserve logs and produce a compact bundle with next actions.

## Gate matrix

| Gate family | Examples | Notes |
|---|---|---|
| Self/tooling | `self_check`, `diagnose` | Must be cheap and deterministic. |
| Backend | cargo default tests, DB ignored tests | Ignored DB tests are covered by separate DB-safe gate. |
| Backend smoke | Python API smoke first/second run | Requires isolated DB/runtime or explicit disposable DB consent. |
| Frontend | prepare deps, build, unit/integration | Missing deps are infra failures, not product failures. |
| UI/browser | UIX boot/core-flow, legacy optional browser smoke | Playwright is transitional; the project-owned UIX runner uses system browser evidence without mandatory browser downloads. |
| Real backend UI | `frontend_uiux_real_backend_core_flow` against managed frontend/backend/test DB | Preferred product-path proof for release confidence; legacy no-mock browser path remains optional transition evidence. |
| Docs/release | README commands, known limitations, checklist | Low cost; always run. |
| Clean-machine | sandbox dry/deps/runtime profiles | Optional until core gates are clean. |

## Bundle contract

Each run should write:

```text
release-gates.md
release-gates.json
release-gates_*.zip
logs/*.log
release-gates-consent.md/json
remediation/gate-ledger.md/json
remediation/problem-ledger.md/json
remediation/probe-ledger.json
remediation/next-actions.md
remediation/rerun-commands.md
release-confidence-gate.md/json
v1-release-readiness.md
```

## Classification rules

- `ok`: command passed and no special release caveat.
- `partial_pass`: command exited successfully but skipped/ignored meaningful checks.
- `infra_failed`: prerequisite or environment issue.
- `failed`: product/test command failed after prerequisites were met.
- `skipped_prerequisite`: gate would be unsafe or meaningless now.
- `skipped_optional`: optional signal not requested.
- `planned`: dry-run only.

## Consent profiles

| Profile | Intent |
|---|---|
| `diagnostic` | Safe baseline with no DB/runtime/download mutators unless explicitly requested. |
| `prepared-local` | Prepare local caches/dependencies. |
| `isolated-db` | Use managed/disposable DB for write-capable gates. |
| `managed-runtime` | Start owned backend/frontend on dynamic ports against isolated DB. |
| `full-local-release` | Highest local signal: deps, managed DB/runtime, UIX real-backend product path, clean-machine dry. |

## Playwright transition note

The original v2 plan used Playwright as the browser-smoke implementation and added `playwright_install` as a controlled gate. After repeated browser revision/install failures, Playwright is considered a legacy transition layer. `frontend_uiux_real_backend_core_flow` is now accepted by the automated release-confidence scorecard as the preferred real-backend product-path proof; the legacy no-mock browser path remains optional until it is retired or kept only as supplemental evidence.

## Done criteria

- bundle is complete and redacted;
- failed gates have `REL-*` mapping and next action;
- dry-run does not require local dependencies;
- write-capable gates cannot run against shared DB by accident;
- generated artifacts remain outside source archives;
- UI evidence is available without mandatory Playwright downloads.
