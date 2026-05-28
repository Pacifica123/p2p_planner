# Deployment pitfalls catalog for dev auto-bootstrapper

## Purpose

This catalog lists failure families that devbootstrap should classify before a human edits product code. It is intentionally compact; detailed evidence belongs in per-run bundles.

## Pitfall map

| Layer | Common failures | Preferred classification/remediation |
|---|---|---|
| OS/platform | Unsupported shell, path length, permissions, clock skew. | `REL-ENV`; print platform, shell, path and concrete command. |
| Project layout | Wrong cwd, missing `backend/`, `frontend/`, `tools/`, `.env.example`. | Discovery failure; show expected root and found files. |
| Python | Missing Python or incompatible version. | Prerequisite blocker before any project mutation. |
| Git/devctl | Dirty tree, missing patches dir, push/network failure. | `REL-DEVCTL`; separate local apply from remote push. |
| Rust/Cargo | Missing cargo/rustc, failed metadata/check/test, Windows linker path noise. | Toolchain vs product classification; keep raw stderr. |
| Node/npm | Missing node/npm, lockfile mismatch, install failure. | `REL-FE`; never mutate lockfile implicitly. |
| PostgreSQL | Server absent, stopped, wrong port, bad password, no CREATEDB, migrations mismatch. | `REL-DB`; prefer managed test DB or explicit `TEST_DATABASE_URL`. |
| Backend runtime | Port busy, health timeout, env parse, migration boot failure. | `REL-PROC` or `REL-BE` depending on evidence. |
| Frontend runtime | Vite startup failure, env API mismatch, port busy. | `REL-FE` / `REL-PROC`. |
| UI/browser evidence | Browser prerequisite, app boot failure, JS runtime error, route/form/storage failure. | Transitional `REL-BROWSER`; target `REL-UIUX`. |
| Smoke | Writes blocked, dirty shared user state, non-idempotent assumptions. | `REL-SMOKE`; use isolated DB/runtime. |
| Cleanup | Stale PID, owned process not stopped, temporary DB retained unexpectedly. | `REL-PROC`; preserve cleanup evidence. |
| Archive hygiene | `.dev-bootstrap`, node_modules, target, logs or generated reports in source snapshot. | `REL-DEVCTL` / `REL-DOC`; exclude generated artifacts. |
| Security | Secrets in logs, env files in archive, unsafe public defaults. | `REL-SEC`; redact or block archive. |

## Diagnostic principles

1. Classify before fixing.
2. Separate prerequisite failure from product regression.
3. Preserve raw evidence, but redact secrets.
4. Do not “helpfully” write to shared databases.
5. Prefer short targeted rerun commands.
6. Treat generated run artifacts as disposable evidence, not source.

## PostgreSQL checklist

- Is `psql` available?
- Does `pg_isready` reach the target host/port?
- Does the configured user authenticate?
- Is the target database disposable?
- Can the admin role create/drop a per-run DB?
- Are migrations embedded and current?
- Does backend boot against the same DB used by smoke tests?

## Browser/UI checklist

Legacy Playwright issues must not be confused with UI product failures. The target custom UI/UX Evidence Runner should distinguish:

- no supported system browser;
- frontend unreachable;
- app root not mounted;
- JS runtime/console fatal;
- route marker missing;
- button hidden/disabled/not actionable;
- form submission failed;
- local/session storage mismatch;
- backend contract/network mismatch.

## Archive checklist

Project snapshots should exclude:

```text
.git/
.devctl/
.dev-bootstrap/
.venv/
node_modules/
target/
dist/
build/
coverage/
logs/
__pycache__/
.pytest_cache/
.env*
*.db / *.sqlite / *.tsbuildinfo
```

Per-run release-gates bundles remain separate and are attached only when diagnosing a run.
