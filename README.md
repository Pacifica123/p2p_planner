# P2P Planner

P2P Planner — экспериментальный **web-first / local-first** планировщик задач в стиле Kanban.
Текущий статус репозитория: **рабочий vertical slice для core flow** + appearance + activity,
поверх Axum/PostgreSQL backend и React/Vite frontend.

## Что уже есть

- workspaces → boards → columns → cards;
- drag-and-drop перемещение карточек между колонками;
- card details drawer;
- board activity / card activity / workspace audit log API surface;
- labels / checklists / comments as a минимально полезная карточка baseline;
- local-first board/card runtime baseline with persistent snapshot and pending card ops;
- sync baseline: replicas, push/pull cursor, tombstones for core deletes;
- export / backup safety net: workspace/board JSON bundle + non-destructive import preview;
- user appearance + board appearance;
- OpenAPI draft и docs по архитектуре;
- smoke-проверки для backend happy-path.

## Что пока не считать готовым v1 surface

Текущий репозиторий содержит несколько future-ready контрактов и stub-модулей. Они полезны для архитектуры, но не должны восприниматься как уже готовые пользовательские фичи:

- destructive import/restore execution — intentionally disabled; use import preview, actual apply/import-as-copy mutation is future work;
- integrations/webhooks and generic provider job orchestration — reserved/internal contracts and stub receipts;
- mobile и full p2p/relay/bootstrap — out of v1.

Актуальная карта правды и contract parity baseline: `docs/product/v1-execution-roadmap.md`.

## Текущее auth-состояние

Основной web-flow уже использует `auth/session`: frontend получает access token через `sign-in` / `sign-up` / `refresh` и отправляет его как `Authorization: Bearer ...`. Refresh-сессия живет в cookie.

`X-User-Id` больше не является обычным frontend/dev-flow. В backend он оставлен только как legacy/dev-test fallback за флагом `AUTH__ENABLE_DEV_HEADER_AUTH=false` по умолчанию.

Для beta/self-host/production-like профилей backend теперь валидирует security env на старте: `X-User-Id` не попадает в CORS headers без local/dev header-auth режима, wildcard CORS запрещен, `AUTH__COOKIE_SECURE=true` обязателен, а `AUTH__JWT_SECRET` должен быть реальным non-default секретом.

## Структура репозитория

```text
backend/   Axum + sqlx + PostgreSQL
frontend/  React + Vite + TanStack Query
docs/      ADR, архитектурные решения, OpenAPI, MVP scope
```

## Автодиагностика и env-подготовка dev-среды

Текущие слои будущего авторазвертывателя доступны как безопасные команды диагностики/env-подготовки и guarded-команда запуска PostgreSQL:

```bash
python tools/devbootstrap.py self-check --no-write-report
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
python tools/devbootstrap.py release-gates --dry-run
python tools/devbootstrap.py release-gates
python tools/devbootstrap.py release-gates --managed-test-db
python tools/devbootstrap.py release-gates --managed-test-db --prepare-frontend --install-playwright-browsers
python tools/devbootstrap.py release-gates --managed-test-db --prepare-frontend --install-playwright-browsers --include-real-backend-browser
python tools/devbootstrap.py release-gates --prepare-frontend --include-clean-machine
python tools/devbootstrap.py status
python tools/devbootstrap.py stop --dry-run
python tools/devbootstrap.py stop
```

Финальный v1-hardening слой добавляет `self-check`: встроенные fixtures для env parser/diff, URL parse, failure classifiers, root discovery, report JSON contract и release-gates v2 contracts. Его стоит запускать после каждого патча к `tools/devbootstrap.py` вместе с `ast.parse`.

`release-gates` — v2-агрегатор по принципу одной команды: он запускает реализованные backend/frontend/browser/docs gates с keep-going semantics, пишет `summary.txt`, `release-gates.md`, `release-gates.json`, `logs/*.log` и собирает маленький `release-gates_*.zip` в `.dev-bootstrap/runs/...`. Для write-safe DB-прогонов используй `--managed-test-db`: devbootstrap создает одноразовую PostgreSQL БД `p2pkanban_rg_*`, переопределяет `DATABASE__URL` / `DATABASE_URL` / `TEST_DATABASE_URL`, стартует собственный backend для write-capable smoke и применяет retention policy `--test-db-retention=drop-always|keep-on-failure|keep-always`. Если frontend dependencies отсутствуют или marker устарел, обычный запуск честно остановит frontend gates как infra failure; для одного самодостаточного прогона используй `--prepare-frontend`, тогда `prepare-frontend` будет выполнен внутри того же release-gates bundle до планирования frontend build/test/browser gates. Real-backend browser path и clean-machine quickstart сделаны явными opt-in gates, потому что пишут в live backend/DB или создают временную clean-machine копию проекта.

