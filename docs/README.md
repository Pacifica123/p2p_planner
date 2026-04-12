# Документация проекта P2P Planner

Этот каталог фиксирует базовые архитектурные решения и контракты проекта
универсального **web-first local-first** планировщика задач в стиле Kanban.

Важно различать два слоя:
- **v1 / MVP** — то, что обязуемся довести до первой рабочей версии;
- **future-ready architecture** — то, к чему готовим модель данных, контракты и
  границы модулей, не обещая это в первом релизе.

## Назначение документов

- `product/mvp-scope-v1.md` — продуктовые границы первой версии.
- `adr/` — принятые архитектурные решения.
- `domain/` — доменная модель, инварианты, права доступа, жизненный цикл и термины.
- `sync/` — glossary, протокол синхронизации и каноническая conflict policy.
- `architecture/` — структура каталогов, карта backend-модулей, карта БД, auth/identity, appearance, activity/history/audit, local-first data layer, инженерный sync plan и transport/p2p abstraction.
- `api/openapi.yaml` — черновой HTTP-контракт между backend и web-клиентом.

## Зафиксированные принципы

1. Проект строится как **local-first** система.
2. **Web-клиент — первый клиент** и основной носитель MVP.
3. **Backend обязателен для MVP** как HTTP/API слой, auth/session слой и
   координатор синхронизации.
4. **P2P-синхронизация опциональна и не входит в MVP** как обязательный
   пользовательский сценарий.
5. Мобильный клиент откладывается до стабилизации core, а интеграции проектируются заранее как isolated adapter layer без hard dependency на MVP core flow.
6. Архитектура сохраняет future-ready задел под реплики, change log,
   tombstones, relay/bootstrap и внешние adapters.

## Как читать эти документы

1. Сначала `product/mvp-scope-v1.md`.
2. Затем `domain/terms.md` и `sync/glossary.md`.
3. Затем `adr/`.
4. После этого `domain/entities.md`, `domain/invariants.md`, `domain/permissions.md`.
5. Затем `architecture/database.md`, `architecture/backend-modules.md`,
   `architecture/auth-and-identity-v1.md`, `architecture/appearance-customization-v1.md`,
   `architecture/activity-history-audit-v1.md`, `architecture/local-first-data-layer-v1.md`,
   `architecture/sync-model-implementation-plan-v1.md`,
   `architecture/sync-lifecycle-map-v1.md`,
   `architecture/frontend-visible-sync-state-model-v1.md`,
   `architecture/conflict-resolution-v1.md`,
   `architecture/p2p-relay-bootstrap-abstraction-v1.md`,
   `architecture/integrations-architecture-v1.md`
   и `architecture/project-structure.md`.
6. И только потом `api/openapi.yaml`, `sync/protocol.md` и
   `sync/conflict-resolution.md`.

## Статус

Документы в этом каталоге являются **docs v2**: они уточняют границы между MVP и
future-ready архитектурой, фиксируют термины и снимают двусмысленность вокруг
local-first, sync и optional p2p.

- `docs/architecture/web-frontend-core-ui-v1.md` — web frontend core UI v1: app shell, screen composition, shared primitives, backend CRUD wiring.

- `docs/architecture/local-first-data-layer-v1.md` — local-first data layer v1: persistent local store, hydration, pending ops, optimistic updates и offline UX rules.

- `docs/architecture/sync-model-implementation-plan-v1.md` — инженерный план MVP sync: actors, units, push/pull, reconciliation, batching, ordering, idempotency, snapshot vs incremental.

- `docs/architecture/sync-lifecycle-map-v1.md` — сквозная lifecycle map для boot, local mutation, push, pull, reconciliation и snapshot recovery.

- `docs/architecture/frontend-visible-sync-state-model-v1.md` — frontend-visible sync state: app-level, scope-level и entity-level surface model для local-first UX.

- `docs/architecture/conflict-resolution-v1.md` — подробная conflict matrix v1: taxonomy, resolution rules, examples, edge-cases и user-facing UX policy.

- `docs/architecture/p2p-relay-bootstrap-abstraction-v1.md` — transport-neutral P2P / relay / bootstrap abstraction: layered boundaries, discovery/bootstrap roles, relay-compatible design и phased rollout.

- `docs/architecture/integrations-architecture-v1.md` — integrations architecture v1: provider registry, import/export touchpoints, webhooks, domain-event boundary и adapter isolation.
