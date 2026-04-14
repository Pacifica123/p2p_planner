# Testing strategy v1

## 1. Цель документа

- Назначение: определить **слоистую тестовую стратегию** для проекта, а не свести качество только к unit-тестам.
- Цель: зафиксировать, **какие тесты обязательны**, что именно проверяется на backend и frontend, как проверять contract/sync/conflict-сценарии и какие правила нужны для reproducibility в local-first системе.

> Этот документ опирается на `openapi.yaml`, local-first/sync/conflict/security документы и текущее состояние репозитория, где backend уже имеет рабочие smoke/integration проверки, а frontend уже получил базовый Vitest + Testing Library harness и короткий browser smoke слой.

## 2. Базовые принципы

Проекту нужна не "максимально большая куча тестов", а **предсказуемое покрытие по рискам**.

Принимаются следующие принципы:

1. **Layered testing, not one test type.** Unit, integration, contract и smoke решают разные задачи и не заменяют друг друга.
2. **Fast feedback first.** На PR должны доминировать быстрые проверки; дорогие сценарии допускаются как selective или nightly.
3. **Contract-first integration.** Backend и frontend должны сходиться не по догадкам, а по HTTP/OpenAPI контракту и явно зафиксированным fixtures.
4. **Local-first realism.** Для клиента и sync-слоя важны offline/pending/failed/replay cases, а не только happy-path online CRUD.
5. **Determinism over incidental success.** Тест не должен проходить только потому, что “сегодня повезло со временем, порядком событий или уже грязной dev-БД”.
6. **Replayability.** Sync/conflict кейсы должны уметь воспроизводиться из фиксированных входных наборов: события, порядок применения, cursor state, membership state.
7. **Black-box smoke keeps the slice honest.** Минимальный живой smoke должен подтверждать, что вертикальный slice реально работает на запущенном приложении.

## 3. Testing pyramid проекта

В этом проекте пирамида должна быть такой:

1. **Основа — unit tests.**
   Быстрые проверки доменной логики, маппинга DTO, селекторов, reducers/store helpers, валидаторов, merge/apply функций и error mapping.
2. **Основной рабочий слой — integration tests.**
   Именно здесь проверяется большая часть реальной ценности проекта: router + service + repo + DB на backend, а на frontend — экран/feature поверх local store, query layer и mocked transport.
3. **Тонкий, но обязательный слой — contract tests.**
   Они подтверждают, что backend реально отдает формы данных, на которые рассчитывает frontend и sync client.
4. **Очень тонкий верх — smoke / e2e.**
   Небольшое число жизненно важных end-to-end сценариев, которые ловят поломку vertical slice, auth/session flow, wiring, CORS, migrations и базовые регрессии.

Это значит:
- unit тестов должно быть **больше всего**;
- integration тесты — **второй по массе обязательный слой**;
- contract tests — **небольшие, но обязательные для API/sync surface**;
- smoke/e2e — **мало, но стабильно и регулярно**.

## 4. Разделение по слоям

### 4.1. Backend

#### Backend unit
Проверяют локальную логику без реальной БД и без поднятого HTTP приложения.

Обязательные зоны:
- валидация входных значений;
- преобразование request DTO -> domain intent;
- error mapping в API errors;
- auth/token helpers;
- sync envelope validation helpers;
- conflict-resolution helpers там, где они выделены в чистые функции.

#### Backend integration
Проверяют собранное приложение или крупные его куски.

Обязательные зоны:
- router -> handler -> service -> repo -> PostgreSQL;
- migrations against real PostgreSQL;
- CRUD и derived endpoints (`activity`, `audit`, `appearance`, `me`, `session`);
- authorization boundaries;
- soft delete / tombstone-visible behavior;
- idempotency и duplicate apply в sync-ready поверхностях.

#### Backend contract
Проверяют, что фактический HTTP слой соответствует `docs/api/openapi.yaml` и согласованным error envelopes.

