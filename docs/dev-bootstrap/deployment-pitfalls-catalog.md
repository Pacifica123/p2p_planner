# Deployment pitfalls catalog for future dev auto-bootstrapper

- Статус: Draft v1
- Дата: 2026-05-13
- Назначение: собрать базу рисков, проверок и подводных камней для будущего кастомного авторазвертывателя локальной dev-среды P2P Planner.

---

## 1. Граница документа

Этот документ не является планом реализации инструмента. Он отвечает на другой вопрос:

```text
что может пойти не так при разворачивании проекта
и что будущий auto-bootstrapper должен уметь диагностировать
```

Целевая стартовая ситуация самая низкоуровневая:

```text
есть чистая или полугрязная Windows/Linux машина
есть скачанный архив проекта
PostgreSQL может отсутствовать полностью
часть инструментов может отсутствовать
часть инструментов может быть установлена, но настроена не под этот проект
```

---

## 2. Уровень 0: сама ОС и среда выполнения

## 2.1. Определение платформы

Риски:

- Windows, Linux и WSL ведут себя по-разному;
- shell-команды отличаются;
- путь проекта может содержать пробелы, кириллицу или спецсимволы;
- на Windows могут быть отключены long paths;
- права пользователя могут запрещать bind портов, создание сервисов, Docker/Podman доступ;
- антивирус или корпоративная политика могут блокировать запуск бинарников или Node postinstall scripts.

Проверки:

- OS family: Windows/Linux/WSL;
- architecture: x64/arm64;
- текущий shell;
- абсолютный путь проекта;
- есть ли пробелы/не-ASCII символы в пути;
- длина путей для Windows;
- права на запись в проект, `.dev-bootstrap/`, `backend/`, `frontend/`;
- доступность loopback `127.0.0.1`.

Рекомендация инструменту:

- не строить shell-команды строковой конкатенацией;
- использовать subprocess args-list там, где возможно;
- все пути отображать явно;
- сразу предупреждать о потенциально проблемных путях, но не запрещать их без причины.

## 2.2. Часовой пояс и системное время

Риски:

- сильно неверное системное время ломает cookie/session/debugging;
- timestamp reports становятся непонятными;
- TLS/cert проверки могут падать при будущем HTTPS/self-host.

Проверки:

- вывести local time и UTC;
- предупредить, если время выглядит аномально;
- фиксировать timestamp всех run reports в UTC.

---

## 3. Уровень 1: структура проекта после распаковки архива

Риски:

- пользователь распаковал архив с лишней верхней папкой;
- проект лежит не в expected root;
- запуск идет из `backend/` или `frontend/`, а инструмент ожидает root;
- в архиве отсутствуют части проекта;
- в проект случайно попали `node_modules/`, `target/`, `dist/`, `release/*.zip`, `release/*.exe`;
- применен не тот патч или не применен предыдущий патч;
- есть незакоммиченные локальные изменения.

Проверки:

- найти project root по `backend/`, `frontend/`, `docs/`, `docker-compose.dev.yml`;
- проверить наличие `backend/Cargo.toml`;
- проверить наличие `frontend/package.json`;
- проверить наличие `backend/migrations/`;
- проверить наличие `backend/.env.example` и `frontend/.env.example`;
- проверить наличие devctl workspace, если инструмент вызывается из devctl flow;
- показать git status, если `.git` есть;
- показать предупреждение о тяжелых/generated каталогах.

Рекомендация инструменту:

- поддерживать команду `diagnose` без побочных эффектов;
- в отчете явно писать найденный project root;
- не требовать идеальной структуры, если можно дать понятную диагностику.

---

## 4. Уровень 2: системные инструменты

## 4.1. Git

Риски:

- Git не установлен;
- репозиторий не инициализирован, потому что проект пришел архивом;
- branch не `main`;
- working tree dirty;
- line endings меняются между Windows/Linux;
- пользователь запускает проверки после применения patch.zip, но до коммита.

Проверки:

