# Sync lifecycle map v1

- Статус: Draft v1
- Дата: 2026-04-12
- Назначение: зафиксировать сквозной жизненный цикл sync-состояния для клиента и backend coordinator.

> Это operational map для этапа реализации. Он не заменяет protocol/glossary, а показывает, как именно движется состояние через boot, local mutation, push, pull, reconcile и recovery.

---

## 1. High-level lifecycle

```text
BOOT
  -> replica registration
  -> local store recovery
  -> hydration decision
      -> snapshot/bootstrap path
      -> incremental pull path
  -> scope becomes ready

LOCAL MUTATION
  -> local commit
  -> pending op created
  -> entity marked pending
  -> push scheduled

PUSH
  -> batch assembly
  -> server validate/dedupe
  -> change_events append
  -> current-state apply
  -> ack returned
  -> local pending finalized

PULL
  -> request after cursor
  -> ordered server events returned
  -> local apply
  -> reconciliation
  -> cursor advance

RECOVERY
  -> retry/backoff on transient failure
  -> failed/conflict marker on semantic failure
  -> needs_snapshot on cursor invalidation / long-gap recovery
```

---

## 2. Boot lifecycle

```text
App start
  -> open persistent local store
  -> restore replica metadata, cursors, pending_ops, entity_meta
  -> determine network state
  -> if replica not registered: register replica
  -> classify each scope:
       - hydrated and warm
       - cached but stale
       - empty and not hydrated
       - broken / needs snapshot
  -> start background sync engine
```

### Boot decisions

### A. Warm boot
- локальные данные уже есть;
- экран может рендериться сразу;
- sync engine делает background pull.

### B. Cold boot
- нужного scope локально нет;
- сначала нужен bootstrap/snapshot-like hydration path;
- после seed состояния scope переходит на incremental pull.

### C. Offline boot
- локальные данные есть -> рендерим их и помечаем offline;
- локальных данных нет -> показываем `offline and nothing cached`.

---

## 3. Outbound mutation lifecycle

```text
User action
  -> validate command locally
  -> local transaction:
       - patch domain records
       - update entity_meta
       - create/coalesce pending op
       - assign replicaSeq/logicalClock
  -> UI shows new state immediately
  -> push job scheduled
```

### Local statuses after commit
- entity: `pending_create | pending_update | pending_delete`
- operation: `queued`
- scope: `hasPendingChanges = true`
- app surface: `Saved locally` / `Changes pending`

---

## 4. Push lifecycle

```text
Sync engine selects pending ops
  -> group by scope
  -> sort by replicaSeq
  -> build push batch
  -> POST /sync/push
  -> server validates each event
      -> duplicate
      -> rejected
      -> conflict
      -> accepted
  -> server writes change_events + assigns serverOrder
  -> server applies event to domain state
  -> server returns per-event results
  -> client finalizes local pending state
```

### Client reaction to push results

#### `accepted`
- pending op closed;
- entity can stay locally visible;
- source event waits for later pull normalization if needed.

#### `duplicate`
- pending op closed as no-op;
- no user-facing error.

#### `rejected`
- pending op gets failure state;
- entity keeps local state only if это не вводит пользователя в заблуждение;
- UI получает retry/discard surface.

#### `conflict`
- pending op gets conflict marker;
- либо canonical outcome уже выбран и создается `conflict_stub`/review marker;
- либо операция требует manual resolution/retry/discard согласно `docs/architecture/conflict-resolution-v1.md`.

---

## 5. Inbound pull lifecycle

```text
Sync trigger
  -> choose scope cursor
  -> POST /sync/pull
  -> receive ordered events after lastServerOrder
  -> apply one by one to local store
  -> update entity_meta and projections
  -> persist new cursor only after full durable apply
  -> if hasMore: continue pull loop
```

### Client apply rules
- inbound apply is idempotent;
- ordering is strictly by `serverOrder`;
- tombstones are processed before stale local resurrection becomes possible;
- own earlier events may arrive back through server stream and must not duplicate domain records.

---

## 6. Reconciliation lifecycle

```text
Inbound event arrives
  -> detect relation to local entity
  -> detect relation to local pending op / recent ack
  -> normalize local domain state
  -> clear dirtyFields if server state supersedes them
  -> preserve failure marker if event did not actually resolve issue
  -> write final entity_meta
```

### Typical reconciliation outcomes

#### A. Clean convergence
- local state and server stream agree;
- entity becomes `synced`.

#### B. Accepted but still stale locally
- push succeeded, but richer canonical state came only with later pull;
- local record updated from inbound event.

#### C. Failure convergence
- server rejected operation;
- local state marked `failed/retryable`;
- cursor still moves for unrelated incoming events.

#### D. Snapshot required
- server says cursor invalid or gap too large;
- scope enters `needs_snapshot` and exits normal incremental loop.

---

## 7. Snapshot recovery lifecycle

```text
Scope marked needs_snapshot
  -> pause normal incremental pull for this scope
  -> fetch fresh snapshot/bootstrap state
  -> replace or carefully re-seed local records for this scope
  -> write fresh seeded cursor
  -> resume incremental pull from new baseline
```

### Safety rules
- snapshot reset is scope-local, not global by default;
- pending ops for the same scope must be reviewed before destructive reseed;
- client must not merge fresh snapshot with stale cursor lineage blindly.

---

## 8. Failure and retry lifecycle

```text
Network failure
  -> operation remains queued/retryable
  -> app surface becomes offline/degraded
  -> exponential backoff starts
  -> reconnect retriggers push/pull

Semantic failure
  -> no blind auto-retry loop
  -> failed/conflict marker kept
  -> user may retry after editing or discard local change
```

### Retry categories
- transient network/server unavailable -> automatic retry;
- unauthorized/revoked replica -> requires re-auth / re-registration;
- validation/business rejection -> requires user or app-level intervention;
- snapshot_required/cursor_expired -> requires recovery flow.

---

## 9. Scope lifecycle summary

```text
empty
  -> hydrating
  -> ready
  -> syncing
  -> ready

ready
  -> has_pending_changes
  -> pushing
  -> pulling
  -> reconciling
  -> ready

ready/syncing
  -> degraded
  -> backoff
  -> ready

ready/syncing
  -> needs_snapshot
  -> hydrating
  -> ready
```

---

## 10. Operational checkpoints

На этапе реализации система считается корректной, если выполняются такие checkpoints:
- локальная мутация переживает reload до sync;
- push дубликата не создает дублей на сервере;
- pull повтора не создает дублей локально;
- cursor не двигается до durable apply;
- offline не уничтожает уже видимое локальное состояние;
- snapshot recovery не ломает соседние scope;
- UI умеет различать `pending`, `syncing`, `failed`, `conflict_stub`, `needs_snapshot`.
