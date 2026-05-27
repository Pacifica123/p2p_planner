# Манифест радикального вскрытия release/dev lifecycle v2

- Статус: Draft v2
- Дата: 2026-05-27
- Назначение: заменить режим бесконечных реактивных фиксов на одно управляемое инженерное расследование, которое строит полную карту отказов, воспроизводит их в контролируемой среде и только после этого запускает цепочку тематических исправлений.

---

## 1. Почему предыдущей формулировки недостаточно

Одного призыва “думать шире” мало. Он все равно оставляет проект в том же режиме:

```text
падение -> анализ лога -> патч шире обычного -> новое падение -> новый патч
```

Такой цикл может выглядеть взрослее, но он остается тем же реактивным циклом. Он просто становится дороже: вместо маленьких псевдофиксов появляются большие псевдофиксы.

Новая стратегия должна быть другой не по размеру патча, а по устройству процесса.

Главный сдвиг:

```text
Не “сделать более умный фикс”.
А “построить машину, которая сначала допрашивает весь release/dev контур”.
```

Пока у проекта нет такой машины, любые исправления остаются догадками, даже если они аккуратные и полезные локально.

---

## 2. Новая формула вехи

```text
Сначала генеральное вскрытие системы запуска.
Потом реестр всех выявленных и гипотетически вероятных отказов.
Потом пакетный план безопасных ремедиаций.
И только потом тематическая цепочка патчей.
```

Эта веха не должна начинаться с очередного исправления `npm`, `Vite`, `cmd.exe`, `PostgreSQL`, `CORS` или smoke. Она должна начинаться с инструмента/протокола, который заставляет проект выдать правду о себе.

Название вехи:

```text
Deep Release Autopsy and Total Remediation Plan
```

Слово `total` здесь не означает магическое обещание найти абсолютно все проблемы во вселенной. Это означает другое: мы явно задаем поддерживаемую область реальности и внутри нее требуем почти исчерпывающего обследования.

Поддерживаемая область на v1:

- clean checkout / clean archive;
- Windows cmd / PowerShell;
- Linux shell;
- Node/npm/Vite startup path;
- Rust/Cargo/backend build path;
- PostgreSQL discovery, auth, role/db creation and migration path;
- environment files and runtime config;
- ports, child processes, stale processes and cleanup;
- backend/frontend readiness;
- smoke/release-gates repeatability;
- artifact/report completeness.

То, что входит в эту область, не должно “всплывать случайно” после пятого патча. Оно должно быть заранее допрошено.

---

## 3. Стоп-правило: не лечить новый stacktrace первым действием

На период этой вехи запрещается начинать с очередного продуктового фикса, если перед ним не выполнено хотя бы одно из двух условий:

1. Сбой уже покрыт существующим failure-mode ID и понятно, какой remediation закрывает класс проблемы.
2. Сбой сначала добавлен в диагностическую карту, воспроизведен или формально признан невоспроизводимым, и только потом превращен в fix-задачу.

Иначе мы снова будем использовать Git как дневник попыток.

Патч без нового знания считается подозрительным.
Патч без воспроизводимого критерия считается экспериментом.
Патч без rollback/cleanup-логики считается потенциальным новым источником хаоса.

---

## 4. Центральная идея: Release Autopsy Harness

Нужен не “еще один devbootstrap fix”, а отдельный режим полного вскрытия, условно:

```text
python tools/devbootstrap.py autopsy --profile local-v1 --output .dev-bootstrap/autopsy/<run-id>
```

Или в будущем:

```text
python tools/devbootstrap.py deep-scan
python tools/devbootstrap.py remediation-plan
python tools/devbootstrap.py apply-remediation --step <id>
```

Смысл не в названиях команд, а в контракте.

Autopsy Harness обязан пройти по системе не как пользователь, который надеется, что все стартанет, а как следователь, который заранее подозревает каждый слой.

Он должен не только запускать, но и спрашивать:

