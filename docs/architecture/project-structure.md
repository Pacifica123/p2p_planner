# Структура каталогов проекта

Ниже зафиксирована рекомендуемая структура репозитория на ближайшие итерации.

```text
docs/
  README.md
  adr/
  api/
    openapi.yaml
  product/
    mvp-scope-v1.md
  domain/
    terms.md
    entities.md
    invariants.md
    permissions.md
    lifecycle.md
    customization.md
  sync/
    glossary.md
    protocol.md
    conflict-resolution.md
    schemas/
  architecture/
    project-structure.md
    database.md
    backend-modules.md
    conflict-resolution-v1.md
    p2p-relay-bootstrap-abstraction-v1.md

backend/
  migrations/
  scripts/
    smoke_api/
  src/
    auth/
    common/
    db/
    http/
    modules/
      workspaces/
      boards/
      board_appearance/
      cards/
      labels/
      checklists/
      comments/
      attachments/
      custom_fields/
      activity/
      integrations/
      sync/
      users/
      invitations/
    transport/
      bootstrap/
      relay/
      discovery/
    app.rs
    config.rs
    error.rs
    lib.rs
    main.rs
    models.rs
    state.rs

frontend/
  src/
    public/
    src/
      app/
        layouts/
        providers/
        router/
        styles/
      features/
        auth/
        workspace-switcher/
        boards/
        board-settings/
        cards/
        labels/
        checklists/
        comments/
        activity/
        integrations/
        sync-status/
        settings-appearance/
      shared/
        api/
        config/
        lib/
        sync/
          engine/
          transport/
          topology/
        types/
        ui/

mobile/
  app/
  features/
  shared/

shared-contracts/
  api/
  sync/
  types/
```

## Принципы

### 1. Документы живут рядом с кодом
Архитектурные решения и контракты не должны жить только "в голове" или в чате.

### 2. Product-first reading order
Сначала читается `product/`, затем термины и glossary, потом ADR и только после
этого детали домена, БД и sync-протокола.

### 3. Backend модульный
Модули backend группируются по домену, а не по техническим таблицам.

### 4. Frontend feature-based
Функциональность сгруппирована по пользовательским сценариям и bounded context'ам.

### 5. Shared contracts выделены отдельно
Если появится необходимость делить типы и схемы между клиентами, для этого
уже есть место в структуре.

### 6. Mobile вводится позже
Каталог mobile резервируется заранее, но не раздувает current scope.


### 7. Transport/topology слой выделяется отдельно
Даже если concrete runtime сначала coordinator-only, в структуре заранее
резервируется место для `transport`, `bootstrap`, `relay`, `discovery` и
frontend-side sync/transport adapters. Это нужно, чтобы optional p2p
добавлялся как отдельный слой, а не растекался по UI и CRUD-модулям.
