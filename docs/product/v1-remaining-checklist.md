# Что осталось допилить до v1

Этот список фиксирует только то, что осталось после патча `contract archive reorder baseline`.

## 1. Contract parity sweep

Статус: закрыто патчем `contract parity sweep`. Детали зафиксированы в `docs/api/contract-parity-sweep-v1.md`, а повторяемая проверка добавлена как `python tools/contract_parity_sweep.py --check`.

- [x] Сверить оставшиеся backend routes, frontend API calls и OpenAPI paths после archive/reorder/card lifecycle baseline.
- [x] Найти frontend-кнопки, которые ведут в отсутствующие или stub routes.
- [x] Обновить OpenAPI под оставшийся фактический beta-surface.
- [x] Зафиксировать, какие routes являются real v1, а какие deferred/internal.

Итог sweep по подозрительным зонам:

- labels/checklists/comments оставлены как `deferred_stub` до minimal card enrichment slice;
- sync оставлен как `deferred_stub` до sync baseline;
- import/export/integrations/webhooks помечены как `contract_stub`, потому что surface есть, но настоящего исполнения bundle/import/webhook еще нет;
- user/device naming выровнен: `DELETE /me/devices/{deviceId}` вместо несуществующего revoke-route.

## 2. Минимально полезная карточка

Выбран вариант A: не скрывать labels/checklists/comments, а реализовать минимальный рабочий slice.

Статус: закрыто патчем `minimal card enrichment slice`. Backend-заглушки labels/checklists/comments заменены рабочими CRUD/assignment flows, OpenAPI переведен в `real_v1`, а `CardDetailsDrawer` получил UI для labels, checklists и comments.

- [x] Labels: создать label на доске.
- [x] Labels: назначить label на карточку.
- [x] Labels: снять label с карточки.
- [x] Labels: переименовать/удалить label.
- [x] Checklists: создать checklist.
- [x] Checklists: добавить item.
- [x] Checklists: отметить item done/undone.
- [x] Checklists: удалить item.
- [x] Comments: добавить comment.
- [x] Comments: показать comments timeline в карточке.
- [x] Comments: редактировать/удалить свой comment, если берем это в v1.
- [x] Activity: писать события labels/checklists/comments.
- [x] Frontend: добавить UI в `CardDetailsDrawer`.
- [x] Smoke/browser test: покрыть минимальный card enrichment flow через backend smoke API; browser smoke остается mocked critical boot-flow.

## 3. Local-first runtime baseline

- [ ] Persistent local store на frontend.
- [ ] Local schema для workspace/board/column/card.
- [ ] Pending operations queue.
- [ ] Sync metadata: `synced / pending / failed`.
- [ ] Warm start: показать сохраненную доску до network refresh.
- [ ] Offline read для уже загруженной доски.
- [ ] Offline edit/create/reorder/move card.
- [ ] Reconnect flush pending operations.
- [ ] UI состояния: `offline`, `saved locally`, `syncing`, `sync failed`.
- [ ] Retry failed operation.

Минимальный критерий: пользователь открыл доску, сеть пропала, он изменил карточку, сеть вернулась — изменение не потерялось.

## 4. Sync baseline

- [ ] Replica registration.
- [ ] Client replica identity.
- [ ] Monotonic `replicaSeq`.
- [ ] Push changes.
- [ ] Pull changes by cursor.
- [ ] Idempotency по `eventId` или `replicaId + replicaSeq`.
- [ ] Duplicate-safe apply.
- [ ] Tombstone-aware delete/archive для core entities.
- [ ] Visible sync status на frontend.
- [ ] Smoke/integration test: повторный push не создает дубликаты.

## 5. Export / backup safety net

- [ ] Export workspace или board в versioned JSON bundle.
- [ ] `manifest.json` внутри export bundle.
- [ ] Явно описать, что входит в export.
- [ ] Import preview или import-as-copy.
- [ ] Никакого destructive restore по умолчанию.
- [ ] Smoke: export созданной board/card структуры.
- [ ] README: как сделать backup/export.

## 6. Auth/security hardening

- [ ] `AUTH__ENABLE_DEV_HEADER_AUTH=false` в beta/profile по умолчанию.
- [ ] `X-User-Id` оставить только для local/dev.
- [ ] CORS allowlist без wildcard для beta/self-host.
- [ ] JWT/secret values не default.
- [ ] Refresh cookie атрибуты под deployment profile.
- [ ] Sign-out чистит frontend session state.
- [ ] Sign-out-all инвалидирует refresh family.
- [ ] Negative auth smoke: no token / wrong token / forbidden workspace.
- [ ] Derived endpoints проверяют access: activity/audit/export/sync.
- [ ] Логи не содержат password/token/secret.

## 7. Testing and release gates

- [ ] `cargo test`.
- [ ] `python tests/smoke_core_api.py`.
- [ ] `npm run build`.
- [ ] `npm run test:run`.
- [ ] `npm run test:browser`.
- [ ] Browser smoke проверяет реальный backend path.
- [ ] Smoke идемпотентен на повторных прогонах.
- [ ] Clean-machine quickstart проверен.
- [ ] README соответствует реальному запуску.
- [ ] Release notes + known limitations обновлены.

## 8. Devctl / packaging hygiene

- [ ] Убедиться, что `target/`, `node_modules/`, `dist/`, `build/` не попадают в snapshots.
- [ ] Убедиться, что `release/**/*.zip` и `release/**/*.exe` заменяются заглушками.
- [ ] Добавить exclude для `*.tsbuildinfo`.
- [ ] Проверить, нужны ли generated `vite.config.js/.d.ts`; если нет — исключить.
- [ ] Проверить, что патчи всегда идут в новом формате: `manifest.json + files/...`.

## Release decision

Если готовы local-first + sync baseline:

```text
v1.0.0-beta.1
```

Если есть только web/core без полноценного local-first/sync:

```text
v1.0.0-web-preview.1
```

## Короткая формула продолжения

1. remaining contract parity;
2. minimal card enrichment;
3. local-first runtime;
4. sync baseline;
5. export/backup;
6. security hardening;
7. tests/release gates.

Самый первый следующий практический патч: **minimal card enrichment slice** — labels/checklists/comments вместо backend-заглушек.