Минимум:
- status codes;
- envelope shape (`data` / `error`);
- обязательные поля в ключевых responses;
- enum/string compatibility для frontend-visible полей;
- sync endpoint payload shapes, когда они начнут реально жить.

#### Backend smoke
Проверяют запущенный backend как black box.

Минимум:
- health;
- sign-up / sign-in / session;
- core CRUD slice;
- derived endpoints `activity/audit/appearance`;
- sign-out / anonymous rejection;
- отсутствие 500 там, где ожидается 2xx/4xx.

### 4.2. Frontend

#### Frontend unit
Проверяют изолированные функции и небольшие компоненты.

Обязательные зоны:
- selectors, mappers и formatters;
- API response -> UI model mapping;
- local-first entity status helpers;
- conflict/status badge derivation;
- utility logic для drag-and-drop и ordering;
- appearance/theme helpers.

#### Frontend integration
Проверяют feature или экран с mocked network/local storage boundary.

Обязательные зоны:
- Workspaces/Boards/Card flows;
- loading / empty / error / retry states;
- activity/history rendering;
- appearance settings save/apply flow;
- auth session bootstrap;
- local-first hydration and optimistic/pending/failed state transitions.

#### Frontend contract
Проверяют, что frontend понимает ровно те формы ответов, которые backend обещает.

Минимум:
- parsing/typing ключевых API payloads;
- error payload compatibility;
- enum compatibility;
- snapshot/sync payload compatibility для будущего sync клиента.

#### Frontend smoke / browser smoke
Проверяют минимальный живой пользовательский путь в браузере.

Минимум для MVP:
- открыть приложение;
- увидеть список рабочих пространств или пустое состояние;
- создать workspace;
- открыть board;
- создать card;
- открыть card details;
- убедиться, что критический экран не разваливается на boot/navigation/basic mutation.

Полный браузерный e2e набор пока **не должен** разрастаться раньше времени. Для MVP нужен именно короткий smoke-набор, а не сотни UI-сценариев.

## 5. Что обязательно тестировать

### 5.1. Обязательный backend минимум

Без этого этап нельзя считать надежным:

- auth happy-path: sign-up, sign-in, sign-out, sign-out-all, session restore;
- unauthorized/forbidden cases для закрытых endpoints;
- workspaces/boards/columns/cards core CRUD;
- card move/archive/unarchive;
- activity feed, card history, workspace audit log;
- user appearance + board appearance defaults/update/partial update;
- error envelopes и validation 4xx вместо 500;
- migrations применяются на чистой БД;
- derived endpoints не ослабляют access boundary по сравнению с базовыми сущностями.

### 5.2. Обязательный frontend минимум

- рендер app shell и router entry;
- workspace list/create flow;
- board screen with columns/cards;
- card details open/update happy-path;
- loading / empty / error / retry states;
- appearance screens;
- auth bootstrap/session-aware rendering;
- local-first sync badges/state mapping, когда local store будет введен;
- offline-empty vs cached-offline vs pending/failed UI states, когда local-first слой станет активным runtime layer.

## 6. Contract tests

Contract tests здесь нужны не как формальность, а как страховка от рассинхрона между backend, frontend и будущим sync engine.

### 6.1. Источник истины

Основной контрактный источник:
- `docs/api/openapi.yaml` для HTTP surface;
- `docs/sync/schemas/*.json` для sync envelope/snapshot/change event форматов.

### 6.2. Что проверяется контрактно

#### HTTP
- наличие обязательных endpoint groups;
- ключевые request/response shapes;
- error payload shape;
- enum values, используемые UI;
- backward-compatible optional fields.

#### Sync
- envelope schema validity;
- `eventId`, `replicaId`, `replicaSeq`, `lamport`, `serverOrder` semantics в payload shape;
- cursor/snapshot-required responses;
- conflict review item shape.

### 6.3. Практическое правило

