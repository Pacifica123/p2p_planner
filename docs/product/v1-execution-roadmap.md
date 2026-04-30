# v1 execution roadmap и contract parity baseline

Документ фиксирует не идеальную архитектурную картину, а текущее фактическое состояние проекта перед добиванием v1/beta. Его задача — не дать перепутать:

- **реализованную рабочую фичу**;
- **частично рабочий вертикальный срез**;
- **API/модуль, который уже заведен, но внутри все еще stub/not implemented**;
- **future-ready контракт, который не должен выглядеть как обещанная v1-фича**.

Этот файл должен быть первой точкой входа для следующих патчей по v1: сначала сверяемся с ним, потом меняем код/контракты/docs.

## Статусы

| Статус | Значение |
| --- | --- |
| `Done` | Фича есть в backend/frontend/docs и может использоваться в текущем ручном сценарии. |
| `Partial` | Есть рабочий slice, но границы или hardening еще не закрыты. |
| `Blocker` | Нельзя обещать v1/beta без реализации, скрытия из UI или явного изменения scope. |
| `Contract mismatch` | Backend, frontend и/или OpenAPI описывают разные маршруты/семантику. |
| `Deferred` | Осознанно отложено после v1 и не должно быть видимой пользовательской фичей. |
| `Internal stub` | Контракт/модуль существует для будущего, но текущий ответ stub-only/manifest-only/not implemented. |
| `Out of v1` | Не входит в v1 даже как must-have beta path. |

## Текущая правда о состоянии проекта

| Область | Статус | Что считать правдой сейчас | Решение для v1 |
| --- | --- | --- | --- |
| Auth/session | `Partial` | Frontend использует sign-up/sign-in/refresh/session/sign-out и `Authorization: Bearer ...`. `X-User-Id` остается legacy/dev-test fallback за флагом. | Довести security gates, negative auth smoke и production/dev profile boundaries. |
| Workspace/board/column/card core CRUD | `Partial` | Основной flow уже рабочий: создать workspace, board, columns, cards; открыть board; редактировать card; move между columns. | Закрыть route mismatches вокруг archive/delete и reorder. |
| Card DnD между columns | `Done` | Межколоночное перемещение использует `POST /cards/{cardId}/move`, backend route есть. | Оставить в v1 path. |
| Card DnD внутри одной column | `Contract mismatch` | Frontend вызывает `POST /columns/{columnId}/cards/reorder`, но backend route отсутствует. | Либо реализовать route, либо временно отключить same-column reorder. Для v1 лучше реализовать. |
| Workspace/board archive buttons | `Contract mismatch` | UI вызывает `POST /workspaces/{workspaceId}/archive` и `POST /boards/{boardId}/archive`, но backend сейчас имеет `DELETE /workspaces/{workspaceId}` и `DELETE /boards/{boardId}` с soft-delete semantics. | Выбрать канонику: добавить archive endpoints или переименовать UI/API в delete. Для UX лучше archive endpoints. |
| Card archive/unarchive | `Partial` | Backend и frontend имеют `POST /cards/{cardId}/archive` и `/unarchive`; OpenAPI вместо этого описывает `/complete` и `/restore`. | Обновить OpenAPI под фактические routes или переименовать backend/frontend. |
| Appearance/customization | `Done` | User appearance и board appearance заведены, есть backend/frontend/API wiring и smoke/integration контекст. | Оставить в v1 path. |
| Activity/history/audit | `Partial` | Board activity, card activity, workspace audit log заведены и наполняются core mutation-flow. | Оставить в v1 path, но помнить: labels/checklists/comments пока не пишут activity, потому что сами не реализованы. |
| Labels | `Blocker` | Backend routes заведены, но repo возвращает `not_implemented`; OpenAPI path shape отличается от backend. Видимого frontend UI сейчас нет. | Для v1 либо реализовать минимальный slice, либо явно скрыть/отложить. Рекомендация: реализовать минимальный slice. |
| Checklists | `Blocker` | Backend routes заведены, но repo возвращает `not_implemented`; есть path mismatch по checklist item routes. Видимого frontend UI сейчас нет. | Для v1 либо реализовать минимальный slice, либо явно скрыть/отложить. Рекомендация: реализовать минимальный slice. |
| Comments | `Blocker` | Backend routes заведены, но repo возвращает `not_implemented`; видимого frontend UI сейчас нет. | Для v1 либо реализовать минимальный slice, либо явно скрыть/отложить. Рекомендация: реализовать минимальный slice. |
| Local-first runtime | `Blocker` | Docs есть, но в frontend runtime пока нет persistent local store, pending ops, offline/reconnect queue или visible sync state. | Нужен отдельный implementation patch до beta, если релиз называется local-first beta. |
| Sync routes | `Blocker` | Routes заведены, repo возвращает `not_implemented`; OpenAPI не полностью совпадает с backend methods. | Нужен backend-coordinated sync baseline или честное переименование релиза в web-preview. |
| Import/export/backup | `Internal stub` | Есть provider/capabilities/import-export endpoints. Portable export возвращает manifest-oriented stub, import/restore не мутирует domain state. | Для v1 нужен минимальный реальный export bundle или пометка как preview/internal. |
| Integrations/webhooks | `Deferred` / `Internal stub` | Provider registry и webhook boundary заведены, но orchestration/signature verification/command translation не реализованы. | Не показывать как пользовательскую v1-фичу. Оставить как internal future-ready boundary. |
| P2P/full relay/bootstrap | `Out of v1` | Архитектурные docs есть, обязательного пользовательского runtime нет. | Не блокирует v1, если sync baseline идет через backend. |
| Mobile | `Out of v1` | Отложено до стабилизации web/backend/sync. | Не учитывать в v1 release gate. |

