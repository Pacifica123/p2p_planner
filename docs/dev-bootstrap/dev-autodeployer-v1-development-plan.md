# Dev auto-bootstrapper v1 development plan

## Purpose

`tools/devbootstrap.py` is the project-owned local environment assistant. It exists so a developer can move from a raw checkout/archive to a diagnosed, runnable, testable dev environment through explicit, reportable commands.

## Non-goals

- Do not become a package manager.
- Do not hide destructive actions.
- Do not silently write to a shared database.
- Do not start or stop processes that were not created by the tool.
- Do not replace devctl; devbootstrap prepares/tests the project, devctl applies patches.

## CLI surface

| Command | Responsibility |
|---|---|
| `diagnose` | Read-only platform/tool/port/HTTP checks. |
| `plan` | Show intended env/runtime actions. |
| `prepare-env` | Safely create missing env files from examples. |
| `start-db` | Guarded PostgreSQL/compose assistance. |
| `check-backend` | Backend metadata/check compilation diagnostics. |
| `start-backend` | Start owned backend process and track PID/logs. |
| `prepare-frontend` | Install/refresh frontend dependencies by policy. |
| `start-frontend` | Start owned Vite frontend and track PID/logs. |
| `smoke` | Quick/standard/full smoke ladder. |
| `status` | Show tracked PIDs, ports, health and stale state. |
| `stop` | Stop only tracked owned processes; DB only by explicit opt-in. |
| `up` | One-command guarded pipeline. |
| `self-check` | Internal sanity suite for the bootstrapper. |
| `release-gates` | Keep-going release evidence runner and remediation bundle. |

## Implemented v1/v2 reality

The original v1 phased plan has been implemented and extended. Current notable capabilities:

- JSON/Markdown report envelope for commands;
- timeout policy and failure classifiers;
- Windows command resolution for `.cmd`/npm/cargo cases;
- managed test DB derivation and safe write guards;
- managed runtime with dynamic backend/frontend ports;
- frontend dependency marker and prepare modes;
- release-gates profiles and consent plan;
- remediation bundle, ledgers, confidence gate and regression memory;
- explicit transition away from Playwright toward custom UI/UX evidence.

## Runtime state and artifacts

Generated files live under `.dev-bootstrap/`. They are not source and should not be included in devctl project snapshots.

Important paths:

```text
.dev-bootstrap/state.json
.dev-bootstrap/frontend-install.json
.dev-bootstrap/runs/<run-id>/report.md
.dev-bootstrap/runs/<run-id>/release-gates.md
.dev-bootstrap/runs/<run-id>/release-gates.json
.dev-bootstrap/runs/<run-id>/release-gates_*.zip
```

## Safety model

| Action | Default |
|---|---|
| Read environment/tools/ports | Allowed. |
| Write reports under `.dev-bootstrap` | Allowed for non-dry command runs. |
| Create env files | Only missing files, never overwrite secrets. |
| Install dependencies | Explicit prepare mode/profile. |
| Create/drop test DB | Explicit managed DB/profile and credentials. |
| Write through backend smoke | Requires isolated DB or explicit disposable dev DB consent. |
| Start processes | Only owned tracked processes. |
| Stop processes | Only owned tracked processes. |

## Integration with devctl

- devctl applies project patches and creates pre/post/failed archives.
- devbootstrap generates diagnostic bundles inside a project run.
- devctl archives must exclude `.dev-bootstrap` because it is generated evidence, not source.
- Patch checks may run `python -B tools/devbootstrap.py self-check --no-write-report` for syntax/contract confidence.

## Acceptance criteria

The tool is acceptable when:

- a new developer can diagnose missing prerequisites without reading source;
- every mutating action is explicit and logged;
- failed gates produce targeted next commands;
- generated run artifacts are shareable as separate bundles;
- source archives remain small and free of `.dev-bootstrap` history.