Обычные `diagnose`, `plan`, `prepare-env`, `diagnose --section postgres`, `start-db`, `check-backend`, `start-backend`, `prepare-frontend`, `start-frontend` и `up` дополнительно сохраняют отчеты в `.dev-bootstrap/runs/...`; эта служебная папка игнорируется Git. Phase 1 проверяет корень проекта, обязательные файлы, доступные инструменты, порты и базовые health URL. Phase 2 читает env-контракт, показывает diff ключей, маскирует секреты и безопасно создает отсутствующие `backend/.env` / `frontend/.env.local` из example-файлов без перезаписи существующих env. Phase 3 проверяет PostgreSQL target из `DATABASE__URL`, умеет классифицировать частые проблемы БД и может поднять compose-сервис `postgres`, если configured port закрыт. Phase 4 добавляет backend-проверку через `cargo metadata` / `cargo check` и guarded `cargo run` с PID/state/log capture и ожиданием `/health` + `/api/v1/health`. Phase 5 добавляет frontend-подготовку через `npm ci` / `npm install`, install-marker для `node_modules`, guarded `npm run dev`, `frontend.log`, PID/state и проверку `VITE_API_BASE_URL` против backend health. Phase 6 добавляет `up`: единый безопасный pipeline `diagnose → plan → prepare-env → start-db → check-backend → start-backend → prepare-frontend → start-frontend → smoke → report` с `--dry-run`, skip-флагами и остановкой на первом блокирующем сбое. Phase 7 добавляет отдельные smoke gates: `quick` проверяет backend/frontend HTTP-доступность, `standard` добавляет backend Python smoke и frontend `npm run test:run`, `full` добавляет browser smoke через `npm run test:browser`. Для write-capable backend smoke нужен `TEST_DATABASE_URL` или явный `--allow-dev-db-write`, чтобы случайно не писать в обычную dev-БД. Phase 8 закрывает lifecycle: `status` показывает tracked PID/ports/health/compose snapshot, а `stop` завершает только backend/frontend процессы из `.dev-bootstrap/state.json`; PostgreSQL compose service останавливается только при явном `stop --include-db`. Phase 9 поднимает инструмент до `1.0.0`, фиксирует общий JSON-envelope отчетов, централизует timeout policy и добавляет `self-check` как внутренний v1 sanity suite.

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
- `docs/api/openapi.yaml` — текущий HTTP-контракт;
- `docs/dev-bootstrap/devbootstrap-v1-operations.md` — quick commands, report contract, timeout policy and cleanup rules for devbootstrap v1.

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
10. проверить user appearance и board appearance;
11. нажать `💾` на board screen и скачать board-level `*.bundle.json` backup.

Не опирайся пока на destructive restore/import execution, webhook delivery и full conflict-resolution UI как на стабильные сценарии.

## Backup / export safety net

Минимальный ручной backup уже доступен двумя способами.

Через UI: открой board screen и нажми `💾`. Frontend запросит `backup_snapshot` для текущей board, включит archived/activity/appearance sections и скачает JSON файл вида `p2p-planner-backup-snapshot-board-<uuid>-<job>.bundle.json`.

Через API:

```bash
curl -X POST http://127.0.0.1:18080/api/v1/integrations/import-export/exports \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "scopeKind": "board",
    "boardId": "<board-id>",
    "exportMode": "backup_snapshot",
    "includeArchived": true,
    "includeActivityHistory": true,
    "includeAppearance": true
  }'
```

Ответ содержит `bundle` — это self-describing application-level JSON artifact с ключом `manifest.json` и payload sections: `workspaces`, `boards`, `columns`, `cards`, `labels`, `cardLabels`, `checklists`, `checklistItems`, `comments`, `boardAppearanceSettings`, `activityEntries`. Bundle не содержит sessions, access/refresh tokens, provider secrets, sync cursors или raw DB dump.

Безопасный preview:

```bash
curl -X POST http://127.0.0.1:18080/api/v1/integrations/import-export/imports/preview \
  -H "Authorization: Bearer <access-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "importMode": "restore_backup",
    "restoreStrategy": "create_copy",
    "bundle": { "manifest.json": { "format": "p2p_planner_bundle", "formatVersion": 1 } }
  }'
```

По умолчанию destructive restore не выполняется: execution endpoint в v1 возвращает `preview_required` и не мутирует domain state.

## Что имеет смысл делать дальше

- провести production-hardening auth/session flow и account-management UX;
- довести import-as-copy/apply flow после preview;
- расширить release gates и browser smoke на real backend path.

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

`test:browser` запускает только mocked exact-spec `e2e/smoke/auth-and-workspaces.smoke.spec.ts`. Write-capable no-mock сценарий вынесен в отдельный opt-in script:

```bash
cd frontend
npm run test:browser:real-backend
```

Для безопасного DB-writing release review подготовь отдельную test DB по инструкции `docs/dev-bootstrap/release-gates-test-database.md` и запускай real-backend browser gate через `python tools/devbootstrap.py release-gates --prepare-frontend --install-playwright-browsers --include-real-backend-browser`.