## Что сейчас можно тестить руками

Минимальный ручной happy-path, который соответствует текущей реальности:

1. Поднять PostgreSQL через `docker-compose.dev.yml` или локальный PostgreSQL.
2. Запустить backend:
   ```bash
   cd backend
   cargo run
   ```
3. Запустить frontend:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
4. В web UI пройти auth-flow через sign-up/sign-in.
5. Создать workspace.
6. Создать board.
7. Создать columns.
8. Создать cards.
9. Открыть card details drawer.
10. Изменить title/description/status/priority.
11. Переместить card в другую column.
12. Проверить card history / board activity.
13. Проверить user appearance и board appearance.

Что **пока не считать надежным ручным сценарием**:

- архивирование workspace/board через UI;
- reorder карточек внутри той же column;
- labels/checklists/comments;
- реальный offline/local-first runtime;
- sync push/pull;
- реальный import/restore;
- production-like security hardening.

## Contract parity sweep: текущий baseline

### Backend routes, которые существуют фактически

Core/auth/appearance/activity/audit routes:

```text
POST   /auth/sign-up
POST   /auth/sign-in
POST   /auth/refresh
POST   /auth/sign-out
POST   /auth/sign-out-all
GET    /auth/session
POST   /auth/dev-bootstrap
GET    /me
GET    /me/devices
DELETE /me/devices/{deviceId}
GET    /me/appearance
PUT    /me/appearance
GET    /workspaces
POST   /workspaces
GET    /workspaces/{workspaceId}
PATCH  /workspaces/{workspaceId}
DELETE /workspaces/{workspaceId}
GET    /workspaces/{workspaceId}/members
POST   /workspaces/{workspaceId}/members
PATCH  /workspaces/{workspaceId}/members/{memberId}
DELETE /workspaces/{workspaceId}/members/{memberId}
GET    /workspaces/{workspaceId}/boards
POST   /workspaces/{workspaceId}/boards
GET    /workspaces/{workspaceId}/audit-log
GET    /boards/{boardId}
PATCH  /boards/{boardId}
DELETE /boards/{boardId}
GET    /boards/{boardId}/columns
POST   /boards/{boardId}/columns
PATCH  /columns/{columnId}
DELETE /columns/{columnId}
PATCH  /boards/{boardId}/columns/{columnId}
DELETE /boards/{boardId}/columns/{columnId}
GET    /boards/{boardId}/cards
POST   /boards/{boardId}/cards
GET    /cards/{cardId}
PATCH  /cards/{cardId}
DELETE /cards/{cardId}
POST   /cards/{cardId}/move
POST   /cards/{cardId}/archive
POST   /cards/{cardId}/unarchive
GET    /boards/{boardId}/activity
GET    /cards/{cardId}/activity
GET    /boards/{boardId}/appearance
PUT    /boards/{boardId}/appearance
```

