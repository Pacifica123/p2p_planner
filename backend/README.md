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

## Auth / session model

Основной API-flow сейчас идет через `Authorization: Bearer ...`: frontend получает access token на `/auth/sign-in`, `/auth/sign-up` или `/auth/refresh`, а refresh token хранится в cookie. Protected endpoints должны извлекать пользователя из bearer-сессии.

Legacy `X-User-Id` fallback оставлен только для dev/test сценариев и выключен по умолчанию через `AUTH__ENABLE_DEV_HEADER_AUTH=false`. Его не нужно считать нормальным browser flow и не нужно возвращать в CORS без отдельного решения.

## Smoke tests

- `tests/core_crud_smoke.rs`
- `tests/appearance_smoke.rs`
- `tests/smoke_core_api.py`

Integration tests требуют `TEST_DATABASE_URL` или `DATABASE_URL`.
