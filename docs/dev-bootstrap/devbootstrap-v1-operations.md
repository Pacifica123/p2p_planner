# devbootstrap v1 operations guide

`tools/devbootstrap.py` is the project-specific local dev auto-bootstrapper. It is not a generic deployment system and it intentionally stays inside Python standard library. Its job is to make the local development routine repeatable, diagnosable and safe on Windows/Linux machines where the project archive was extracted by a human or by devctl.

## Quick command path

For a fresh archive, the safest sequence is:

```bash
python tools/devbootstrap.py self-check
python tools/devbootstrap.py diagnose
python tools/devbootstrap.py plan
python tools/devbootstrap.py prepare-env
python tools/devbootstrap.py up --dry-run
python tools/devbootstrap.py up
python tools/devbootstrap.py smoke --level quick
python tools/devbootstrap.py status
python tools/devbootstrap.py stop
```

For stronger checks after the stack is alive:

```bash
python tools/devbootstrap.py smoke --level standard --allow-dev-db-write
python tools/devbootstrap.py smoke --level full --allow-dev-db-write
```

`standard` and `full` smoke can write through the backend API. Prefer `TEST_DATABASE_URL`; use `--allow-dev-db-write` only when the configured dev database is intentionally disposable.

## Command responsibilities

| Command | Role | Safe by default |
|---|---|---|
| `self-check` | Runs internal v1 fixtures for env parsing, URL parsing, classifiers, root discovery and report JSON contract. | Yes |
| `diagnose` | Reads platform, tools, required files, ports, health URLs and tracked state. | Yes |
| `plan` | Compares env examples and local env files, masks secrets and reports mismatches. | Yes |
| `prepare-env` | Creates missing env files from examples. Existing env files are not overwritten. | Yes |
| `start-db` | Checks configured PostgreSQL and can start compose `postgres` if the port is closed. | Guarded |
| `check-backend` | Runs `cargo metadata` and `cargo check`. | Yes, but can be slow |
| `start-backend` | Starts `cargo run`, captures PID/state/logs and waits for health. | Guarded |
| `prepare-frontend` | Runs `npm ci` or `npm install` when dependencies are missing/stale. | Guarded |
| `start-frontend` | Starts `npm run dev`, captures PID/state/logs and waits for frontend root. | Guarded |
| `up` | Orchestrates the routine pipeline and stops on first blocking failure. | Guarded; `--dry-run` first |
| `smoke` | Runs quick/standard/full post-start gates. | Quick is read-only; standard/full need DB write consent |
| `status` | Shows tracked PIDs, ports, health probes and compose snapshot. | Yes |
| `stop` | Stops only devbootstrap-tracked backend/frontend processes. DB stop requires `--include-db`. | Yes |

## Report artifacts

Commands that write reports create run folders under:

```text
.dev-bootstrap/runs/YYYYMMDD_HHMMSS_<command>/
```

A run folder always uses this convention:

```text
report.md        Human-readable summary and next actions.
<command>.json   Machine-readable payload for tooling and AI-assisted debugging.
*.log            Optional command logs for long-running subprocesses.
```

`diagnose` keeps the historical name `diagnose.json`; `smoke`, `up`, `stop` and `self-check` write `smoke.json`, `up.json`, `stop.json`, `self-check.json`. The JSON report envelope includes:

```json
{
  "schemaVersion": 1,
  "command": "self-check",
  "toolVersion": "1.0.0",
  "generatedAt": "...",
  "status": "ok"
}
```

Command-specific fields remain below this common envelope. Secrets are not supposed to appear in JSON or markdown reports; env values with markers such as `SECRET`, `PASSWORD`, `TOKEN`, `COOKIE`, `DATABASE__URL` and `DATABASE_URL` are masked.

## Timeout policy

The v1 tool keeps its default timeout values in a central `TIMEOUT_POLICY` map inside `tools/devbootstrap.py`:

| Key | Default meaning |
|---|---|
| `probe_command` | Small command probes such as `git --version`. |
| `port_probe` | TCP port reachability checks. |
| `http_probe` | Simple HTTP health probes. |
| `postgres_ready` | Waiting for compose PostgreSQL readiness. |
| `cargo_metadata` | Backend metadata resolution. |
| `cargo_check` | Backend compilation/type check. |
| `backend_ready` | Waiting for backend health after `cargo run`. |
| `npm_install` | Frontend dependency installation. |
| `frontend_ready` | Waiting for Vite root after `npm run dev`. |
| `smoke_step` | Command-based smoke substeps. |
| `up_step` | Short orchestration substeps. |
| `stop_grace` | Graceful stop window for owned processes. |

Command-line flags can override the important long-running values when a slow machine needs more time.

## Failure handling rules

The v1 quality bar is: every common failure should answer four questions.

1. What command failed?
2. Which subsystem does it belong to?
3. What is the likely class of problem?
4. What should the user inspect or run next?

Important examples:

- `port_conflict` means devbootstrap refuses to kill a foreign process automatically.
- `migration_drift` points to Rust/sqlx migration embedding mismatch or stale build artifacts.
- `postgres_auth_failed` means the port is reachable but credentials/user/database do not match the configured URL.
- `frontend_dependency_missing` means `node_modules` or npm install state should be repaired before start.
- `runtime_unreachable` in smoke means HTTP/browser tests could not reach a service.

## Cleanup rules

`stop` is deliberately conservative:

- it reads only `.dev-bootstrap/state.json`;
- it stops backend/frontend PIDs only after ownership verification;
- it removes stale tracked PIDs safely;
- it does not kill arbitrary processes occupying `18080` or `5173`;
- it does not stop PostgreSQL unless `--include-db` is passed;
- it never removes Docker volumes.

If ports remain open after `stop`, use `status` and manual OS tools to inspect them.

## v1 acceptance check

Before treating devbootstrap changes as routine-ready, run:

```bash
python -c "import ast,pathlib; ast.parse(pathlib.Path('tools/devbootstrap.py').read_text(encoding='utf-8'))"
python tools/devbootstrap.py self-check --no-write-report
python tools/devbootstrap.py diagnose --no-write-report
python tools/devbootstrap.py up --dry-run --smoke-level quick
python tools/devbootstrap.py stop --dry-run --no-write-report
```

When Docker/Rust/Node/PostgreSQL are available, also run the real sequence:

```bash
python tools/devbootstrap.py prepare-env
python tools/devbootstrap.py up
python tools/devbootstrap.py smoke --level quick
python tools/devbootstrap.py stop
```