- `git --version`;
- есть ли `.git`;
- текущая ветка;
- `git status --porcelain`;
- remote origin;
- предупреждение о CRLF/LF при необходимости.

Решение:

- Git не должен быть обязательным для простого local run из архива;
- Git должен быть обязательным для devctl/patch conveyor режима.

## 4.2. Python

Риски:

- Python отсутствует;
- команда называется `python`, `python3` или `py`;
- версия слишком старая;
- PATH указывает не туда;
- Windows Store alias мешает запуску;
- smoke запускается не тем интерпретатором.

Проверки:

- найти Python candidates;
- проверить версию;
- проверить запуск `python -c`;
- зафиксировать выбранную команду в report.

## 4.3. Rust/Cargo

Риски:

- Rust отсутствует;
- установлен старый toolchain;
- cargo есть, но rustc нет или наоборот;
- не установлен нужный target;
- первый `cargo check` долго качает crates;
- corporate proxy ломает crates.io;
- stale build cache ведет себя странно;
- после изменения migrations нужен rebuild из-за `sqlx::migrate!()` и `build.rs`.

Проверки:

- `cargo --version`;
- `rustc --version`;
- `cargo metadata` в `backend/`;
- доступ к cargo registry при первом запуске;
- наличие `backend/build.rs` и `backend/migrations/`;
- быстрый `cargo check` как preflight, если toolchain есть.

Рекомендации:

- отличать отсутствие toolchain от compile error проекта;
- при compile error сохранять полный лог;
- не делать `cargo clean` автоматически, только по явной команде.

## 4.4. Node/npm

Риски:

- Node отсутствует;
- версия Node несовместима с Vite/Playwright;
- npm отсутствует или сломан;
- lockfile не совпадает с package.json;
- `node_modules` от другой ОС;
- npm cache поврежден;
- proxy/cert ломает `npm install`;
- postinstall scripts запрещены политикой;
- PowerShell execution policy мешает запуску npm shim.

Проверки:

- `node --version`;
- `npm --version`;
- наличие `frontend/package-lock.json`;
- наличие/состояние `frontend/node_modules`;
- `npm ci` vs `npm install` режим;
- проверить scripts: `dev`, `build`, `test:run`, `test:browser`.

Рекомендации:

- для чистого install предпочитать `npm ci`, если lockfile актуален;
- если `node_modules` уже есть, проверять marker/mtime/package-lock hash;
- не удалять `node_modules` без подтверждения.

## 4.5. Docker/Podman

Риски:

- Docker отсутствует;
- Docker Desktop установлен, но не запущен;
- пользователь не имеет прав на Docker daemon;
- на Linux нужен docker group/re-login;
- Podman установлен вместо Docker;
- Compose plugin отсутствует;
- порт 5432 уже занят локальным PostgreSQL;
- старый compose project держит volume с другой БД.

Проверки:

- `docker --version` или `podman --version`;
- `docker compose version`;
- daemon доступен;
- compose file существует;
- список контейнеров проекта;
- health status PostgreSQL-контейнера;
- volume name и возраст.

Рекомендации:

- Docker — удобный способ поднять PostgreSQL, но не единственный;
- если локальный PostgreSQL уже есть и подходит, не надо насильно поднимать контейнер;
- destructive volume reset только через explicit confirm.

---

## 5. Уровень 3: env-файлы и конфиг

## 5.1. Backend `.env`

Риски:

- `backend/.env` отсутствует;
- `.env` скопирован из старой версии;
- отсутствуют новые ключи;
- `DATABASE__URL` указывает не туда;
- `AUTH__JWT_SECRET` остался default в non-dev профиле;
- `AUTH__ENABLE_DEV_HEADER_AUTH` включен не там;
- `HTTP__CORS_ALLOWED_ORIGINS` не содержит frontend origin;
- `APP__PORT` конфликтует с занятым портом;
- переменная задана одновременно в shell и `.env`, а пользователь не понимает precedence.

Проверки:

- сравнить `.env` с `.env.example` по ключам;
- показать missing/extra keys;
- вывести effective critical config без секретных значений;
- замаскировать secrets в report;
- проверить `DATABASE__URL` синтаксически;
- проверить соответствие backend port и frontend API URL;
- проверить CORS origins.

Рекомендации:

- если `.env` отсутствует, создать из example только после plan/confirm;
- при изменении `.env` делать backup;
- никогда не выводить пароли/секреты полностью.

## 5.2. Frontend `.env.local`

Риски:

- `frontend/.env.local` отсутствует;
- `VITE_API_BASE_URL` указывает на старый порт/host;
- frontend собран с одним URL, а dev server запущен с другим;
- пользователь ожидает runtime env, но Vite `VITE_*` — публичный build-time config;
- API URL использует `localhost`, backend bind — `127.0.0.1`, а cookie/CORS настроены иначе.

Проверки:

- наличие `.env.local`;
- сравнение с `.env.example`;
- проверка `VITE_API_BASE_URL`;
- запрос backend health по этому URL;
- сравнение frontend origin с backend CORS allowlist.

Рекомендации:

- в dev по умолчанию использовать `http://127.0.0.1:18080/api/v1`;
- явно объяснять, что `VITE_*` не место для secrets.

---

## 6. Уровень 4: PostgreSQL

## 6.1. PostgreSQL отсутствует

Риски:

- чистая ОС без PostgreSQL;
- `psql` отсутствует;
- Docker тоже отсутствует;
- пользователь не знает, какой вариант выбрать.

Проверки:

- есть ли `psql`;
- есть ли Docker/Compose;
- можно ли открыть TCP на `127.0.0.1:5432`;
- существует ли compose service `postgres`.

Решение:

- предложить варианты: Docker Compose PostgreSQL или существующий внешний PostgreSQL;
- не считать отсутствие локального PostgreSQL фатальным, если можно поднять compose.

## 6.2. PostgreSQL установлен, но не запущен

Риски:

- сервис установлен, но остановлен;
- Docker container exists, но stopped;
- порт закрыт;
- Windows service называется иначе;
- Linux service управляется systemd, но без прав.

Проверки:

- TCP connect к host/port из `DATABASE__URL`;
- список известных docker containers;
- optional service hints без жесткой зависимости от systemd/sc.exe.

Решение:

- если это compose-контейнер проекта — можно предложить `docker compose up -d postgres`;
- если это системный PostgreSQL — дать команду-подсказку, но не стартовать без режима/подтверждения.

## 6.3. PostgreSQL запущен, но доступ не проходит

Риски:

- неверный пользователь/пароль;
- `pg_hba.conf` запрещает подключение;
- база слушает только socket, не TCP;
- SSL mode mismatch;
- пароль содержит спецсимволы и неверно URL-encoded;
- `localhost` резолвится в IPv6, а сервис слушает IPv4.

Проверки:

- parse connection string;
- TCP connect;
- попытка SQL `select 1`;
- маскированный вывод host/port/db/user;
- отдельная диагностика auth failure vs db missing vs network failure.

## 6.4. Подключение проходит, но база не та

Риски:

- `DATABASE__URL` указывает на старую БД;
- база подготовлена для проекта, но называется иначе;
- пользователь думал, что работает с `p2p_planner`, а подключен к `postgres`;
- smoke пишет данные в неправильную dev-БД;
- integration tests используют `DATABASE_URL`, хотя ожидался `TEST_DATABASE_URL`.

Проверки:

- вывести имя базы из connection string;
- выполнить `select current_database(), current_user`;
- проверить наличие проектных таблиц;
- проверить таблицу миграций;
- проверить наличие expected schemas/extensions;
- если таблицы есть, показать примерный статус: empty/dev-data/unknown.

Рекомендации:

- требовать явный `TEST_DATABASE_URL` для destructive/idempotent smoke;
- никогда не делать reset базы, имя которой не выглядит тестовым, без подтверждения.

## 6.5. База существует, но миграции не сходятся

Риски:

- часть миграций применена;
- бинарник собран со старым списком миграций;
- `sqlx::migrate!()` не увидел новые файлы без rebuild;
- миграция была переименована после применения;
- локальная dev-БД пережила несколько эпох проекта;
- schema drift из ручных правок.

Проверки:

- список файлов `backend/migrations/*.sql`;
- состояние migration table;
- запуск backend до health;
- распознавание ошибки “migration previously applied but missing”;
- подсказка про rebuild/build.rs, если симптомы похожи.

Рекомендации:

- auto-bootstrapper не должен чинить schema drift вслепую;
- для dev можно предложить создать новую dev/test БД;
- для существующей БД нужен отчет и ручное решение.

## 6.6. Extensions и permissions

Риски:

- пользователь БД не имеет права создавать extensions;
- extensions уже есть в другом schema;
- UUID/time helpers зависят от миграций;
- managed PostgreSQL ограничивает права.

Проверки:

- выполнить lightweight query по required extensions, если применимо;
- при failure показать SQL error без потери деталей;
- отличать permission denied от syntax/migration bug.

---

## 7. Уровень 5: backend

## 7.1. `cargo check`

Риски:

- dependencies не скачаны;
- compile error в коде;
- feature mismatch;
- платформенный compile issue;
- lockfile изменился;
- warning noise маскирует настоящую ошибку.

Проверки:

- запуск из `backend/`;
- сохранение полного лога;
- classification: missing cargo / dependency download / compile error / timeout.

## 7.2. `cargo run`

Риски:

- backend собирается, но падает на runtime config;
- backend падает на миграциях;
- порт занят;
- bind host недоступен;
- старый backend уже слушает тот же порт;
- процесс стартовал, но health не отвечает;
- backend поднялся на другом порту из env.

Проверки:

- проверить порт до запуска;
- записать PID процесса;
- читать stdout/stderr;
- ждать health с timeout;
- проверить `/health` и `/api/v1/health`, если оба используются;
- если порт занят, определить хотя бы PID/process name там, где возможно.

Рекомендации:

- не убивать процесс на порту автоматически, если он не был поднят этим инструментом;
- если это старый backend проекта, предложить safe stop;
- сохранять backend log даже при успешном запуске.

## 7.3. Auth/CORS/dev-header traps

Риски:

- frontend использует auth flow, но backend env в dev-header режиме;
- `AUTH__ENABLE_DEV_HEADER_AUTH=false`, а старый frontend ожидает `X-User-Id`;
- `X-User-Id` не разрешен в CORS allow headers;
- CORS origins не содержат frontend dev server;
- cookie secure/same-site не подходит для HTTP dev;
- sign-out оставляет frontend state.

Проверки:

- effective auth mode;
- CORS origin vs frontend URL;
- CORS allowed headers для dev header, если он включен;
- cookie policy для local HTTP;
- smoke no-token/wrong-token в будущих hardening режимах.

---

## 8. Уровень 6: frontend

## 8.1. Dependencies

Риски:

- `node_modules` отсутствует;
- `node_modules` от другой ОС;
- package-lock устарел;
- install не завершился;
- Playwright browsers не установлены;
- npm scripts изменились.

Проверки:

- проверить package manager baseline;
- проверить наличие `node_modules/.package-lock.json` или аналогов;
- сравнить mtime/hash lockfile с install marker;
- проверить `npx playwright --version`, если нужен browser smoke;
- при необходимости предложить `npx playwright install`.

## 8.2. Vite dev server

Риски:

- порт 5173 занят;
- Vite выбрал другой порт;
- browser открывает старый URL;
- frontend API URL не совпадает с backend;
- CORS blocked выглядит как “backend недоступен”;
- HMR websocket блокируется firewall/proxy.

Проверки:

- порт до запуска;
- stdout Vite для фактического URL;
- health request к backend из конфиг URL;
- optional browser-open только после успешного старта.

## 8.3. Browser/local state

Риски:

- localStorage/sessionStorage содержит старые данные;
- cookies от предыдущего backend/session;
- service worker/cache, если появится позже;
- user appearance/customization в dev-БД сохраняется между smoke прогонами;
- browser smoke падает на “грязном” состоянии, а не на regression.

Проверки:

- browser smoke должен быть либо изолированным, либо явно чистить контекст;
- live manual session should not be treated as clean test state;
- report должен предупреждать, если используется shared dev-БД.

---

## 9. Уровень 7: тесты и smoke

## 9.1. Backend smoke

Риски:

- backend не поднят;
- smoke ходит в другой `BASE_URL`;
- smoke использует фиксированного пользователя и грязную БД;
- cleanup неполный;
- повторный прогон меняет результат;
- smoke пишет в dev-БД вместо test-БД.

Проверки:

- backend health перед smoke;
- вывести `BASE_URL`;
- вывести test/dev DB classification;
- предупреждать при отсутствии `TEST_DATABASE_URL`;
- smoke должен быть idempotent или создавать уникальные test identities.

## 9.2. Rust integration tests

Риски:

- тесты требуют `DATABASE_URL`/`TEST_DATABASE_URL`;
- parallel tests конфликтуют по данным;
- миграции на тестовой БД не применены;
- тесты используют shared dev user;
- flaky timeout на медленной машине.

Проверки:

- env для tests;
- database reachability;
- test DB name guard;
- serial/parallel mode hints.

## 9.3. Frontend unit/browser tests

Риски:

- unit tests завязаны на env;
- browser smoke требует Playwright browsers;
- browser smoke mocked, а пользователь ожидает live backend;
- live e2e требует поднятых backend/frontend;
- pageerror от старого frontend bundle.

Проверки:

- scripts exist;
- dependencies installed;
- Playwright browsers installed;
- explicit mode: mocked browser smoke vs live browser smoke.

---

## 10. Уровень 8: порты, процессы и cleanup

## 10.1. Порты

Базовые ожидания:

- backend: `127.0.0.1:18080`;
- frontend: `127.0.0.1:5173`;
- PostgreSQL: `127.0.0.1:5432`.

Риски:

- порт занят старым backend/frontend;
- порт занят другим приложением;
- Docker пробросил порт, но контейнер unhealthy;
- Vite auto-incremented port;
- firewall блокирует loopback;
- IPv4/IPv6 mismatch.

Проверки:

- TCP port check до запуска;
- process owner/name там, где возможно;
- post-start check фактического bind;
- report occupied ports.

## 10.2. Процессы

Риски:

- пользователь закрыл терминал, процесс остался;
- backend старой сборки продолжает слушать порт;
- frontend dev server живет отдельно;
- child process не завершился;
- Windows process tree завершается иначе, чем Linux.

Проверки:

- PID state для процессов, поднятых инструментом;
- process still alive check;
- graceful stop;
- forced stop только для owned processes и только после timeout.

Рекомендации:

- хранить state в `.dev-bootstrap/state.json`;
- команда `stop` должна быть безопасной;
- команда `doctor` должна уметь показать orphan candidates, но не удалять их молча.

## 10.3. Docker cleanup

Риски:

- остановить чужой контейнер;
- удалить volume с данными;
- оставить dangling containers;
- compose project name отличается из-за пути проекта.

Проверки:

- compose project name;
- container labels;
- volume labels;
- health status.

Рекомендации:

- `stop` может останавливать compose service, если он был поднят инструментом;
- `down -v` только через explicit destructive command.

---

## 11. Уровень 9: networking and proxy

Риски:

- корпоративный proxy ломает cargo/npm;
- TLS interception ломает cert validation;
- offline machine без доступа к registries;
- DNS не резолвит registry;
- firewall блокирует localhost или dev server websocket;
- VPN меняет network routing.

Проверки:

- network reachability для cargo/npm только если нужно скачивать dependencies;
- показать proxy env vars без секретов;
- отличать локальный runtime failure от dependency download failure.

Рекомендации:

- не требовать интернет, если dependencies уже установлены;
- поддержать offline-ish режим: только diagnose и локальные checks.

---

## 12. Уровень 10: devctl и patch workflow

Риски:

- auto-bootstrapper генерирует файлы, которые попадают в devctl patch;
- run logs случайно коммитятся;
- `.env`, database dumps, `node_modules`, `target`, `dist`, `release/*.zip`, `release/*.exe` попадают в архивы;
- checks меняют working tree;
- devctl применяет патч на грязное дерево;
- patch содержит абсолютные пути.

Проверки:

- bootstrap runtime state должен жить в исключаемой папке, например `.dev-bootstrap/`;
- generated logs не должны попадать в patch files;
- docs/code changes должны быть отделены от runtime artifacts;
- перед devctl patch/start показать git status;
- после checks показать new changes introduced by checks.

Рекомендации:

- auto-bootstrapper должен иметь режим `--no-write`/`diagnose`;
- devctl checks могут вызывать только safe diagnostics;
- любые generated artifacts должны быть явно внесены в exclude list.

---

## 13. Уровень 11: безопасность локального запуска

Риски:

- dev secret уехал в non-dev;
- `.env` попал в patch/archive;
- токены/пароли попали в logs;
- smoke печатает cookies/tokens;
- dev-header auth включен в preview;
- CORS wildcard случайно стал baseline;
- destructive DB reset выполнен не на test DB.

Проверки:

- mask secrets in logs;
- forbid printing full connection string password;
- classify env: local/dev/preview/production;
- warn on default JWT secret outside local;
- warn on wildcard CORS outside local;
- require confirm for DB reset unless database name is test-prefixed and user explicitly allowed it.

---

## 14. Диагностические статусы, которые стоит заложить

Вместо одного `failed` инструменту нужны статусы:

```text
ok
warning
missing_tool
bad_version
missing_env
bad_env
port_busy
process_conflict
db_unavailable
db_auth_failed
db_missing
db_wrong_target
db_schema_drift
backend_compile_failed
backend_runtime_failed
backend_health_timeout
frontend_install_failed
frontend_runtime_failed
smoke_failed
cleanup_partial
```

Это поможет строить понятные отчеты и будущую UI/CLI навигацию.

---

## 15. Минимальный будущий checklist auto-bootstrapper

На первом полезном этапе инструмент должен уметь хотя бы:

- найти project root;
- определить OS/shell;
- проверить Python/Git/Rust/Node/npm/Docker availability;
- проверить backend/frontend env-файлы;
- показать effective critical config без секретов;
- проверить PostgreSQL по `DATABASE__URL`;
- отличить “PostgreSQL не жив” от “база не та”;
- проверить занятость портов `18080`, `5173`, `5432`;
- выполнить `cargo check`;
- выполнить `npm install` или подсказать необходимость;
- поднять backend и дождаться health;
- поднять frontend и показать фактический URL;
- запустить backend smoke;
- запустить frontend browser smoke в выбранном режиме;
- сохранить run report;
- остановить процессы, которые инструмент сам поднял.

---

## 16. Итоговая карта рисков

Самые опасные классы проблем:

1. **Wrong target** — всё работает, но инструмент стучится не в ту БД/backend/frontend.
2. **Dirty state** — тесты падают или проходят из-за старых данных.
3. **Stale process** — жив старый backend/frontend, и пользователь проверяет не тот код.
4. **Silent config drift** — `.env` устарел, но выглядит правдоподобно.
5. **Cross-platform shell traps** — команда работает на Linux, но ломается на Windows.
6. **Destructive cleanup** — автоматизация случайно удаляет данные или гасит чужой процесс.
7. **Secret leakage** — полезные diagnostics превращаются в слив паролей/tokens.
8. **Generated artifact pollution** — runtime мусор попадает в patch/archive.

Главное требование к будущему auto-bootstrapper:

```text
не просто запускать команды,
а доказывать, что каждая команда применяется к правильной среде,
и оставлять после себя понятный отчет о том, что произошло.
```
