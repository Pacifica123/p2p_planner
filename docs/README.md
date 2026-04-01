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
- `sync/` — glossary, протокол синхронизации и conflict policy.
- `architecture/` — структура каталогов, карта backend-модулей, карта БД и auth/identity решения.
- `api/openapi.yaml` — черновой HTTP-контракт между backend и web-клиентом.

## Зафиксированные принципы

1. Проект строится как **local-first** система.
2. **Web-клиент — первый клиент** и основной носитель MVP.
3. **Backend обязателен для MVP** как HTTP/API слой, auth/session слой и
   координатор синхронизации.
4. **P2P-синхронизация опциональна и не входит в MVP** как обязательный
   пользовательский сценарий.
5. Мобильный клиент и развитые интеграции откладываются до стабилизации core.
6. Архитектура сохраняет future-ready задел под реплики, change log,
   tombstones, relay/bootstrap и внешние adapters.

## Как читать эти документы

1. Сначала `product/mvp-scope-v1.md`.
2. Затем `domain/terms.md` и `sync/glossary.md`.
3. Затем `adr/`.
4. После этого `domain/entities.md`, `domain/invariants.md`, `domain/permissions.md`.
5. Затем `architecture/database.md`, `architecture/backend-modules.md`,
   `architecture/auth-and-identity-v1.md`, `architecture/appearance-customization-v1.md`
   и `architecture/project-structure.md`.
6. И только потом `api/openapi.yaml`, `sync/protocol.md` и
   `sync/conflict-resolution.md`.

## Статус

Документы в этом каталоге являются **docs v2**: они уточняют границы между MVP и
future-ready архитектурой, фиксируют термины и снимают двусмысленность вокруг
local-first, sync и optional p2p.
