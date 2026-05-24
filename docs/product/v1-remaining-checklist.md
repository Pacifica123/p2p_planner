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

Статус: закрыто патчем `local-first runtime baseline`. Основной board/card runtime теперь читает persistent local snapshot, пишет card operations в pending queue и flush-ит их при reconnect через существующий HTTP API. Детали реализации зафиксированы в `docs/architecture/local-first-data-layer-v1.md`, раздел 24.

- [x] Persistent local store на frontend.
- [x] Local schema для workspace/board/column/card.
- [x] Pending operations queue.
- [x] Sync metadata: `synced / pending / failed`.
- [x] Warm start: показать сохраненную доску до network refresh.
- [x] Offline read для уже загруженной доски.
- [x] Offline edit/create/reorder/move card.
- [x] Reconnect flush pending operations.
- [x] UI состояния: `offline`, `saved locally`, `syncing`, `sync failed`.
- [x] Retry failed operation.

Минимальный критерий: пользователь открыл доску, сеть пропала, он изменил карточку, сеть вернулась — изменение не потерялось.

Ограничения baseline:

- это runtime baseline, а не финальный sync protocol;
- labels/checklists/comments для локально созданной новой карточки становятся доступны после sync карточки;
- browser storage adapter намеренно сделан простым и изолированным, чтобы позже заменить его на IndexedDB без переписывания screen-level контрактов.

## 4. Sync baseline

Статус: закрыто патчем `sync baseline`. Sync routes больше не являются `501`-заглушками: backend регистрирует replica, принимает idempotent push events в `change_events`, отдает pull batch по cursor и пишет tombstones для core delete/archive events. Frontend получил browser replica identity и видимый sync baseline banner на board screen.

- [x] Replica registration.
- [x] Client replica identity.
- [x] Monotonic `replicaSeq`.
- [x] Push changes.
- [x] Pull changes by cursor.
- [x] Idempotency по `eventId` или `replicaId + replicaSeq`.
- [x] Duplicate-safe apply.
- [x] Tombstone-aware delete/archive для core entities.
- [x] Visible sync status на frontend.
- [x] Smoke/integration test: повторный push не создает дубликаты.

Ограничения baseline:

- local-first card CRUD flush пока остается на domain HTTP API, чтобы не смешивать event-log baseline с domain replay за один патч;
- pull сохраняет cursor metadata, но frontend пока не применяет входящий stream в entity projections автоматически;
- conflict handling ограничен duplicate/out-of-order/rejected markers, без полноценного merge UI.

## 5. Export / backup safety net

Статус: закрыто патчем `export backup safety net`. Dedicated import/export endpoints больше не возвращают фиктивные counts: backend формирует versioned workspace/board JSON bundle с `manifest.json`, payload sections и restore hints, frontend умеет скачать board-level backup с board screen, а import preview валидирует supplied bundle manifest без destructive restore.

- [x] Export workspace или board в versioned JSON bundle.
- [x] `manifest.json` внутри export bundle.
- [x] Явно описать, что входит в export.
- [x] Import preview или import-as-copy.
- [x] Никакого destructive restore по умолчанию.
- [x] Smoke: export созданной board/card структуры.
- [x] README: как сделать backup/export.

Ограничения baseline:

- bundle является application-level JSON snapshot, а не raw DB dump и не sync-log replay;
- attachment blobs зарезервированы, но не экспортируются;
- import execution остается non-destructive boundary и возвращает `preview_required`; реальное apply/import-as-copy остается будущим hardening slice.

## 6. Auth/security hardening

Статус: закрыто патчем `auth security hardening`. Детали baseline зафиксированы в `docs/architecture/security-privacy-threat-model-v1.1.md`, раздел 23: dev-header auth ограничен local/dev/test профилями, CORS/JWT/cookie config получил startup guards, sync push/pull усилены workspace access boundaries, а smoke покрывает negative auth и derived endpoint access cases.

- [x] `AUTH__ENABLE_DEV_HEADER_AUTH=false` в beta/profile по умолчанию.
- [x] `X-User-Id` оставить только для local/dev.
- [x] CORS allowlist без wildcard для beta/self-host.
- [x] JWT/secret values не default.
- [x] Refresh cookie атрибуты под deployment profile.
- [x] Sign-out чистит frontend session state.
- [x] Sign-out-all инвалидирует refresh family.
- [x] Negative auth smoke: no token / wrong token / forbidden workspace.
- [x] Derived endpoints проверяют access: activity/audit/export/sync.
- [x] Логи не содержат password/token/secret.

Ограничения baseline:

- MFA/passkeys/E2EE не входят в v1 hardening;
- local-first snapshot encryption не реализован;
- browser smoke по реальному backend остается частью следующего release-gates блока.

## 7. Testing and release gates

Автоматизация будущего полного прогона этого блока зафиксирована в `docs/dev-bootstrap/devbootstrap-v2-release-gates-plan.md`. До реализации v2 эти пункты остаются ручными gates; важно не считать mocked browser smoke заменой real backend browser path.

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
