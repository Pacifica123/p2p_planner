# Release-gates test database

`devbootstrap release-gates` deliberately treats DB-writing checks as unsafe unless a write-safe database target is explicit. This keeps regular dev data from being modified by backend smoke, DB integration tests, or the real-backend browser path.


## Managed ephemeral database

The recommended one-command path is now:

```bash
python tools/devbootstrap.py release-gates --managed-test-db
```

With this flag, `release-gates` derives a PostgreSQL maintenance connection from `DATABASE__URL` / `DATABASE_URL`, creates an isolated database named like `p2pkanban_rg_<toolVersion>_<timestamp>_<id>`, and overrides `DATABASE__URL`, `DATABASE_URL` and `TEST_DATABASE_URL` for DB-writing gates. The Python smoke and opt-in real-backend browser gate are run only after devbootstrap starts its own backend process against that managed DB; an already occupied backend port is treated as unsafe and is not reused.

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
  --prepare-frontend \
  --install-playwright-browsers \
  --include-real-backend-browser \
  --include-clean-machine
```

`--prepare-frontend` runs `prepare-frontend` inside the same release-gates bundle before frontend build/test/browser gates are planned. This is useful when `frontend/node_modules` or `.dev-bootstrap/frontend-install.json` is missing/stale.

Use `--allow-dev-db-write` only when the configured dev database is disposable and writing into it is intentional.