Routes that are wired but not implemented or stub-only:

```text
GET    /boards/{boardId}/labels                  -> repo not_implemented
POST   /boards/{boardId}/labels                  -> repo not_implemented
PATCH  /labels/{labelId}                         -> repo not_implemented
DELETE /labels/{labelId}                         -> repo not_implemented
PUT    /cards/{cardId}/labels                    -> repo not_implemented
GET    /cards/{cardId}/checklists                -> repo not_implemented
POST   /cards/{cardId}/checklists                -> repo not_implemented
PATCH  /checklists/{checklistId}                 -> repo not_implemented
DELETE /checklists/{checklistId}                 -> repo not_implemented
POST   /checklists/{checklistId}/items           -> repo not_implemented
PATCH  /checklist-items/{itemId}                 -> repo not_implemented
DELETE /checklist-items/{itemId}                 -> repo not_implemented
GET    /cards/{cardId}/comments                  -> repo not_implemented
POST   /cards/{cardId}/comments                  -> repo not_implemented
PATCH  /comments/{commentId}                     -> repo not_implemented
DELETE /comments/{commentId}                     -> repo not_implemented
GET    /sync/status                              -> repo not_implemented
GET    /sync/replicas                            -> repo not_implemented
POST   /sync/replicas                            -> repo not_implemented
POST   /sync/push                                -> repo not_implemented
GET    /sync/pull                                -> repo not_implemented
POST   /integrations/import-jobs                 -> stub_only
POST   /integrations/export-jobs                 -> stub_only
POST   /integrations/import-export/exports       -> ready_stub, manifest only
POST   /integrations/import-export/imports/preview -> preview_stub
POST   /integrations/import-export/imports       -> accepted_stub, no mutation
POST   /integrations/webhooks/{providerKey}      -> stub_only
```

### Frontend API calls, которые сейчас есть

Known-good or mostly-good calls:

```text
POST   /auth/sign-in
POST   /auth/sign-up
POST   /auth/refresh
GET    /auth/session
POST   /auth/sign-out
POST   /auth/sign-out-all
GET    /workspaces
POST   /workspaces
PATCH  /workspaces/{workspaceId}
GET    /workspaces/{workspaceId}/boards
POST   /workspaces/{workspaceId}/boards
GET    /boards/{boardId}
PATCH  /boards/{boardId}
GET    /boards/{boardId}/columns
POST   /boards/{boardId}/columns
PATCH  /boards/{boardId}/columns/{columnId}
DELETE /boards/{boardId}/columns/{columnId}
GET    /boards/{boardId}/cards
POST   /boards/{boardId}/cards
GET    /cards/{cardId}
PATCH  /cards/{cardId}
DELETE /cards/{cardId}
POST   /cards/{cardId}/move
POST   /cards/{cardId}/archive
POST   /cards/{cardId}/unarchive
GET    /boards/{boardId}/activity
GET    /cards/{cardId}/activity
GET    /me/appearance
PUT    /me/appearance
GET    /boards/{boardId}/appearance
PUT    /boards/{boardId}/appearance
```

Frontend calls requiring a fix before v1:

```text
POST   /workspaces/{workspaceId}/archive         -> visible UI button, backend route missing
POST   /boards/{boardId}/archive                 -> visible UI button, backend route missing
POST   /columns/{columnId}/cards/reorder         -> DnD same-column reorder, backend route missing
```

Frontend integration/import-export API helpers exist, but should remain internal/not surfaced as a v1 user feature until real export/import behavior is implemented.

### OpenAPI mismatches found in this sweep

