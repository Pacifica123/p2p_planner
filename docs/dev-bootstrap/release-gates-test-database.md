# Release-gates test database

`devbootstrap release-gates` deliberately treats DB-writing checks as unsafe unless a write-safe database target is explicit. This keeps regular dev data from being modified by backend smoke, DB integration tests, or the real-backend browser path.



## Release-gates profiles and consent policy

Profiles are the preferred high-level UX for the managed release-gates stack:

```bash
python tools/devbootstrap.py release-gates --profile diagnostic --dry-run
python tools/devbootstrap.py release-gates --profile prepared-local
python tools/devbootstrap.py release-gates --profile isolated-db
python tools/devbootstrap.py release-gates --profile managed-runtime
python tools/devbootstrap.py release-gates --profile full-local-release --dry-run
```

`diagnostic` is the safe baseline. `prepared-local` allows dependency/browser cache preparation. `isolated-db` creates a managed PostgreSQL test DB. `managed-runtime` combines managed DB plus owned backend/frontend processes on dynamic ports. `full-local-release` combines dependency preparation, managed DB/runtime, the real-backend browser path and a dry clean-machine sandbox.

Profiles set defaults only. Explicit flags still win, including boolean opt-out forms such as:

```bash
python tools/devbootstrap.py release-gates --profile full-local-release --managed-test-db=false
python tools/devbootstrap.py release-gates --profile prepared-local --install-playwright-browsers=false
python tools/devbootstrap.py release-gates --profile diagnostic --include-clean-machine
```

Every run writes `release-gates-consent.md` and `release-gates-consent.json` into the run directory. The consent files show the resolved profile, explicit overrides, effective options, allowed side effects, denied side effects and planned gate families. Dry-run profile runs must not create databases, install dependencies, start processes, copy clean-machine sandboxes or perform browser downloads.

## Diagnostic remediation bundle

Every `release-gates` run writes a first-class remediation bundle under `remediation/` and includes it in `release-gates_*.zip`:

```text
remediation/
  gate-ledger.md
  gate-ledger.json
  prerequisites.md
  skipped-gates.md
  next-actions.md
  rerun-commands.md
  environment-fingerprint.json
```

The ledger normalizes raw gate states into human/AI-friendly statuses: `passed`, `failed`, `infra_failed`, `skipped_prerequisite`, `skipped_optional`, `partial_pass` and `planned`. This makes the important distinction explicit: an `infra_failed` run can still prove that some gates passed while other release-critical areas remain unknown.

`prerequisites.md` lists infrastructure blockers with targeted next actions. `skipped-gates.md` lists unverified areas. `rerun-commands.md` is generated from actual blocker classifications, for example `--prepare-deps --install-playwright-browsers` for frontend dependency/browser blockers or `--managed-test-db --managed-runtime` for write-safe DB/runtime blockers. `environment-fingerprint.json` captures OS, Python, Git, Cargo/Rust, Node/npm, Docker/Compose, `psql`/`pg_isready`, default port probes, frontend dependency marker details, lockfile/migrations hashes, `backend/build.rs` presence and the current `.dev-bootstrap/state.json` summary with secrets masked by omission.


## Managed ephemeral database

The recommended one-command DB path is:

```bash
python tools/devbootstrap.py release-gates --managed-test-db
```

`--managed-test-db` automatically uses the same isolated runtime for write-capable gates. You can also pass `--managed-runtime` explicitly, especially when using an external `TEST_DATABASE_URL`:

```bash
python tools/devbootstrap.py release-gates --managed-test-db --managed-runtime
```

With `--managed-test-db`, `release-gates` derives host/port and the backend DB owner from `DATABASE__URL` / `DATABASE_URL`, creates an isolated database named like `p2pkanban_rg_<toolVersion>_<timestamp>_<id>`, overrides `DATABASE__URL`, `DATABASE_URL` and `TEST_DATABASE_URL` for DB-writing gates, and routes write-capable smoke through an isolated managed runtime. By default the same DB user is used for the maintenance connection. When that user cannot create databases, pass an explicit maintenance/admin role with `--test-db-admin-user` plus either `--test-db-admin-password-env` or `--test-db-admin-password`; create/drop then uses the maintenance role, while the created database is owned by the backend user from the source URL. With explicit `--managed-runtime`, Python smoke and browser gates are run only after devbootstrap starts its own backend/frontend processes from the current workspace on dynamic ports; occupied selected ports are treated as unsafe and are not reused.

