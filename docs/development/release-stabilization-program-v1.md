# Release stabilization program v1

## Decision

The release/dev lifecycle is treated as a measurable system, not as a sequence of ad-hoc fixes. Every red gate must become one of three things:

1. a classified product regression;
2. a classified infrastructure/prerequisite blocker;
3. an explicit unknown with a next probe.

The program is implemented through `tools/devbootstrap.py release-gates` plus the Phase 0-7 documentation and per-run remediation bundle.

## Supported reality v1

| Area | Supported baseline |
|---|---|
| OS | Linux and Windows are supported, but Linux is the preferred truth source when Windows toolchain noise appears. |
| Workspace | Project lives in a devctl workspace; generated artifacts must not be committed or archived as source. |
| Backend | Rust/Axum backend; cargo gates are required. |
| Frontend | Vite/React frontend; build and unit/integration gates are required. |
| DB | PostgreSQL; write-capable gates require `TEST_DATABASE_URL`, managed test DB, or explicit disposable dev DB consent. |
| Browser/UI | Legacy Playwright is transitional; long-term target is a custom UI/UX Evidence Runner. |
| Artifacts | Each release-gates run writes a bundle with reports, ledgers, classifications, rerun commands and evidence. |

## Operating loop

1. Run a safe diagnostic first.
2. Read `release-confidence-gate.md`, `problem-ledger.md`, `next-actions.md` and logs.
3. Do not patch product code until the blocker is classified.
4. Apply the smallest remediation.
5. Rerun the same profile to prove the signal changed.
6. Escalate profile only after lower profiles are clean enough.

Canonical command ladder:

```bash
python -B tools/devbootstrap.py self-check --no-write-report
python -B tools/devbootstrap.py release-gates --dry-run
python -B tools/devbootstrap.py release-gates --profile diagnostic --prepare-deps
python -B tools/devbootstrap.py release-gates --managed-test-db --managed-runtime --prepare-deps
python -B tools/devbootstrap.py release-gates --profile full-local-release --include-clean-machine --clean-machine-profile=dry
```

## Ledgers

| Ledger | Purpose |
|---|---|
| Problem Ledger | Stable `REL-*` IDs, owner layer, severity, evidence and next probe. |
| Probe Ledger | What was checked, under which profile, with which side effects. |
| Decision Ledger | Human decision after evidence: fix, defer, accept, split, or reclassify. |
| Regression Memory | Recurring family counts and repeat-failure hints across runs. |

## Failure taxonomy

Core families:

| Family | Meaning |
|---|---|
| `REL-ENV` | OS/tool/path/environment prerequisite. |
| `REL-DB` | PostgreSQL connectivity, authority, migrations or disposable DB setup. |
| `REL-PROC` | Managed process, port, PID, runtime or teardown issue. |
| `REL-BE` | Backend product/test failure. |
| `REL-FE` | Frontend dependency/build/unit failure. |
| `REL-BROWSER` | Browser automation prerequisite or UI smoke issue. |
| `REL-SMOKE` | Backend/frontend smoke write-safety or idempotency issue. |
| `REL-DOC` | Documentation or release-note gate. |
| `REL-DEVCTL` | Patch conveyor/archive/VCS transport issue. |
| `REL-SEC` | Secret leakage, redaction, unsafe logs or privacy-sensitive artifact. |
| `REL-UNMAPPED` | Temporary fallback; must be reduced by new classifier or explicit decision. |
| `REL-UIUX` | Post-Playwright UI/UX evidence runner design/implementation issue. |

## Metrics

| Metric | Use |
|---|---|
| Release Confidence Score | 0-100 summary signal from passed/partial/skipped/failed gates. |
| Unknown Ratio | Fraction of signals that are not classified enough to act on. |
| Reproducibility Index | Whether same-profile reruns produce stable results. |
| Classification Coverage | How much of the failure surface maps to stable `REL-*` IDs. |
| Remediation Closure Rate | How quickly active blockers become fixed/accepted/deferred. |
| Artifact Quality | Whether bundle manifest, redaction, completeness and logs are present. |

## Phase map

| Phase | Result |
|---|---|
| 0 | Governance baseline, freeze rules, manual scorecard, side-effect profile map. |
| 1 | Autopsy bundle contract: manifest, environment fingerprint, command resolution, redaction and completeness reports. |
| 2 | Machine-readable Problem/Probe/Decision ledgers and taxonomy mapping. |
| 3 | Low-risk diagnostic provocation matrix. |
| 4 | Controlled mutators with consent, cleanup and rollback evidence. |
| 5 | Repeatability loop and historical same-profile comparison. |
| 6 | Automated release confidence gate and `v1-release-readiness.md`. |
| 7 | Regression memory and recurring family counts. |

## Current post-Phase-7 decision

Playwright repeatedly became the blocker instead of the application evidence source: stale browser revisions, missing `chromium_headless_shell`, install timeouts and large downloads. The long-term decision is to replace mandatory Playwright browser smoke with a custom, lighter UI/UX Evidence Runner while keeping legacy Playwright only during migration.

See `docs/development/custom-uiux-evidence-manifesto-v1.md`.

## Definition of done

The program is complete when:

- release-gates can run from a clean workspace with documented side effects;
- every red signal maps to a stable family or a deliberate unknown probe;
- write-capable tests use isolated DB/runtime by default;
- generated run artifacts stay outside source archives;
- the final bundle is small enough to share and complete enough to diagnose;
- Playwright is no longer required for the mandatory UI/UX release signal.
