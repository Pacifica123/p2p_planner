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

## Что пока не считать готовым v1 surface

Текущий репозиторий содержит несколько future-ready контрактов и stub-модулей. Они полезны для архитектуры, но не должны восприниматься как уже готовые пользовательские фичи:

- labels / checklists / comments — routes заведены, но backend repo еще возвращает `not_implemented`;
- sync push/pull/replicas — routes заведены, но runtime implementation еще не готов;
- local-first client runtime — описан в docs, но persistent local store / pending ops / offline queue еще не реализованы;
- integrations/webhooks/import orchestration — существуют как reserved/internal contracts и stub responses;
- mobile и full p2p/relay/bootstrap — out of v1.

Актуальная карта правды и contract parity baseline: `docs/product/v1-execution-roadmap.md`.

## Текущее auth-состояние

Основной web-flow уже использует `auth/session`: frontend получает access token через `sign-in` / `sign-up` / `refresh` и отправляет его как `Authorization: Bearer ...`. Refresh-сессия живет в cookie.

`X-User-Id` больше не является обычным frontend/dev-flow. В backend он оставлен только как legacy/dev-test fallback за флагом `AUTH__ENABLE_DEV_HEADER_AUTH=false` по умолчанию.

## Структура репозитория

```text
backend/   Axum + sqlx + PostgreSQL
frontend/  React + Vite + TanStack Query
docs/      ADR, архитектурные решения, OpenAPI, MVP scope
```

## Автодиагностика и env-подготовка dev-среды

Текущие слои будущего авторазвертывателя доступны как безопасные команды диагностики/env-подготовки и guarded-команда запуска PostgreSQL:

```bash
python tools/devbootstrap.py diagnose --no-write-report
python tools/devbootstrap.py plan --no-write-report
python tools/devbootstrap.py prepare-env
python tools/devbootstrap.py diagnose --section postgres --no-write-report
python tools/devbootstrap.py start-db --dry-run
python tools/devbootstrap.py check-backend --dry-run
python tools/devbootstrap.py start-backend --dry-run
python tools/devbootstrap.py prepare-frontend --dry-run
python tools/devbootstrap.py start-frontend --dry-run
python tools/devbootstrap.py up --dry-run
python tools/devbootstrap.py smoke --level quick
python tools/devbootstrap.py smoke --level standard --allow-dev-db-write
python tools/devbootstrap.py status
```

Обычные `diagnose`, `plan`, `prepare-env`, `diagnose --section postgres`, `start-db`, `check-backend`, `start-backend`, `prepare-frontend`, `start-frontend` и `up` дополнительно сохраняют отчеты в `.dev-bootstrap/runs/...`; эта служебная папка игнорируется Git. Phase 1 проверяет корень проекта, обязательные файлы, доступные инструменты, порты и базовые health URL. Phase 2 читает env-контракт, показывает diff ключей, маскирует секреты и безопасно создает отсутствующие `backend/.env` / `frontend/.env.local` из example-файлов без перезаписи существующих env. Phase 3 проверяет PostgreSQL target из `DATABASE__URL`, умеет классифицировать частые проблемы БД и может поднять compose-сервис `postgres`, если configured port закрыт. Phase 4 добавляет backend-проверку через `cargo metadata` / `cargo check` и guarded `cargo run` с PID/state/log capture и ожиданием `/health` + `/api/v1/health`. Phase 5 добавляет frontend-подготовку через `npm ci` / `npm install`, install-marker для `node_modules`, guarded `npm run dev`, `frontend.log`, PID/state и проверку `VITE_API_BASE_URL` против backend health. Phase 6 добавляет `up`: единый безопасный pipeline `diagnose → plan → prepare-env → start-db → check-backend → start-backend → prepare-frontend → start-frontend → smoke → report` с `--dry-run`, skip-флагами и остановкой на первом блокирующем сбое. Phase 7 добавляет отдельные smoke gates: `quick` проверяет backend/frontend HTTP-доступность, `standard` добавляет backend Python smoke и frontend `npm run test:run`, `full` добавляет browser smoke через `npm run test:browser`. Для write-capable backend smoke нужен `TEST_DATABASE_URL` или явный `--allow-dev-db-write`, чтобы случайно не писать в обычную dev-БД.

Если env-файл уже существует, `prepare-env` не меняет его по умолчанию. Для аккуратного добавления недостающих ключей из example-файлов есть явный режим:

```bash
python tools/devbootstrap.py prepare-env --add-missing-keys
```

Перед таким изменением создается backup рядом с исходным env-файлом.

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
VITE_ENABLE_PROJECT_ROADMAP_SEED=true
```

## Где смотреть документацию

- `docs/README.md` — карта документов;
- `docs/product/v1-execution-roadmap.md` — текущая правда перед v1 и contract parity baseline;
- `docs/product/mvp-scope-v1.md` — границы MVP;
- `docs/architecture/backend-modules.md` — карта backend-модулей;
- `docs/architecture/frontend_architecture_v_1.md` — структура frontend;
- `docs/api/openapi.yaml` — текущий HTTP-контракт.

## Что можно тестить руками сейчас

Реалистичный ручной happy-path на текущем состоянии:

1. sign-up / sign-in;
2. создать workspace;
3. создать board;
4. создать columns;
5. создать cards;
6. открыть card details drawer;
7. изменить title / description / status / priority;
8. переместить card в другую column;
9. посмотреть card history / board activity;
10. проверить user appearance и board appearance.

Не опирайся пока на workspace/board archive buttons, same-column card reorder, labels/checklists/comments, offline/local-first runtime и sync push/pull как на стабильные сценарии.

## Что имеет смысл делать дальше

- закрыть contract mismatches: archive/delete/reorder/card lifecycle;
- реализовать или явно скрыть labels/checklists/comments;
- добавить local-first клиентский runtime;
- реализовать sync baseline;
- сделать реальный export/backup safety net;
- провести production-hardening auth/session flow и account-management UX.

## Тестирование

На текущем этапе в репозитории уже есть backend smoke и integration проверки, а общая стратегия описана в:

- `docs/architecture/testing-strategy-v1.md`;
- `docs/architecture/testing-pyramid-v1.md`;
- `docs/architecture/testing-application-guide-v1.md`;
- `backend/tests/SMOKE_SCENARIOS.md`.

Быстрые полезные команды:

```bash
cd frontend
npm install
npm run test:run
```

```bash
cd backend
python tests/smoke_core_api.py
```

```bash
cd backend
cargo test --test core_crud_smoke -- --ignored
cargo test --test appearance_smoke -- --ignored
```

```bash
cd frontend
npm run test:browser
```