- какие инструменты реально найдены;
- какие версии реально используются;
- через какой shell реально будет вызвана команда;
- какой exact argv будет передан;
- есть ли несколько `npm`, `node`, `psql`, `cargo` в PATH;
- существуют ли старые backend/frontend процессы;
- кто держит порты;
- можно ли создать БД;
- кто владелец БД;
- какие миграции лежат на диске;
- какие миграции уже применены;
- пересобрался ли backend после изменения migrations;
- совпадает ли API URL у frontend с живым backend;
- готов ли backend до старта smoke;
- является ли smoke идемпотентным;
- можно ли повторить запуск дважды подряд;
- можно ли корректно остановить и снова запустить.

Главный артефакт autopsy — не “успешно/неуспешно”. Главный артефакт — доказательная карта состояния.

---

## 5. Не один прогон, а матрица провокаций

Текущий цикл ломается потому, что мы узнаем о проблеме только тогда, когда случайно дошли до нее в happy path.

Autopsy Harness должен запускать не только happy path, но и провокационные сценарии.

Минимальная матрица:

### 5.1. Filesystem/workspace

- чистый workspace;
- workspace после предыдущего падения;
- workspace с существующей `.env`;
- workspace без `.env`;
- workspace с пробелами в пути;
- workspace с Windows-style path;
- workspace, где `node_modules` отсутствует;
- workspace, где `node_modules` есть, но marker устарел.

### 5.2. Process/port lifecycle

- порты свободны;
- backend port занят чужим процессом;
- frontend port занят чужим процессом;
- остался stale pid file;
- процесс жив, но readiness endpoint не отвечает;
- процесс умер сразу после старта;
- stop вызывается дважды подряд;
- start вызывается после аварийного kill.

### 5.3. Windows launcher matrix

- direct executable;
- `.cmd` wrapper;
- `cmd.exe /d /c call ...`;
- PowerShell invocation;
- path with spaces;
- npm script with forwarded args;
- Vite direct launch fallback.

Цель: больше не угадывать, как именно Windows сломает argv. Мы должны иметь таблицу launcher-mode -> exact command -> expected behavior -> remediation.

### 5.4. PostgreSQL authority matrix

- `TEST_DATABASE_URL` уже задан;
- `DATABASE_URL` задан;
- PostgreSQL доступен локально без прав на `createdb`;
- PostgreSQL доступен с правами `createdb`;
- есть `psql`, но сервер не запущен;
- сервер запущен, но auth method не подходит;
- роль существует, БД отсутствует;
- БД существует, владелец неправильный;
- миграции частично применены;
- миграции на диске отличаются от примененных;
- пользователь хочет сохранить БД после прогона;
- пользователь хочет одноразовую throwaway DB.

### 5.5. Runtime config matrix

- frontend API base URL совпадает с backend;
- frontend указывает на старый backend;
- backend CORS не пускает frontend origin;
- env variable задана в shell, но перекрыта `.env`;
- `.env` содержит локальный секрет;
- report должен редактировать секреты, но сохранять диагностическую ценность.

### 5.6. Repeatability matrix

- cold start;
- warm start;
- start -> stop -> start;
- failed start -> stop -> start;
- release-gates два раза подряд;
- smoke на непустой dev-БД;
- smoke на fresh throwaway-БД.

Пока эти сценарии не описаны, мы не знаем, что именно поддерживаем.

---

## 6. Смелость, но не безумие: controlled mutators

Стратегия должна разрешать смелые решения, но только как контролируемые мутации окружения.

Controlled mutator — это действие, которое меняет локальное окружение, но имеет:

- явный preflight;
- dry-run plan;
- подтверждение или explicit flag;
- лог всех команд;
- rollback или cleanup-инструкцию;
- отказ от выполнения в опасном окружении;
- запись в итоговый report.

Примеры controlled mutators:

