# p2p-planner backend

Текущая backend-часть — это Axum + sqlx + PostgreSQL сервис для core kanban flow,
appearance и activity/audit surface.

## Что уже заведено

- bootable HTTP server;
- config loading from `config/default.toml` + environment variables;
- PostgreSQL pool;
- startup migrations;
- app state + tracing + error envelope;
- modular router composition;
- core CRUD для `workspaces / boards / columns / cards`;
- appearance endpoints;
- activity / history / audit read-model endpoints.

## Запуск локально

1. Подними PostgreSQL и создай базу `p2p_planner`.
2. Проверь `.env`.
3. Запусти backend:

```bash
cargo run
```

Health endpoints:

- `GET /health`
- `GET /api/v1/health`

## Dev auth bridge

Пока полноценный auth/session flow не доведен до финального UX,
core CRUD и frontend dev-flow используют временный `X-User-Id` header.

Из-за этого для web-клиента важно, чтобы CORS разрешал `x-user-id`.

## Smoke tests

- `tests/core_crud_smoke.rs`
- `tests/appearance_smoke.rs`
- `tests/smoke_core_api.py`

Integration tests требуют `TEST_DATABASE_URL` или `DATABASE_URL`.
