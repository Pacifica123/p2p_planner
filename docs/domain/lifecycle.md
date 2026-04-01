# Жизненный цикл сущностей

> Важно: жизненный цикл ниже описывает **целевую модель состояний**.
> Не все состояния обязаны иметь отдельный UI или отдельную пользовательскую фичу в MVP.

## Workspace
Стадии:
1. created
2. active
3. archived
4. deleted

### Переходы
- created -> active
- active -> archived
- archived -> active
- active -> deleted
- archived -> deleted

## WorkspaceInvitation
Стадии:
1. created
2. active
3. accepted
4. revoked
5. expired

### Комментарий
Как отдельная пользовательская сущность invitation flow не обязателен для MVP.

## Board
Стадии:
1. created
2. active
3. archived
4. deleted

### Комментарий
Архивированная доска сохраняет данные, но обычные пользовательские изменения
по умолчанию блокируются или требуют явного восстановления.

## Column
Стадии:
1. created
2. active
3. deleted

### Комментарий
Удаление колонки требует стратегии обработки карточек:
- move to another column;
- archive cards;
- reject delete while non-empty.

Эта политика должна быть определена в прикладном сервисе.

## Card
Стадии:
1. created
2. active
3. completed
4. deleted

### Комментарий
`completed` — доменное состояние, не обязательно физическое перемещение в отдельную колонку.
Отдельное архивирование card допустимо как расширение, но не считается обязательной
отдельной стадией MVP.

## ChecklistItem
Стадии:
1. created
2. active
3. completed
4. deleted

## Comment
Стадии:
1. created
2. edited
3. deleted

## IntegrationConnection
Стадии:
1. created
2. active
3. degraded
4. revoked
5. deleted

### Комментарий
Это future-ready сущность и не обязательна для MVP.

## Replica
Стадии:
1. created
2. active
3. stale
4. revoked

## Замечание по реализации

Жизненный цикл не обязан один-в-один совпадать с одним enum в БД. В части
случаев он моделируется комбинацией полей:
- `is_archived` или `archived_at`
- `status`
- `deleted_at`
- tombstone
- `revoked_at`