Любое изменение в `openapi.yaml` или `docs/sync/schemas/` должно либо:
- не ломать существующие contract tests,
- либо сопровождаться осознанным обновлением fixtures/tests с объяснимым change intent.

## 7. Sync и conflict scenario tests

Для этого проекта они обязательны, потому что local-first/sync — часть архитектуры, а не “когда-нибудь потом разберемся”.

### 7.1. Какие sync сценарии обязательны

1. **Deterministic outbound ordering**
   - одна реплика генерирует несколько pending операций;
   - порядок отправки и повторного воспроизведения стабилен;
   - `replicaSeq` монотонен.

2. **Idempotent duplicate apply**
   - один и тот же event/envelope приходит повторно;
   - backend/client не создает дубликаты и не ломает состояние.

3. **Pull after push acknowledgment**
   - после ack клиент корректно двигает локальные cursors и pending state.

4. **Snapshot-required recovery**
   - stale cursor / history gap / replica reset переводит scope в controlled `needs_snapshot` сценарий, а не в тихую порчу данных.

5. **Offline mutate -> reconnect -> reconcile**
   - изменения, накопленные offline, после reconnect либо принимаются, либо честно получают failed/conflict surface.

6. **Membership revoke vs offline replay**
   - событие, созданное до revoke, не получает “grandfather privilege” после revoke;
   - это требование напрямую вытекает из security/privacy/threat model.

### 7.2. Какие conflict сценарии обязательны

1. rename vs rename;
2. move vs move;
3. edit vs archive;
4. edit vs delete/tombstone;
5. board/card appearance partial updates from different replicas;
6. manual-resolution-required case с user-visible conflict item.

### 7.3. Что важно для этих тестов

Эти тесты должны быть:
- **seeded**;
- **replayable**;
- независимыми от системного текущего времени;
- независимыми от случайного порядка БД выборок без `ORDER BY`.

## 8. Smoke strategy

Smoke-набор нужен как **короткая проверка живого vertical slice**, а не как еще один integration suite.

### 8.1. Что входит в backend smoke v1

Обязательный backend smoke:
- health;
- sign-up/sign-in;
- session;
- create workspace;
- create board;
- create column;
- create/update/move/archive/unarchive card;
- list cards/columns/workspaces;
- board activity;
- card activity;
- workspace audit log;
- me / devices;
- sign-out-all + anonymous access blocked.

### 8.2. Что входит в browser smoke v1

Обязательный browser smoke:
- app boot;
- initial route render;
- workspace create/open;
- board render;
- create card;
- open card drawer;
- no white screen / no uncaught error on critical interaction.

### 8.3. Чего не делать смоком

Не надо в smoke:
- исчерпывающе тестировать every validation branch;
- перебором проходить все permissions;
- проверять редкие edge-cases sync/conflict;
- заменять им integration tests.

## 9. Fixture strategy

### 9.1. Общие правила

- Предпочитать **маленькие composable fixtures**, а не огромные SQL/JSON дампы.
- Использовать **factories/builders** для сущностей и API payloads.
- Явно различать:
  - domain fixtures;
  - API fixtures;
  - sync event fixtures;
  - browser scenario fixtures.

### 9.2. Backend fixtures

Нужно хранить отдельно:
- SQL/bootstrap fixtures для тестовой БД;
- JSON payload fixtures для contract/smoke;
- seeded sync/conflict scenario inputs.

### 9.3. Frontend fixtures

Нужно хранить отдельно:
- mocked HTTP responses;
- local store snapshots;
- sync status states (`synced`, `pending`, `failed`, `needs_resync`, `offline_unavailable`);
- realistic but minimal board/card/workspace states.

### 9.4. Fixture anti-patterns

Нельзя полагаться на:
- shared dirty dev DB как будто она всегда чистая;
- случайный `Uuid::now_v7()` без возможности стабилизировать ожидания там, где нужен snapshot comparison;
- локальную timezone/locale машины без явного учета;
- network fixtures, зависящие от порядка полей или нестабильных timestamp без нормализации.

