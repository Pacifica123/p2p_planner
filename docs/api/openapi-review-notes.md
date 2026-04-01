# OpenAPI v1 review notes

## Что было не так в исходном файле
- `openapi.yaml` был скорее skeleton, чем полный v1-контракт.
- Маршруты auth/sync расходились с уже зафиксированной module map.
- В теги были добавлены `labels`, `checklists`, `comments`, но CRUD для них почти отсутствовал.
- Были зашиты `appearance` и `integrations`, хотя они вынесены за пределы MVP v1.
- Для большинства операций не хватало request/response схем и единого error envelope.
- Не были нормально оформлены session/device/replica-aware auth flows.
- Пагинация, фильтрация и сортировка были либо отсутствующими, либо неявными.

## Что исправлено
- Выровнен набор маршрутов под module map:
  - `auth/sign-up`, `auth/sign-in`, `auth/refresh`, `auth/sign-out`, `auth/sign-out-all`, `auth/session`
  - `me`, `me/devices`, revoke device
  - `workspaces`, `workspace members`
  - `boards`, `columns`
  - `cards`, `move`, `complete`, `restore`, `reorder`
  - `labels`, `checklists`, `comments`
  - `sync/replicas`, `sync/push`, `sync/pull`, `sync/status`
- Убраны `appearance` и `integrations` из v1-спеки как не-MVP surface.
- Добавлен единый `ErrorResponse`.
- Добавлены схемы почти для всех request/response DTO.
- Для коллекций введен cursor-based pagination там, где он реально нужен.
- Для `columns` оставлен полный ordered snapshot без pagination.
- Для `cards` добавлены фильтры и сортировка.
- Для auth описаны `bearerAuth` и `refreshTokenCookie`.
- Для sync добавлены `Replica`, `SyncCursor`, push/pull request/response и batch results.

## Что осталось открытым
- `POST /workspaces/{workspaceId}/members` сейчас добавляет участника по `userId`.
  Для удобного UX почти наверняка позже понадобится либо user lookup endpoint,
  либо email/invite flow.
- Политика public sign-up помечена как deployment-level choice:
  self-hosted инстанс может держать `auth/sign-up`, а может выключить его.
- Спека синтаксически парсится и все внутренние `$ref` разрешаются,
  но полноценный внешний OpenAPI validator в этой среде я не запускал.


## Appearance / customization follow-up

После отдельного customization-этапа в v1 добавлены endpoints `GET/PUT /me/appearance` и `GET/PUT /boards/{boardId}/appearance`, а также соответствующие схемы для user preferences и board appearance settings. Image-wallpapers и theme registry по-прежнему остаются за пределами текущего API slice.
