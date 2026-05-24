# Release-gates test database

`devbootstrap release-gates` deliberately treats DB-writing checks as unsafe unless a write-safe database target is explicit. This keeps regular dev data from being modified by backend smoke, DB integration tests, or the real-backend browser path.

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
  --include-real-backend-browser \
  --include-clean-machine \
  --install-playwright-browsers
```

Use `--allow-dev-db-write` only when the configured dev database is disposable and writing into it is intentional.
