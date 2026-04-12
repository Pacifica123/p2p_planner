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
    local-first-data-layer-v1.md
    sync-model-implementation-plan-v1.md
    conflict-resolution-v1.md
    p2p-relay-bootstrap-abstraction-v1.md
    integrations-architecture-v1.md
    import-export-backup-v1.md

backend/
  migrations/
  tests/
  src/
    auth/
    db/
    http/
    modules/
      activity/
      appearance/
      audit/
      boards/
      cards/
      checklists/
      comments/
      integrations/
      labels/
      sync/
      users/
      workspaces/
      common.rs
      mod.rs
    app.rs
    config.rs
    error.rs
    lib.rs
    main.rs
    state.rs
    telemetry.rs

frontend/
  src/
    app/
      layouts/
      providers/
      router/
      styles/
    features/
      activity/
      appearance/
      boards/
      bootstrap/
      cards/
      columns/
      integrations/
      workspaces/
    shared/
      api/
      appearance/
      config/
      lib/
      types/
      ui/
    main.tsx
```

## Принципы

### 1. Документы живут рядом с кодом
Архитектурные решения и контракты не должны жить только "в голове" или в чате.

### 2. Product-first reading order
Сначала читается `product/`, затем термины и glossary, потом ADR и только после
этого детали домена, БД, local-first, sync и integrations.

### 3. Backend модульный
Модули backend группируются по домену, а не по техническим таблицам.

### 4. Frontend feature-based
Функциональность сгруппирована по пользовательским сценариям и bounded context'ам.

### 5. Shared contracts могут быть вынесены позже
Когда появится реальная необходимость делить типы и схемы между несколькими
клиентами, для этого можно добавить отдельный слой shared contracts без ломки
текущей структуры.

### 6. Mobile вводится позже
Каталог mobile сознательно не раздувает текущий runtime scope, пока не
стабилизированы backend, web и sync contracts.

### 7. Transport/topology слой выделяется отдельно по смыслу
Даже если concrete runtime сначала coordinator-only, в архитектуре заранее
резервируется место для `transport`, `bootstrap`, `relay`, `discovery` и
frontend-side sync/transport adapters. Это нужно, чтобы optional p2p
добавлялся как отдельный слой, а не растекался по UI и CRUD-модулям.

### 8. Integrations выделяются отдельным слоем
Даже если реальные provider implementations пока остаются заглушками,
`integrations/` резервирует единое место для provider registry, import/export
orchestration и webhook boundaries. Это уменьшает риск того, что
GitHub/Obsidian/import/export логика потом начнет протекать в `boards`, `cards`
или `sync`.
