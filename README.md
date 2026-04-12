# P2P Planner

P2P Planner — экспериментальный **web-first / local-first** планировщик задач в стиле Kanban.
Текущий статус репозитория: **рабочий vertical slice для core flow** + appearance + activity,
поверх Axum/PostgreSQL backend и React/Vite frontend.

## Что уже есть

- workspaces → boards → columns → cards;
- drag-and-drop перемещение карточек между колонками;
- card details drawer;
- board activity / card activity / workspace audit log API surface;
- user appearance + board appearance;
- OpenAPI draft и docs по архитектуре;
- smoke-проверки для backend happy-path.

## Текущее ограничение

Полный auth/session UX еще не доведен end-to-end.
Для dev-flow frontend и smoke-тесты используют временный `X-User-Id` header.

## Структура репозитория

```text
backend/   Axum + sqlx + PostgreSQL
frontend/  React + Vite + TanStack Query
docs/      ADR, архитектурные решения, OpenAPI, MVP scope
```

## Быстрый запуск

### 1. Backend

Нужен PostgreSQL. Далее:

```bash
cd backend
cargo run
```

Health endpoints:

- `GET /health`
- `GET /api/v1/health`

По умолчанию backend слушает `127.0.0.1:18080` и применяет миграции на старте.
Подробности и dev notes: `backend/README.md`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

По умолчанию frontend ходит в `http://127.0.0.1:18080/api/v1`.
При необходимости создай `.env.local`:

```bash
VITE_API_BASE_URL=http://127.0.0.1:18080/api/v1
VITE_DEV_USER_ID=11111111-1111-7111-8111-111111111111
```

## Где смотреть документацию

- `docs/README.md` — карта документов;
- `docs/product/mvp-scope-v1.md` — границы MVP;
- `docs/architecture/backend-modules.md` — карта backend-модулей;
- `docs/architecture/frontend_architecture_v_1.md` — структура frontend;
- `docs/api/openapi.yaml` — текущий HTTP-контракт.

## Что имеет смысл делать дальше

- local-first клиентский слой;
- sync implementation plan;
- conflict resolution policy;
- security/privacy/threat model;
- доведение auth/session flow до полноценного UX.