Example with a password kept outside shell history/process listings:

```bash
export P2P_TEST_DB_ADMIN_PASSWORD='<password>'
python tools/devbootstrap.py release-gates \
  --profile full-local-release \
  --test-db-admin-user postgres \
  --test-db-admin-password-env P2P_TEST_DB_ADMIN_PASSWORD
```

PowerShell equivalent:

```powershell
$env:P2P_TEST_DB_ADMIN_PASSWORD = '<password>'
python tools/devbootstrap.py release-gates `
  --profile full-local-release `
  --test-db-admin-user postgres `
  --test-db-admin-password-env P2P_TEST_DB_ADMIN_PASSWORD
```

For installations where the maintenance database is not named `postgres`, use `--test-db-maintenance-db <name>`.

Retention is controlled by one compact policy:

```bash
python tools/devbootstrap.py release-gates --managed-test-db --test-db-retention=drop-always
python tools/devbootstrap.py release-gates --managed-test-db --test-db-retention=keep-on-failure
python tools/devbootstrap.py release-gates --managed-test-db --test-db-retention=keep-always
```

`keep-on-failure` is the default: successful runs drop the database, failed runs keep it and print a masked cleanup command in `managed-test-db.json`, `release-gates.md` and the gate logs. The compatibility alias `--keep-test-db=never|on-failure|always` maps to the same policy.

If the configured PostgreSQL port is closed and you intentionally want devbootstrap to start the project compose service first, add:

```bash
python tools/devbootstrap.py release-gates --managed-test-db --start-db-if-needed
```

For failed runs where the DB is retained, `--dump-test-db-on-failure` attempts a `pg_dump --format=custom` into the run directory when `pg_dump` is available. Reports and bundles store masked database URLs only.

## Managed isolated runtime

`--managed-runtime` makes release-gates stop trusting whatever happens to be listening on the legacy `18080` / `5173` ports. It chooses free loopback ports, starts backend with `APP__HOST`, `APP__PORT` and the selected test database env, starts Vite with `VITE_API_BASE_URL` pointing at that managed backend, then passes the same URLs into Python smoke and Playwright.

Runtime ownership is explicit: devbootstrap stores only its own PID/command/cwd/log paths in the release-gates bundle and stops only those processes during teardown. It never kills a process merely because it occupies a port.

Managed runtime bundle files:

```text
logs/runtime-backend.log or logs/*_managed_backend_process.log
logs/runtime-frontend.log or logs/*_managed_frontend_process.log
logs/runtime-state.json
logs/runtime-env-diff.md
logs/managed-urls.env
```

`runtime-state.json` records selected ports, managed URLs, masked database target, PIDs, process logs and final runtime status. `runtime-env-diff.md` lists only the env overrides added by devbootstrap and masks DB/secrets.

`--managed-runtime` needs a safe DB target for the managed backend. The preferred source is `--managed-test-db`; alternatively set `TEST_DATABASE_URL`. `--allow-dev-db-write` can be used only when writing to the configured dev DB is intentional.

## Recommended local database

Use a separate PostgreSQL database named `p2p_planner_test` for release checks.

For the bundled dev compose service:

```bash
docker compose -f docker-compose.dev.yml up -d postgres

docker exec -i p2p-planner-postgres-dev \
  psql -U postgres -d postgres -tc "SELECT 1 FROM pg_database WHERE datname = 'p2p_planner_test'" \
  | grep -q 1 \
  || docker exec -i p2p-planner-postgres-dev createdb -U postgres p2p_planner_test
```

Then export the explicit test URL before running backend DB gates:

```bash
export TEST_DATABASE_URL=postgres://postgres:postgres@127.0.0.1:5432/p2p_planner_test
```

## Live backend smoke

The Python smoke and real-backend browser path talk to an already running backend. For a fully safe release signal, that backend must also be started against the test database.

A local env setup can look like this:

```env
DATABASE__URL=postgres://postgres:postgres@127.0.0.1:5432/p2p_planner_test
TEST_DATABASE_URL=postgres://postgres:postgres@127.0.0.1:5432/p2p_planner_test
```

After changing the env, restart the backend before running release gates.

## Command matrix

```bash
cd backend
cargo test
TEST_DATABASE_URL=postgres://postgres:postgres@127.0.0.1:5432/p2p_planner_test cargo test -- --include-ignored
BASE_URL=http://127.0.0.1:18080/api/v1 TEST_DATABASE_URL=postgres://postgres:postgres@127.0.0.1:5432/p2p_planner_test python tests/smoke_core_api.py
BASE_URL=http://127.0.0.1:18080/api/v1 TEST_DATABASE_URL=postgres://postgres:postgres@127.0.0.1:5432/p2p_planner_test python tests/smoke_core_api.py
```

The second smoke run is intentional: release gates use it to catch non-idempotent smoke behavior.

A fuller release review can then run:

```bash
python tools/devbootstrap.py release-gates \
  --managed-test-db \
  --managed-runtime \
  --prepare-deps \
  --install-playwright-browsers \
  --include-real-backend-browser \
  --include-clean-machine \
  --clean-machine-profile=dry
```

## Clean-machine sandbox gate

`--include-clean-machine` now runs a structured sandbox gate instead of a one-off quickstart log. Devbootstrap copies the current project to a temporary directory like `/tmp/devbootstrap-clean-machine-<run-id>-*/kanban`, excluding generated or local state: `.git`, `.dev-bootstrap`, `.venv`, `node_modules`, `target`, `dist`, `build`, `coverage`, `__pycache__`, `.pytest_cache`, local env files, bytecode and large release payloads. The copy keeps committed example files such as `backend/.env.example` and `frontend/.env.example`, then checks required startup files before running commands inside the sandbox.

Profiles:

| Profile | What it does | Cost |
|---|---|---|
| `dry` / `clean-machine-dry` | Required files, `self-check`, `diagnose`, `plan`, safe `prepare-env`, and `up --dry-run` with heavy steps skipped. | Low |
| `deps` / `clean-machine-deps` | Everything from `dry`, plus `prepare-frontend --install-mode=stale` and backend `cargo test --no-run` from the sandbox. | Medium |
| `runtime` / `clean-machine-runtime` | Everything from `deps`, plus a nested managed `release-gates --managed-test-db --managed-runtime --prepare-deps` run inside the sandbox. | High |

Retention defaults to `keep-on-failure` so a failed sandbox can be inspected and a successful sandbox is deleted. Use `--clean-machine-retention=delete-always` for CI-like cleanup or `--clean-machine-retention=keep-always` when you intentionally want to inspect the copied project. When the sandbox is kept, the report prints the cleanup command.

The main release-gates bundle includes:

```text
logs/clean-machine/report.md
logs/clean-machine/clean-machine.json
logs/clean-machine/file-list.txt
logs/clean-machine/exclusions.txt
logs/clean-machine/commands.log
```

Example cheap release-review run:

```bash
python tools/devbootstrap.py release-gates --include-clean-machine --clean-machine-profile=dry
```

`--prepare-deps` is the managed dependency preparation umbrella. Bare `--prepare-deps` means `stale` / `missing-or-stale`: release-gates first runs `prepare-frontend --install-mode=stale --no-write-report`, then a backend `cargo test --no-run` warmup, and only after that plans frontend build/test/browser gates using the refreshed marker. The compatibility flag `--prepare-frontend` maps to the same stale mode.

Available dependency modes:

| Mode | Behavior |
|---|---|
| `never` | Do not prepare dependencies; only diagnose and skip/fail gates with precise prerequisites. |
| `missing` | Run `npm ci` only when `frontend/node_modules` is absent. |
| `stale` / `missing-or-stale` | Run `npm ci` when `node_modules` is missing or `.dev-bootstrap/frontend-install.json` does not match package hashes/platform/node/npm. |
| `always` | Run `npm ci` every time. |

The frontend install marker now records package hashes, Node/npm versions, OS/platform fingerprint, install mode and install command. `prepare-frontend` refuses to fall back to `npm install` when `frontend/package-lock.json` is missing unless `--allow-npm-install-without-lock` is passed explicitly, and it treats package/lockfile changes caused by install as a separate dependency failure instead of hiding them inside frontend test failures.

Playwright browser binaries remain an explicit opt-in because the download can be large:

```bash
python tools/devbootstrap.py release-gates --prepare-deps --install-playwright-browsers
```

When browser cache is missing and this flag is enabled, release-gates runs `npx playwright install chromium` as a separate controlled gate before `npm run test:browser`. Without the flag, browser smoke is skipped as `browser_smoke_prerequisite` with a precise next action.

Use `--allow-dev-db-write` only when the configured dev database is disposable and writing into it is intentional.