| Area | OpenAPI says | Backend/frontend reality | v1 decision needed |
| --- | --- | --- | --- |
| Current user update | `PATCH /me` | Backend has `GET /me`, no `PATCH /me`. | Add backend route or remove/defer OpenAPI path. |
| Device revoke | `POST /me/devices/{deviceId}/revoke` | Backend has `DELETE /me/devices/{deviceId}`. | Pick one canonical route. |
| Workspace archive | `POST /workspaces/{workspaceId}/archive` | Frontend calls it; backend has `DELETE /workspaces/{workspaceId}` soft-delete. | Add archive route or change UI/OpenAPI to delete. |
| Board archive | `POST /boards/{boardId}/archive` | Frontend calls it; backend has `DELETE /boards/{boardId}` soft-delete. | Add archive route or change UI/OpenAPI to delete. |
| Column reorder | `POST /boards/{boardId}/columns/reorder` | Backend route absent; frontend does not currently call this exact route. | Implement or remove from beta OpenAPI. |
| Card same-column reorder | `POST /columns/{columnId}/cards/reorder` | Frontend calls it; backend route absent. | Implement before v1 or disable same-column reorder. |
| Card lifecycle | `POST /cards/{cardId}/complete`, `POST /cards/{cardId}/restore` | Backend/frontend use `/archive` and `/unarchive`; no `/complete` route. | Update OpenAPI to archive/unarchive, or change implementation. |
| Labels | `/boards/{boardId}/labels/{labelId}`, `POST /cards/{cardId}/labels`, `DELETE /cards/{cardId}/labels/{labelId}` | Backend uses `/labels/{labelId}` and `PUT /cards/{cardId}/labels`; repo not implemented. | Implement minimal slice and align paths. |
| Checklist item routes | `/checklists/items/{itemId}` | Backend uses `/checklist-items/{itemId}`; repo not implemented. | Pick canonical route while implementing. |
| Sync pull | `POST /sync/pull` | Backend has `GET /sync/pull`; repo not implemented. | Pick canonical method before sync implementation. |
| Sync replicas | OpenAPI has `POST /sync/replicas`; backend also has `GET /sync/replicas`. | `GET /sync/replicas` missing from OpenAPI. | Add to OpenAPI or remove route. |

## v1 execution checklist from this point

### 0. Truth document and README alignment

- [x] Add `docs/product/v1-execution-roadmap.md`.
- [x] Define status vocabulary: `Done`, `Partial`, `Blocker`, `Deferred`, `Internal stub`, `Out of v1`, `Contract mismatch`.
- [x] Mark labels/checklists/comments as `Blocker` unless scope is reduced.
- [x] Mark sync routes as `Blocker` for a real local-first beta.
- [x] Mark integrations/webhooks as `Deferred` / `Internal stub`.
- [x] Mark mobile and full p2p/relay/bootstrap as `Out of v1`.
- [x] Add a short “what can be tested manually now” section.
- [ ] Keep root README in sync after each v1 blocker is closed.

### 1. Contract parity sweep

- [x] Inventory backend routes from `backend/src/**/mod.rs`.
- [x] Inventory frontend API calls from `frontend/src/features/**/api/*.ts`.
- [x] Inventory OpenAPI paths from `docs/api/openapi.yaml`.
- [x] Identify routes returning `not_implemented` or stub-only responses.
- [x] Identify visible UI paths that can currently call missing backend routes.
- [ ] Decide canonical route semantics for archive/delete/reorder/lifecycle.
- [ ] Update backend/frontend/OpenAPI to the selected canonical contract.
- [ ] Add contract parity smoke/check so these mismatches do not silently return.

### 2. Immediate blocker queue

Recommended next patch order:

1. **Archive/reorder contract fix**: workspace archive, board archive, same-column card reorder.
2. **OpenAPI alignment**: card archive/unarchive, user/device routes, labels/checklists/comments canonical paths, sync method shape.
3. **Card enrichment minimal slice**: labels/checklists/comments backend + frontend or explicit deferral/hiding.
4. **Local-first runtime baseline**: local store, pending ops, offline/reconnect surface.
5. **Sync baseline**: replicas, push/pull, idempotency, cursors.
6. **Real export safety net**: at least one real portable export bundle path.
7. **Security/release gates**: auth negative smoke, profile boundaries, CORS/JWT/session hardening.

## Release naming rule

Use this rule until blockers are closed:

- If local-first runtime and sync baseline are not implemented, call the next demo release `web-preview`, not `local-first beta`.
- If local-first runtime and backend-coordinated sync baseline are implemented and tested, `v1.0.0-beta.1` is a fair name.

Suggested gate:

```text
v1.0.0-web-preview.1  -> web core flow is usable, but local-first/sync are not real yet
v1.0.0-beta.1         -> web core + local-first runtime + sync baseline + export safety net
```
