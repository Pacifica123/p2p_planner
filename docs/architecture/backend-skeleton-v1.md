# Backend skeleton v1

## Scope of this step
This step creates a bootable backend foundation for the already approved MVP and architecture:
- PostgreSQL + sqlx migrations on startup
- axum HTTP server
- config + app state + tracing + error layer
- modular router registration
- file skeletons for `dto / handler / service / repo`

## What is already real
- the application boots if PostgreSQL is available and migrations can run;
- health endpoints are live:
  - `GET /health`
  - `GET /api/v1/health`
  - `GET /api/v1/auth/session` returns a skeleton response;
- all main route groups are already registered;
- the database schema is split into ordered migrations instead of one draft file.

## What is intentionally still stubbed
Business logic for domain modules is not implemented yet. These routes are wired and return `not_implemented` until the next step:
- auth write operations
- users/devices
- workspaces/members
- boards/columns
- cards
- labels
- checklists/items
- comments
- sync
- audit-log

## Project layout added in backend
- `config/default.toml`
- `.env.example`
- `src/app.rs`
- `src/config.rs`
- `src/state.rs`
- `src/error.rs`
- `src/telemetry.rs`
- `src/db/*`
- `src/http/*`
- `src/auth/*`
- `src/modules/*`

## Why this shape
This keeps consistency with earlier decisions:
- modular monolith;
- `dto / handler / service / repo` layering;
- separate `auth` and `sync` concerns;
- `boards` own columns, `workspaces` own membership;
- sync-ready schema exists before full sync logic.

## Next step
The next practical step is `Core backend logic`:
- implement real CRUD for `workspaces`, `boards`, `columns`, `cards`;
- add minimal auth/session persistence;
- start replacing stub repos with real sqlx queries.