- создать throwaway PostgreSQL database для release-gates;
- создать dedicated PostgreSQL role для devbootstrap;
- выдать этой роли ownership на тестовые базы;
- сгенерировать `.env.local` из безопасного шаблона;
- освободить stale pid/port, если процесс точно принадлежит текущему workspace;
- пересобрать backend после изменения migrations;
- выполнить `cargo clean` только по доказанному migration-embed рассинхрону;
- удалить одноразовую БД после успешного прогона, если retention policy так настроена.

---

## 7. PostgreSQL: authority ladder вместо паники

Этот раздел задает `PostgreSQL authority ladder` как обязательную модель принятия решений для БД.

PostgreSQL — один из главных источников “невидимых” проблем. Поэтому стратегия должна быть не “надеемся, что БД есть”, а `authority ladder`.

Лестница полномочий:

### Level 0: Use existing explicit DB

Если задан `TEST_DATABASE_URL`, используем его, но проверяем:

- доступность;
- права на schema/migrations;
- что это не production-looking URL;
- что report не утечет секретами.

### Level 1: Managed per-run DB with existing admin credentials

Если заданы admin credentials, devbootstrap создает отдельную БД под прогон:

```text
p2pkanban_test_<date>_<shortid>
```

После прогона применяет retention policy:

- delete on success;
- keep on failure;
- keep always;
- delete older than N days.

### Level 2: Dedicated local dev role

Если можно создать роль, devbootstrap предлагает dedicated role:

```text
p2pkanban_devbootstrap
```

Эта роль должна быть владельцем только своих dev/test БД, а не глобальным хозяином всего PostgreSQL.

### Level 3: Local-only bootstrap admin path

Если без повышенных прав никак, допускается смелый local-only сценарий: создать временную или постоянную devbootstrap-admin роль.

Но это разрешено только при жестких условиях:

- host должен быть local/loopback;
- команда должна быть явно подтверждена;
- SQL должен быть показан до выполнения;
- report должен отметить, что была выполнена privileged operation;
- cloud/remote-looking targets должны блокироваться;
- должен быть сгенерирован rollback SQL;
- по умолчанию это выключено.

Важно: зарегистрированный пользователь Kanban не должен становиться PostgreSQL superuser. Можно связать локальный dev-profile или owner label с созданной тестовой инфраструктурой, но нельзя смешивать application identity и database administration. Иначе мы исправим запуск ценой архитектурной дыры.

### Level 4: Manual remediation pack

Если автоматическое создание прав невозможно, инструмент не должен падать туманно. Он должен выдать готовый manual pack:

- какие команды выполнить;
- зачем они нужны;
- как проверить результат;
- как откатить;
- как снова запустить autopsy.

---

## 8. Главный выход: не патч, а Problem Ledger

После autopsy должен появляться не просто лог, а `Problem Ledger`.

Формат каждой записи:

```text
ID: REL-DB-003
Class: PostgreSQL authority / database owner mismatch
Observed: yes/no/suspected
Evidence: paths to logs, commands, env snapshot references
Impact: blocks release-gates / degrades repeatability / warning
Owner layer: devbootstrap / backend / frontend / smoke / docs / environment
Root cause hypothesis: ...
Remediation options:
  A. safe minimal
  B. bold controlled
  C. manual fallback
Recommended: B
Acceptance check: ...
Rollback/cleanup: ...
Patch phase: 2
```

Это ключевой поворот.

Мы больше не говорим:

```text
“Сейчас упал frontend, сделай фикс”.
```

Мы говорим:

```text
“В Problem Ledger есть REL-FE-004, REL-WIN-002 и REL-PROC-001; они вместе дают frontend startup failure. Применяем remediation phase 3”.
```

---

## 9. Как выявлять еще не встреченные проблемы

Нельзя гарантировать абсолютное знание всех будущих поломок. Но можно перестать ждать, пока они сами вылезут.

Методы:

### 9.1. Negative capability tests

Для каждого критичного слоя создается не только happy-path check, но и check на типовой отказ:

- порт занят;
- БД недоступна;
- неправильный URL;
- stale process;
- отсутствует command;
- command есть, но не тот;
- migration mismatch;
- smoke state dirty.

### 9.2. Fault injection without destruction