## 10. Determinism и replayability

Для local-first и sync-ready проекта это обязательное инженерное требование.

### 10.1. Что должно быть детерминировано

- clock/time provider в тех местах, где сравниваются времена;
- генерация test ids там, где нужен repeatable snapshot/assertion;
- порядок событий при replay;
- сортировка выборок, списков history и change events;
- state transitions pending -> synced/failed.

### 10.2. Что нужно для replayability

- хранить сценарии как явные inputs/expected outputs;
- иметь фиксированный порядок apply;
- сериализуемые scenario fixtures для sync/conflict;
- возможность прогнать один и тот же сценарий несколько раз и получить одинаковый результат.

### 10.3. Специальное правило для smoke

Smoke-тесты должны быть **идемпотентными**: либо работать на чистой БД, либо не предполагать состояние, которое мог оставить предыдущий прогон.

## 11. Директории и организация тестов

### 11.1. Backend

`Cargo` ожидает integration tests в `backend/tests/*.rs`, поэтому реальные Rust integration files остаются в корне `backend/tests/`.

Дополнительно заводятся поддерживающие каталоги:

```text
backend/tests/
  README.md
  appearance_smoke.rs
  core_crud_smoke.rs
  smoke_core_api.py
  smoke/
  contract/
  fixtures/
  scenarios/
  support/
```

Назначение:
- `smoke/` — описание smoke matrix и black-box сценариев;
- `contract/` — HTTP/OpenAPI и sync schema fixtures/checks;
- `fixtures/` — JSON/SQL/test data inputs;
- `scenarios/` — replayable sync/conflict inputs;
- `support/` — общие test helpers и notes.

### 11.2. Frontend

```text
frontend/
  src/
    test/
      README.md
      unit/
      integration/
      contracts/
      fixtures/
      factories/
  e2e/
    README.md
    smoke/
```

Назначение:
- `src/test/unit/` — unit tests;
- `src/test/integration/` — feature/screen integration tests;
- `src/test/contracts/` — typed payload/contract checks;
- `src/test/fixtures/` — mocked responses и local store snapshots;
- `src/test/factories/` — builders/factories;
- `e2e/smoke/` — минимальные browser smoke сценарии.

## 12. Минимальные quality gates

### 12.1. На каждый PR

Минимум должен проходить:
- backend compile/check;
- backend fast tests;
- backend contract checks для измененных API surface;
- frontend build;
- frontend unit/integration tests для затронутых feature;
- backend smoke при изменениях backend auth/core/API wiring.

### 12.2. На main / nightly

Дополнительно:
- browser smoke;
- расширенные sync/conflict scenario tests;
- cross-layer contract checks;
- migration-from-empty-db verification.

## 13. Что внедряем сразу, а что по фазам

### Этап 1 — сразу
- зафиксировать эту стратегию;
- упорядочить test directories;
- сохранить существующий backend smoke как обязательный vertical-slice тест;
- поддерживать Rust integration tests для ключевых backend surfaces;
- подготовить frontend test scaffolding.

### Этап 2 — ближайший
- завести frontend unit/integration harness;
- завести contract fixtures against OpenAPI;
- расширить smoke до browser-level minimal path.

### Этап 3 — когда sync слой станет runtime-реальностью
- replayable sync scenario suite;
- conflict matrix tests;
- revoke-vs-offline-replay regression suite;
- snapshot-required recovery tests.

## 14. Итог

В проекте принимается **пирамида с тяжелым основанием unit/integration, тонким обязательным contract слоем и очень коротким, но живым smoke слоем**.

Критично не просто “иметь тесты”, а обеспечить:
- обязательный backend/frontend split;
- contract discipline;
- replayable sync/conflict scenarios;
- deterministic local-first behavior;
- smoke, который подтверждает, что vertical slice действительно жив.