Инструмент должен уметь моделировать часть отказов без порчи реального окружения:

- dry-run launcher resolution;
- fake env overlay;
- temporary port binder;
- temporary throwaway DB;
- temporary workspace copy;
- temp `.env` variant.

### 9.3. Cross-layer consistency checks

Большинство проблем сидит на стыках:

- backend слушает одно, frontend зовет другое;
- smoke ждет одно, API вернул другое;
- migrations на диске одни, binary embedded migrations другие;
- devbootstrap думает, что запустил npm, а реально вызвал wrapper через не тот shell;
- stop считает процесс своим, но pid уже переиспользован.

Autopsy должен искать именно стыки, а не только отдельные команды.

### 9.4. Regression memory

Каждая найденная проблема становится постоянным probe. Если однажды был баг с Windows npm wrapper, будущая проверка обязана явно подтвердить, какой launcher выбран и почему.

---

## 10. Пакетный план ремедиаций

После autopsy не надо делать один гигантский патч. Но и возвращаться к хаотичному циклу нельзя.

Правильный результат — цепочка тематических патчей, заранее выведенная из Problem Ledger.

Ожидаемая цепочка:

1. **Autopsy Harness foundation** — режим deep-scan, snapshot, artifact contract, Problem Ledger.
2. **PostgreSQL authority manager** — managed test DB, role/db creation ladder, retention policy, safe manual pack.
3. **Process and port supervisor** — ownership-aware start/stop, stale detection, readiness protocol.
4. **Windows launcher normalization** — exact argv planner, cmd/npm/vite matrix, direct executable fallback.
5. **Runtime config resolver** — env precedence, redaction, API/CORS consistency checks.
6. **Migration integrity guard** — disk/applied/embedded migration checks, sqlx rebuild triggers, targeted cargo clean guidance.
7. **Smoke idempotency hardening** — fresh data strategy, dirty-state tolerance, cleanup verification.
8. **Release-gates repeatability loop** — cold/warm/failed/retry scenarios and final report bundle.
9. **Documentation and operations guide** — how to run, inspect, preserve DB, clean old artifacts and recover manually.

Каждый патч должен знать свое место в цепочке до того, как он написан.

---

## 11. Acceptance criteria новой вехи

Веха считается успешной не когда “на моей машине один раз завелось”, а когда выполняется набор критериев.

Минимум:

- есть autopsy command или эквивалентный deep diagnostic mode;
- он собирает единый bundle с machine-readable и human-readable отчетами;
- report показывает toolchain, env, process, port, DB, migration, backend, frontend, smoke state;
- PostgreSQL имеет понятную authority ladder и не падает без объяснения;
- frontend launch path объяснен exact argv и shell mode;
- stop/start lifecycle проверяется повторно;
- smoke можно запускать на fresh и dirty state без ложных regression;
- release-gates прогоняются дважды подряд или честно объясняют, почему нельзя;
- каждый known failure mode имеет ID, remediation и acceptance check;
- новые фиксы принимаются только если добавляют probe/guard/test для своего класса проблем.

Сильный критерий:

```text
После полного autopsy мы можем не обещать отсутствие всех багов,
но можем объяснить почти каждый вероятный отказ до того, как он случится у пользователя.
```

---

## 12. Почему это кардинально меняет ситуацию

Старый цикл:

```text
ошибка ведет к патчу
```

Новый цикл:

```text
ошибка ведет к failure-mode ID
failure-mode ID ведет к Problem Ledger
Problem Ledger ведет к planned remediation chain
remediation chain ведет к probes
probes не дают классу проблемы вернуться молча
```

То есть цель не в том, чтобы “лучше чинить”. Цель в том, чтобы каждый сбой уменьшал темноту системы, а не просто менял текст следующей ошибки.

---

## 13. Практический девиз v2

```text
Не патчить туман.
Сначала построить радар.
Потом идти по карте.
```

И еще жестче:

```text
Пока release/dev контур не умеет сам себя объяснять,
мы не знаем, что именно чиним.
```
