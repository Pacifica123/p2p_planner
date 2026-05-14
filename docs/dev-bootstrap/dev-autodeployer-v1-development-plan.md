# Dev auto-bootstrapper v1 development plan

- Статус: Draft v1
- Дата: 2026-05-13
- Назначение: описать поэтапный план разработки кастомного авторазвертывателя, который сможет подготовить и поднять локальную dev-среду P2P Planner, проверить backend/frontend и дать понятный отчет при сбое.

---

## 1. Контекст и опора на уже принятые документы

Этот план опирается на два документа из `docs/dev-bootstrap/`:

- `dev-autodeployer-manifesto.md` — зачем инструмент нужен и какие принципы важнее всего;
- `deployment-pitfalls-catalog.md` — что может пойти не так на чистой, полугрязной или давно не использованной машине.

Также план учитывает текущие особенности проекта:

- backend: Rust + Axum + sqlx + PostgreSQL;
- backend запускается из `backend/` через `cargo run`;
- backend применяет миграции на старте;
- `sqlx::migrate!()` требует корректного rebuild при изменении `backend/migrations/`, для чего уже есть `backend/build.rs`;
- backend health endpoints: `GET /health` и `GET /api/v1/health`;
- backend env baseline: `backend/.env.example`;
- PostgreSQL dev baseline: `docker-compose.dev.yml`, service `postgres`, база `p2p_planner`, порт `5432`;
- frontend: React + Vite + npm;
- frontend запускается из `frontend/` через `npm run dev`;
- frontend env baseline: `frontend/.env.example` / `frontend/.env.local`;
- frontend default API URL: `http://127.0.0.1:18080/api/v1`;
- текущий нормальный browser/API flow идет через `Authorization: Bearer ...`, а `X-User-Id` — legacy/dev-test fallback, выключенный по умолчанию;
- backend smoke: `backend/tests/smoke_core_api.py`;
- frontend tests: `npm run test:run`, browser smoke: `npm run test:browser`;
- devctl patch conveyor уже существует как отдельный инструмент в `tools/devctl.py` и не должен смешиваться с runtime-bootstrap логикой.

---

## 2. Цель v1

Цель v1 auto-bootstrapper:

```text
из архива проекта на Windows/Linux машине
→ найти корень проекта
→ проверить prerequisites
→ подготовить безопасные env-файлы
→ найти или поднять PostgreSQL
→ проверить базу и миграционный контекст
→ проверить backend cargo check
→ запустить backend
→ дождаться health
→ установить frontend dependencies
→ запустить frontend
→ проверить базовую доступность UI/API
→ запустить минимальные smoke/test checks по запросу
→ сохранить понятный run report
→ корректно остановить процессы, которые сам поднял
```

Минимальный v1 не обязан быть production deployment system. Он нужен для локальной разработки, проверки патчей, восстановления после перерыва и переноса проекта между машинами.

Главный критерий v1:

```text
если приложение не поднялось, пользователь получает не “что-то упало”,
а классифицированную причину, важные логи и следующий безопасный шаг.
```

---

## 3. Не-цели v1

В v1 не делаем:

- установку Rust/Node/Docker/PostgreSQL как полноценный package manager;
- production/self-host deployment;
- Kubernetes, systemd units, Windows services;
- fully-containerized backend/frontend workflow;
- автоматическое удаление или reset реальной базы;
- автоматическое убийство чужих процессов на портах;
- миграционное лечение schema drift вслепую;
- скрытое включение `AUTH__ENABLE_DEV_HEADER_AUTH`;
- замену devctl patch conveyor;
- CI/CD систему.

Разрешено давать подсказки, команды и отчеты, но destructive actions должны быть отдельными командами с явным флагом подтверждения.

---

## 4. Предлагаемое место и имя инструмента

Базовый вариант:

```text
tools/devbootstrap.py
```

Почему отдельный файл, а не расширение `tools/devctl.py`:

- `devctl` отвечает за patch conveyor: применить patch.zip, checks, commit, archive;
- `devbootstrap` отвечает за runtime: env, DB, backend, frontend, smoke, процессы;
- оба инструмента могут использовать похожий стиль отчетов, но зоны ответственности разные;
- разделение снижает риск превратить devctl в труднообслуживаемый монолит.

Требование v1:

```text
pure Python standard library only
```

Это повторяет сильную сторону devctl:

- проще запускать на Windows/Linux;
- не нужен `pip install`;
- меньше bootstrap paradox;
- легче применять в AI-assisted patch workflow.

---

## 5. Пользовательский CLI v1

Минимальный набор команд:

```bash
python tools/devbootstrap.py diagnose
python tools/devbootstrap.py plan
python tools/devbootstrap.py prepare-env
python tools/devbootstrap.py start-db
python tools/devbootstrap.py check-backend
python tools/devbootstrap.py start-backend
python tools/devbootstrap.py prepare-frontend
python tools/devbootstrap.py start-frontend
python tools/devbootstrap.py smoke
python tools/devbootstrap.py status
python tools/devbootstrap.py stop
python tools/devbootstrap.py up
```

### 5.1. `diagnose`

Ничего не меняет.

Проверяет:

- OS/platform/shell;
- project root;
- наличие `backend/`, `frontend/`, `docs/`, `docker-compose.dev.yml`;
- наличие `backend/.env.example`, `frontend/.env.example`;
- наличие Python/Rust/Cargo/Node/npm/Git/Docker/Compose;
- занятость портов `5432`, `18080`, `5173`;
- наличие `.env` / `.env.local`;
- наличие `node_modules`;
- доступность PostgreSQL по `DATABASE__URL`, если env уже существует;
- доступность backend health, если backend уже запущен;
- доступность frontend dev server, если он уже запущен.

Выход:

- console summary;
- `.dev-bootstrap/runs/<timestamp>/report.md`;
- `.dev-bootstrap/runs/<timestamp>/diagnose.json`.

### 5.2. `plan`

Ничего не меняет.

Строит план действий для текущей машины:

- какие env-файлы будут созданы;
- будет ли использоваться Docker PostgreSQL или уже существующий PostgreSQL;
- какие команды будут выполнены;
- какие порты конфликтуют;
- какие действия требуют подтверждения;
- какие checks можно выполнить с текущими prerequisites.

### 5.3. `prepare-env`

Создает или аккуратно обновляет env-файлы.

Правила:

- если `backend/.env` отсутствует — скопировать из `backend/.env.example`;
- если `backend/.env` есть — не перезаписывать, а показать missing/extra keys;
- если нужно изменить файл — сделать backup `backend/.env.bootstrap-backup.<timestamp>`;
- если `frontend/.env.local` отсутствует — скопировать из `frontend/.env.example`;
- secrets в отчетах маскировать;
- `AUTH__ENABLE_DEV_HEADER_AUTH` не включать автоматически;
- проверять согласованность `APP__PORT`, `HTTP__CORS_ALLOWED_ORIGINS` и `VITE_API_BASE_URL`.

### 5.4. `start-db`

Поднимает PostgreSQL только безопасным способом.

Baseline v1:

- если PostgreSQL из `DATABASE__URL` доступен и похож на подходящий — использовать его;
- если не доступен, но Docker/Compose доступны и есть `docker-compose.dev.yml` — предложить `docker compose -f docker-compose.dev.yml up -d postgres`;
- если порт `5432` занят неизвестным процессом — не стартовать compose вслепую;
- если compose container проекта уже exists/stopped — можно стартовать его;
- если volume существует — не удалять;
- destructive reset volume не входит в обычный `start-db`.

### 5.5. `check-backend`

Проверяет backend до запуска.

Минимум:

```bash
cd backend
cargo check
```

Дополнительно:

- проверить `cargo metadata`;
- проверить наличие `backend/build.rs`;
- проверить наличие `backend/migrations/*.sql`;
- сохранить полный лог;
- классифицировать failure: missing cargo, dependency download, compile error, timeout.

### 5.6. `start-backend`

Запускает backend и ждет health.

Поведение:

- перед запуском проверить порт из `APP__PORT`, default `18080`;
- если порт занят неизвестным процессом — не убивать автоматически;
- если порт занят backend-процессом, запущенным прошлым run инструмента — предложить/выполнить safe restart;
- запустить `cargo run` в `backend/`;
- сохранить PID;
- читать stdout/stderr в `backend.log`;
- ждать `GET /health` и `GET /api/v1/health` с timeout;
- если процесс умер — классифицировать вероятную причину по логам.

### 5.7. `prepare-frontend`

Готовит frontend dependencies.

Правила:

- проверить `node --version`, `npm --version`;
- если есть `package-lock.json`, по умолчанию использовать `npm ci` для чистой установки;
- если `node_modules` уже существует — не удалять без подтверждения;
- если install marker/lock hash не совпадает — предложить reinstall;
- сохранить `npm install/npm ci` лог;
- проверить наличие scripts `dev`, `build`, `test:run`, `test:browser`;
- Playwright browsers не ставить автоматически в default path, но диагностировать и дать команду `npx playwright install` или отдельный `prepare-browser-smoke` в будущем.

### 5.8. `start-frontend`

Запускает Vite dev server.

Поведение:

- проверить `VITE_API_BASE_URL`;
- проверить, что backend health доступен по соответствующему base URL;
- проверить порт `5173`;
- запустить `npm run dev -- --host 127.0.0.1` или совместимый режим, если это не ломает текущий package script;
- сохранить PID;
- читать stdout/stderr в `frontend.log`;
- определить фактический URL Vite из лога, потому что Vite может выбрать другой порт;
- проверить HTTP доступность frontend root.

### 5.9. `smoke`

Запускает проверочный набор.

В v1 должно быть три уровня:

```bash
python tools/devbootstrap.py smoke --level quick
python tools/devbootstrap.py smoke --level standard
python tools/devbootstrap.py smoke --level full
```

`quick`:

- backend health;
- frontend root;
- frontend API base URL sanity;
- maybe lightweight auth/session probe, если backend уже живой.

`standard`:

- `cd backend && python tests/smoke_core_api.py`;
- `cd frontend && npm run test:run`.

`full`:

- `cargo test` или выбранный subset;
- `python tests/smoke_core_api.py`;
- `npm run test:run`;
- `npm run test:browser` при наличии Playwright browsers.

Важно:

- smoke не должен использовать destructive reset реальной dev-БД по умолчанию;
- если нужен destructive test DB — требовать `TEST_DATABASE_URL` и отдельный флаг;
- при failure сохранять stdout/stderr и краткий диагноз.

### 5.10. `status`

Показывает runtime state:

- последний run;
- PID backend/frontend, если инструмент их запускал;
- живы ли PID;
- какие порты заняты;
- health backend/frontend;
- Docker postgres status;
- path к последнему report.

### 5.11. `stop`

Останавливает только процессы, которыми владеет инструмент.

Правила:

- PID должен быть в `.dev-bootstrap/state.json`;
- проверять, что PID все еще похож на ожидаемый command/cwd;
- сначала graceful terminate;
- потом timeout;
- force kill только для собственного процесса;
- Docker postgres не останавливать по умолчанию, если пользователь не передал `--include-db`;
- чужие процессы на портах только диагностировать.

### 5.12. `up`

Главная команда happy path.

Эквивалент pipeline:

```text
diagnose
→ plan
→ prepare-env
→ start-db
→ check-backend
→ start-backend
→ prepare-frontend
→ start-frontend
→ smoke --level quick
→ report
```

`up` должен быть безопасным и повторяемым. Он не должен удалять данные и не должен убивать чужие процессы.

---

## 6. Runtime state и артефакты

Служебная папка:

```text
.dev-bootstrap/
  state.json
  runs/
    YYYYMMDD_HHMMSS_<slug>/
      report.md
      diagnose.json
      plan.md
      backend.log
      frontend.log
      cargo-check.log
      npm-install.log
      smoke.log
      env-diff.md
```

### 6.1. `state.json`

Минимальная структура:

```json
{
  "version": 1,
  "activeRunId": "20260513_120000_up",
  "processes": {
    "backend": {
      "pid": 12345,
      "cwd": "backend",
      "command": "cargo run",
      "startedAt": "2026-05-13T12:00:00Z",
      "runId": "20260513_120000_up"
    },
    "frontend": {
      "pid": 23456,
      "cwd": "frontend",
      "command": "npm run dev",
      "startedAt": "2026-05-13T12:01:00Z",
      "runId": "20260513_120000_up"
    }
  },
  "lastReports": []
}
```

Правила:

- state хранит только служебные данные;
- secrets туда не писать;
- пути лучше хранить относительными к project root, где возможно;
- при старте проверять stale PID и чистить state только после диагностики.

### 6.2. `diagnose.json`

Нужен для AI/devctl workflow.

Должен включать machine-readable summary:

- platform;
- project root;
- tool versions;
- env status без secrets;
- ports;
- postgres status;
- backend/frontend status;
- checks result;
- classified failures;
- next recommended action.

---

## 7. Внутренняя архитектура инструмента

Даже если v1 будет одним Python-файлом, внутри нужны явные слои.

Предлагаемые модули/секции:

```text
CLI parsing
Discovery
Report writer
Command runner
Platform adapter
Port inspector
Env parser/differ
Postgres inspector
Docker/Compose adapter
Backend runner
Frontend runner
Smoke runner
Process registry
Failure classifier
```

### 7.1. Discovery

Отвечает за:

- найти project root;
- определить, запущен ли инструмент из root/backend/frontend/tools;
- проверить обязательные файлы;
- найти `.dev-bootstrap/`.

### 7.2. Platform adapter

Отвечает за различия Windows/Linux:

- `python` vs `python3` vs `py`;
- `npm` vs `npm.cmd`;
- `cargo` vs `cargo.exe`;
- процессные сигналы;
- определение порта/PID;
- безопасное завершение процесса;
- кодировка stdout/stderr.

### 7.3. Env parser/differ

Отвечает за:

- простое чтение `.env` без сторонних пакетов;
- сохранение комментариев при минимальных изменениях, если это возможно;
- сравнение keys с `.env.example`;
- маскирование secrets;
- backup перед записью.

### 7.4. Postgres inspector

В v1 без сторонних Python-пакетов есть две стратегии:

1. использовать `psql`, если доступен;
2. запускать lightweight backend health/cargo run и классифицировать ошибки подключения по логам.

Желательно поддержать `psql`, но не делать его жестким prerequisite.

Проверки через `psql`, если возможно:

- `select 1`;
- `select current_database(), current_user`;
- наличие migration table;
- наличие ключевых таблиц проекта.

### 7.5. Docker/Compose adapter

Отвечает за:

- найти `docker`;
- проверить daemon;
- определить compose command: `docker compose` или legacy `docker-compose`, если поддержим;
- стартовать только `postgres` service;
- читать container health/status;
- не удалять volumes без отдельной команды.

### 7.6. Backend runner

Отвечает за:

- `cargo check`;
- `cargo run`;
- health wait;
- log tail;
- PID tracking;
- классификацию backend failures.

### 7.7. Frontend runner

Отвечает за:

- npm install/ci decision;
- `npm run dev`;
- Vite URL detection;
- frontend root readiness;
- npm/vite failure classification.

### 7.8. Failure classifier

Должен превращать низкоуровневые симптомы в понятные категории.

Пример категорий:

```text
missing_prerequisite
invalid_project_root
missing_env
invalid_env
port_conflict
postgres_unavailable
postgres_auth_failed
database_missing
database_not_project_db
migration_failed
cargo_check_failed
backend_start_failed
backend_health_timeout
npm_install_failed
frontend_start_failed
frontend_health_timeout
cors_or_api_base_mismatch
smoke_failed
unknown
```

---

## 8. Этапы разработки до v1

## Phase 0 — документационный baseline

Статус: текущий этап.

Результат:

- manifesto;
- pitfalls catalog;
- v1 development plan.

Acceptance criteria:

- понятно, зачем инструмент нужен;
- понятно, что он должен диагностировать;
- понятно, какой v1 считается достаточным.

---

## Phase 1 — skeleton CLI + read-only diagnose

Статус: implemented baseline in `tools/devbootstrap.py` (`diagnose`, `status`, report writer, root/tool/file/port/http probes). Следующие фазы должны расширять этот файл, не смешивая его с `tools/devctl.py`.

Цель:

- создать `tools/devbootstrap.py`;
- реализовать CLI skeleton;
- реализовать `diagnose` без побочных эффектов.

Команды:

```bash
python tools/devbootstrap.py diagnose
python tools/devbootstrap.py status
```

Что реализовать:

- project root discovery;
- platform summary;
- tool discovery: Python, Git, Cargo, Rustc, Node, npm, Docker;
- file presence checks;
- port checks for `5432`, `18080`, `5173`;
- basic report writer.

Проверки патча:

- `python -m` не нужен, достаточно прямого запуска;
- `ast.parse` для `tools/devbootstrap.py`;
- `python tools/devbootstrap.py diagnose` на архиве без изменения файлов проекта, кроме `.dev-bootstrap/runs/` если report включен.

Acceptance criteria:

- команда работает на проекте из архива;
- если инструменты отсутствуют, она не падает traceback-ом;
- отчет показывает, что есть, чего нет и где root.

---

## Phase 2 — env planner and safe env creation

Статус: implemented in `tools/devbootstrap.py` as `plan` / `prepare-env`.

Цель:

- научить инструмент понимать env-контракт проекта.

Команды:

```bash
python tools/devbootstrap.py plan
python tools/devbootstrap.py prepare-env
```

Что реализовать:

- чтение `.env.example`;
- чтение существующего `.env` / `.env.local`;
- diff keys;
- masked output для secrets/password/token;
- создание missing env-файлов из examples;
- backup перед изменением;
- проверка согласованности:
  - `APP__HOST` / `APP__PORT`;
  - `DATABASE__URL`;
  - `HTTP__CORS_ALLOWED_ORIGINS`;
  - `VITE_API_BASE_URL`;
  - `AUTH__ENABLE_DEV_HEADER_AUTH=false` как нормальный baseline.

Acceptance criteria:

- отсутствующие env создаются;
- существующие env не перетираются;
- report объясняет missing/extra/mismatched keys;
- secrets не попадают в логи.

Реализованные детали Phase 2:

- `plan` строит read-only env-план и может писать `.dev-bootstrap/runs/<timestamp>_plan/report.md`;
- `prepare-env` создает отсутствующие `backend/.env` и `frontend/.env.local` из example-файлов;
- существующие env-файлы по умолчанию не изменяются;
- `prepare-env --add-missing-keys` добавляет недостающие ключи из example-файла только после timestamped backup рядом с env-файлом;
- значения с `SECRET`, `PASSWORD`, `TOKEN`, `COOKIE`, `DATABASE__URL` маскируются в отчетах и JSON;
- выполняется sanity-check согласованности `APP__HOST`, `APP__PORT`, `DATABASE__URL`, `HTTP__CORS_ALLOWED_ORIGINS`, `VITE_API_BASE_URL` и `AUTH__ENABLE_DEV_HEADER_AUTH=false`;
- `plan --no-write-report` и `prepare-env --no-write-report` подходят для быстрых devctl/check прогонов.

---

## Phase 3 — PostgreSQL discovery and compose-assisted start

Статус: implemented in `tools/devbootstrap.py` as PostgreSQL subsystem diagnostics plus guarded compose-assisted `start-db`.

Цель:

- закрыть самый частый blocker: “а база вообще жива?”.

Команды:

```bash
python tools/devbootstrap.py diagnose --section postgres
python tools/devbootstrap.py start-db
python tools/devbootstrap.py start-db --dry-run
```

Реализованные детали Phase 3:

- effective `DATABASE__URL` читается из `backend/.env.example` + `backend/.env`;
- report показывает `host`, `port`, `database`, `user` и masked URL без пароля;
- TCP connect check проверяет именно host/port из `DATABASE__URL`, а не только дефолтный `5432`;
- optional `psql` probe делает короткий `select current_database() || '|' || current_user`, если `psql` есть в PATH;
- optional `pg_isready` probe добавляет readiness-сигнал, если утилита установлена;
- Docker CLI, Docker daemon и Compose обнаруживаются отдельно;
- поддерживаются Compose V2 (`docker compose`) и legacy `docker-compose`;
- `start-db` запускает только сервис `postgres` из `docker-compose.dev.yml`;
- compose start выполняется только когда configured PostgreSQL port закрыт;
- если порт уже открыт, инструмент не трогает окружение, чтобы не снести чужой PostgreSQL;
- `--dry-run` показывает planned compose command без запуска контейнеров;
- report включает compose status и Docker health probe для контейнера `p2p-planner-postgres-dev`, если Docker доступен;
- classification покрывает:
  - `ready`;
  - `port_closed`;
  - `port_open_unverified`;
  - `auth_failed`;
  - `db_missing`;
  - `database_url_invalid`;
  - `compose_unavailable`;
  - `docker_daemon_unavailable` через failures/actions при реальном `start-db`.

Acceptance criteria:

- на чистой машине без PostgreSQL, но с Docker, инструмент может поднять compose postgres;
- если порт занят чужим PostgreSQL, инструмент не ломает окружение и не запускает compose поверх открытого порта;
- если база не та, report показывает db/user/host без пароля;
- без Docker можно безопасно прогнать `diagnose --section postgres` и получить понятный next action.

---

## Phase 4 — backend check and backend start

Статус: implemented in `tools/devbootstrap.py` as `check-backend` / `start-backend` with cargo metadata/check, backend port preflight, guarded `cargo run`, PID/state/log capture, health wait and failure classification.

Цель:

- поднять backend до health и дать понятный диагноз при runtime failure.

Команды:

```bash
python tools/devbootstrap.py check-backend
python tools/devbootstrap.py start-backend
```

Что реализовать:

- `cargo --version`, `rustc --version`;
- `cargo metadata`;
- `cargo check`;
- port preflight для backend;
- запуск `cargo run`;
- PID tracking;
- health wait;
- log capture;
- migration failure hints;
- stale process detection.

Особое внимание:

- отличать compile failure от database failure;
- распознавать симптомы migration drift;
- не делать `cargo clean` автоматически;
- не убивать процесс на `18080`, если инструмент его не запускал.

Acceptance criteria:

- backend может быть поднят одной командой при готовой БД;
- health проверяется автоматически;
- при падении на БД/миграциях/порте report классифицирует причину.

---

## Phase 5 — frontend prepare and frontend start

Статус: implemented in `tools/devbootstrap.py` as `prepare-frontend` / `start-frontend` with npm dependency installation, install marker, Vite port preflight, guarded `npm run dev`, PID/state/log capture, frontend root readiness and API base sanity checks.

Цель:

- поднять Vite frontend и проверить, что он смотрит в правильный backend.

Команды:

```bash
python tools/devbootstrap.py prepare-frontend
python tools/devbootstrap.py start-frontend
```

Что реализовать:

- Node/npm discovery;
- package script discovery;
- `npm ci` / `npm install` decision;
- lockfile/install marker;
- Vite port preflight;
- запуск `npm run dev`;
- фактический URL из Vite лога;
- readiness probe frontend root;
- API base sanity против backend health.

Acceptance criteria:

- frontend dependencies устанавливаются или диагностируются;
- dev server стартует;
- если `VITE_API_BASE_URL` смотрит не туда, report говорит об этом до ручной отладки в браузере.

Реализованные детали Phase 5:

- `prepare-frontend` выбирает `npm ci` при наличии `package-lock.json`, иначе `npm install`;
- dependency install не повторяется без необходимости, если `frontend/node_modules` есть и `.dev-bootstrap/frontend-install.json` совпадает с hash `package.json` / `package-lock.json`;
- `--force-install` позволяет явно переустановить зависимости;
- `--dry-run` показывает план без изменения `node_modules`;
- `start-frontend` проверяет Node/npm, `scripts.dev`, `node_modules`, Vite port и frontend root;
- `start-frontend` запускает `npm run dev -- --host ... --port ... --strictPort`, пишет `frontend.log`, PID/state и ожидает HTTP root;
- report показывает фактический frontend URL, `VITE_API_BASE_URL`, API health probe, mismatch с backend port и подсказки next actions;
- инструмент не убивает чужой процесс на Vite port и не поднимает frontend поверх неясного port conflict.

---

## Phase 6 — one-command `up`

Статус: implemented in `tools/devbootstrap.py` as one-command safe orchestration over Phase 1–5 commands.

Цель:

- собрать безопасный happy path.

Команда:

```bash
python tools/devbootstrap.py up
python tools/devbootstrap.py up --dry-run
```

Реализованный pipeline:

```text
diagnose
→ plan
→ prepare-env          # в --dry-run заменяется read-only env plan
→ start-db
→ check-backend
→ start-backend
→ prepare-frontend
→ start-frontend
→ quick HTTP smoke     # backend health + frontend root
→ report
```

Опции:

```bash
--dry-run
--skip-install
--skip-cargo-check
--skip-db-start
--smoke-level quick|standard|full|none
--yes
--step-timeout-seconds N
--db-timeout-seconds N
--cargo-check-timeout-seconds N
--backend-timeout-seconds N
--npm-timeout-seconds N
--frontend-timeout-seconds N
```

Реализованные детали Phase 6:

- `up` запускает уже существующие команды как отдельные безопасные subcommand-шаги и сохраняет их stdout/stderr в единую папку `.dev-bootstrap/runs/<timestamp>_up/`;
- каждый шаг получает отдельный лог `01_diagnose.log`, `02_plan.log`, ... и общий `up.json` + `report.md`;
- pipeline останавливается на первом блокирующем failure и помечает последующие шаги как skipped;
- `--dry-run` не создает env-файлы, не стартует Docker/Cargo/npm процессы и использует read-only варианты шагов;
- `--skip-db-start`, `--skip-cargo-check`, `--skip-install` явно отражаются в report как skipped, а не исчезают из pipeline;
- `--smoke-level none` отключает финальный quick smoke;
- `--smoke-level standard|full` пока не запускает тяжелые gates: Phase 6 честно предупреждает, что полноценные standard/full smoke относятся к Phase 7, и выполняет только quick HTTP smoke;
- `--yes` зарезервирован под non-destructive автоматизацию и не разрешает reset DB, удаление volumes или убийство чужих процессов;
- общий report добавляется в `.dev-bootstrap/state.json` как последний report;
- итоговый report содержит runtime URL backend/frontend, если pipeline дошел до успешного старта.

Правила:

- `--yes` не должен разрешать destructive actions;
- `up` не должен делать reset DB;
- `up` не должен убивать чужие процессы;
- `up` должен быть идемпотентным.

Acceptance criteria:

- на машине с prerequisites инструмент доводит проект до backend + frontend alive;
- повторный запуск не ломает уже поднятую среду;
- report содержит URL backend/frontend и путь к логам;
- `python tools/devbootstrap.py up --dry-run` можно запускать как безопасный devctl/check smoke без Docker/Rust/Node side effects.

---

## Phase 7 — smoke gates

Статус: implemented in `tools/devbootstrap.py` as post-start smoke gates and as the final `up --smoke-level ...` step.

Цель:

- сделать полезные проверки после запуска;
- отделить “runtime не поднят” от “тест/код сломан”;
- сохранить логи каждого smoke-шага в одном отчете.

Команда:

```bash
python tools/devbootstrap.py smoke --level quick
python tools/devbootstrap.py smoke --level standard
python tools/devbootstrap.py smoke --level full
```

Реализованные уровни:

- `quick`:
  - `GET /health`;
  - `GET /api/v1/health`;
  - frontend root probe по эффективному Vite URL.
- `standard`:
  - весь `quick`;
  - DB write guard;
  - `python backend/tests/smoke_core_api.py` с `BASE_URL` из эффективного frontend/backend env;
  - `npm run test:run` во `frontend/`.
- `full`:
  - весь `standard`;
  - `npm run test:browser` во `frontend/`.

Реализованные детали Phase 7:

- `smoke` пишет `.dev-bootstrap/runs/<timestamp>_smoke/report.md` и `smoke.json`;
- command-based шаги пишут отдельные stdout/stderr logs;
- quick HTTP probes пишутся отдельным JSON-log;
- failure classification различает `backend_unreachable`, `frontend_unreachable`, `runtime_unreachable`, `smoke_db_write_guard`, `backend_smoke_failed`, `frontend_tests_failed`, `browser_smoke_failed`, `browser_smoke_prerequisite`, `missing_prerequisite`;
- `up --smoke-level quick|standard|full|none` теперь вызывает тот же smoke runner вместо Phase 6 quick-only заглушки;
- `up --dry-run` не запускает smoke, а показывает planned step.

Особое правило для БД:

- `standard/full` smoke проходит через backend API и может создавать/изменять данные;
- поэтому write-capable smoke требует `TEST_DATABASE_URL` или явного `--allow-dev-db-write`;
- если используется явный `--allow-dev-db-write` и effective DB выглядит как обычная `p2p_planner`, инструмент добавляет предупреждение;
- наличие `TEST_DATABASE_URL` тоже фиксируется в отчете, но инструмент честно предупреждает, что уже запущенный backend должен быть поднят именно против нужной тестовой БД.

Acceptance criteria:

- пользователь понимает, какая проверка упала;
- можно отличить “код сломан” от “окружение не готово”;
- `python tools/devbootstrap.py smoke --level quick` дает быстрый runtime verdict;
- `python tools/devbootstrap.py smoke --level standard` не пишет в обычную dev-БД без явного разрешения;
- `python tools/devbootstrap.py up --smoke-level standard --allow-dev-db-write` использует тот же smoke gate и сохраняет итог в общем `up` report.

---

## Phase 8 — stop, cleanup hints and stale state handling

Статус: implemented in `tools/devbootstrap.py` as enhanced `status` plus safe `stop` over tracked backend/frontend processes and optional compose postgres stop.

Цель:

- закрыть жизненный цикл dev-сессии.

Команды:

```bash
python tools/devbootstrap.py status
python tools/devbootstrap.py stop
python tools/devbootstrap.py stop --include-db
```

Что реализовать:

- отображение active processes;
- проверка PID/cwd/command перед stop;
- graceful shutdown backend/frontend;
- stale PID cleanup;
- Docker postgres stop только по `--include-db`;
- итоговый cleanup report;
- подсказки про оставшиеся чужие процессы на портах.

Acceptance criteria:

- после `stop` освобождаются backend/frontend процессы, поднятые инструментом;
- чужие процессы не трогаются;
- пользователь видит, что осталось живым.

Реализованные детали Phase 8:

- `status` теперь показывает не только `.dev-bootstrap/state.json`, но и runtime-поверхность: tracked PID liveness, backend/frontend/PostgreSQL ports, backend health, frontend root и Docker Compose status;
- `status --json` выводит тот же snapshot в machine-readable виде;
- `stop` читает только `.dev-bootstrap/state.json` и работает только с tracked `backend` / `frontend`;
- перед остановкой выполняется ownership guard: PID должен быть живым, имя процесса должно быть поддерживаемым, cwd/command сверяются с ожидаемыми `backend/` + `cargo` или `frontend/` + `npm`;
- на POSIX при наличии `/proc` используется фактический process cwd/cmdline; на платформах без такой проверки включается ограниченный guard по сохраненным state cwd/command;
- процессы, запущенные новыми `start-backend` / `start-frontend`, стартуют в отдельной process group/session, чтобы `stop` мог завершать дерево безопаснее;
- stale PID entries удаляются из state без попытки kill;
- graceful SIGTERM идет первым, затем после timeout force kill для own process, если не передан `--no-force`;
- `stop --dry-run` показывает план без остановки процессов и без изменения state;
- `stop --include-db` выполняет только `docker compose ... stop postgres`, без `down`, удаления volume или destructive reset;
- по умолчанию PostgreSQL не останавливается, чтобы не ломать долгоживущую dev-БД;
- итоговый `stop` report содержит actions, verification evidence, ports/http probes after stop и next safe actions.

---

## Phase 9 — hardening до v1

Статус: **реализовано**.

Цель:

- превратить набор команд в надежный v1 tool.

Что сделано:

- поднята версия `tools/devbootstrap.py` до `1.0.0`;
- добавлен `self-check` как внутренний sanity suite без внешних Python packages;
- `self-check` проверяет env parser/masking, env diff, database URL parse, root discovery, failure classifiers, `report.md` baseline и JSON report envelope;
- добавлен общий JSON-envelope для report payloads: `schemaVersion`, `command`, `toolVersion`, `generatedAt`, `status`;
- основные timeout defaults собраны в `TIMEOUT_POLICY`;
- добавлена эксплуатационная памятка `docs/dev-bootstrap/devbootstrap-v1-operations.md`;
- README и docs index обновлены quick commands и v1-status;
- devctl manifest будущих патчей должен запускать `ast.parse` и `python tools/devbootstrap.py self-check --no-write-report`.

Acceptance criteria:

- инструмент можно добавить в routine после применения патча;
- он не требует сторонних Python packages;
- основные ошибки окружения классифицируются;
- есть понятное “что делать дальше”;
- есть проверяемая команда `self-check`, которую можно запускать в devctl checks.

---

## 9. Минимальный v1 scope

Чтобы не расползтись, v1 считается готовым при наличии такого набора:

### Must-have commands

- `diagnose`;
- `plan`;
- `prepare-env`;
- `start-db`;
- `check-backend`;
- `start-backend`;
- `prepare-frontend`;
- `start-frontend`;
- `smoke --level quick`;
- `status`;
- `stop`;
- `up`.

### Must-have diagnostics

- project root;
- OS/platform;
- Python/Cargo/Rust/Node/npm/Docker versions;
- env presence/diff;
- masked effective config;
- port conflicts;
- PostgreSQL TCP availability;
- backend health;
- frontend readiness;
- PID ownership;
- log paths;
- classified error code.

### Must-have safety

- no destructive DB reset;
- no overwriting env without backup;
- no secret leakage;
- no killing unknown processes;
- no automatic global package installs;
- no production claims.

### Must-have project-specific checks

- `backend/.env.example` exists;
- `frontend/.env.example` exists;
- `docker-compose.dev.yml` has postgres service;
- `backend/build.rs` exists;
- `backend/migrations/` exists;
- backend health endpoints answer;
- frontend API base URL points to backend `/api/v1`;
- auth baseline is bearer/session, not accidental `X-User-Id` dependency.

---

## 10. Error message quality bar

Плохой v1 error:

```text
Backend failed.
```

Хороший v1 error:

```text
backend_start_failed: backend process exited before health became ready.
Likely cause: PostgreSQL connection failed.
DATABASE__URL points to 127.0.0.1:5432/p2p_planner as user postgres.
TCP connection to 127.0.0.1:5432 succeeded, but SQL probe failed: database "p2p_planner" does not exist.
Next safe actions:
1. Run: docker compose -f docker-compose.dev.yml up -d postgres
2. Or create database p2p_planner in your local PostgreSQL.
3. Or edit backend/.env DATABASE__URL to point to the correct database.
Full log: .dev-bootstrap/runs/20260513_120000_up/backend.log
```

Каждая ошибка должна иметь:

- stable code;
- human explanation;
- evidence;
- next safe action;
- log path.

---

## 11. Проверки самого инструмента

Для будущих патчей с `tools/devbootstrap.py` минимальный check в `manifest.json` должен быть таким:

```json
{
  "name": "Python syntax без генерации __pycache__",
  "cwd": ".",
  "command": "python -c \"import ast,pathlib; files=['tools/devbootstrap.py']; [ast.parse(pathlib.Path(p).read_text(encoding='utf-8'), filename=p) for p in files]\"",
  "requiredCommands": ["python"],
  "timeoutSeconds": 120
}
```

После появления тестов можно добавить:

```bash
python tools/devbootstrap.py diagnose --no-write-report
python tools/devbootstrap.py plan --no-write-report
```

Важно: проверки инструмента не должны требовать живого PostgreSQL, Cargo или npm для базового syntax gate.

---

## 12. Интеграция с devctl

`devbootstrap` не заменяет `devctl`, но может стать check-командой в devctl manifest.

Примеры будущих checks:

```text
python tools/devbootstrap.py diagnose --no-write-report
python tools/devbootstrap.py check-backend --no-start
python tools/devbootstrap.py smoke --level quick
```

Граница ответственности:

- `devctl` применяет patch.zip, запускает declared checks, делает commit/archive;
- `devbootstrap` проверяет и поднимает runtime окружение;
- `devctl` не должен молча стартовать PostgreSQL/backend/frontend, если patch manifest этого явно не требует;
- `devbootstrap` не должен применять patch.zip.

---

## 13. Риски разработки самого инструмента

### 13.1. Риск “второй devctl-монолит”

Как избежать:

- держать отдельный файл/инструмент;
- делать команды маленькими;
- каждый этап завершать работающим read-only или safe action;
- не смешивать patch workflow и runtime workflow.

### 13.2. Риск “слишком магический up”

Как избежать:

- `plan` перед actions;
- clear report;
- no destructive defaults;
- explicit `--yes` только для safe actions;
- отдельные команды для каждого слоя.

### 13.3. Риск “кроссплатформенность вспомнили в конце”

Как избежать:

- с первого патча использовать `pathlib`, `subprocess` args-list, `shutil.which`;
- не писать bash-only команды внутри Python;
- проверять Windows/Linux assumptions в docs и тестах;
- не полагаться на `lsof`, `netstat`, `taskkill`, `fuser` как единственный путь.

### 13.4. Риск “диагностика хуже ручной отладки”

Как избежать:

- сохранять полные логи;
- не обрезать stderr до бесполезности;
- stable error codes;
- next action hints;
- distinguish environment failure from project failure.

---

## 14. Предлагаемый порядок будущих патчей

### Patch 1 — skeleton + diagnose

Файлы:

- `tools/devbootstrap.py`;
- `docs/dev-bootstrap/dev-autodeployer-v1-development-plan.md` update;
- возможно README quick note.

Проверки:

- `ast.parse`;
- `python tools/devbootstrap.py diagnose --no-write-report`.

### Patch 2 — env plan/prepare

Файлы:

- `tools/devbootstrap.py`;
- tests/fixtures при необходимости;
- docs update.

Проверки:

- env parser unit-like self-check через Python stdlib;
- no secret leakage samples.

### Patch 3 — postgres/docker checks

Файлы:

- `tools/devbootstrap.py`;
- docs update.

Проверки:

- works without Docker by reporting missing docker cleanly;
- no destructive volume operations.

### Patch 4 — backend check/start

Файлы:

- `tools/devbootstrap.py`;
- docs update.

Проверки:

- syntax;
- fake command fixtures if real Cargo unavailable in patch environment;
- real run on local machine later.

### Patch 5 — frontend prepare/start

Файлы:

- `tools/devbootstrap.py`;
- docs update.

Проверки:

- syntax;
- script discovery;
- fake npm fixtures if needed.

### Patch 6 — `up`, smoke, stop

Файлы:

- `tools/devbootstrap.py`;
- docs update;
- README update.

Проверки:

- dry-run plan;
- quick smoke against already running stack;
- safe stop only own processes.

### Patch 7 — v1 hardening

Файлы:

- `tools/devbootstrap.py`;
- `docs/dev-bootstrap/devbootstrap-v1-operations.md`;
- README/docs index updates;
- devctl patch manifest checks.

Проверки:

- `ast.parse` for `tools/devbootstrap.py` and `tools/devctl.py`;
- `python tools/devbootstrap.py self-check --no-write-report`;
- `python tools/devbootstrap.py diagnose --no-write-report`;
- `python tools/devbootstrap.py up --dry-run --smoke-level quick`;
- `python tools/devbootstrap.py stop --dry-run --no-write-report`;
- Windows/Linux manual matrix later on real machines;
- clean archive quickstart;
- dirty machine scenario.

---

## 15. v1 acceptance checklist

Инструмент можно назвать v1, если на машине с установленными Python, Rust, Node/npm и Docker он умеет:

- [ ] найти проект из корня, `tools/`, `backend/` или `frontend/`;
- [ ] создать missing env-файлы без перезаписи существующих;
- [ ] проверить env mismatch и CORS/API URL mismatch;
- [ ] поднять PostgreSQL через `docker-compose.dev.yml`, если нет подходящего живого PostgreSQL;
- [ ] обнаружить чужой процесс на `5432`, `18080`, `5173` и не сломать его;
- [ ] выполнить `cargo check`;
- [ ] запустить backend;
- [ ] дождаться `/health` и `/api/v1/health`;
- [ ] установить frontend dependencies;
- [ ] запустить Vite frontend;
- [ ] показать фактические backend/frontend URLs;
- [ ] выполнить quick smoke;
- [ ] сохранить report/logs;
- [ ] остановить backend/frontend процессы, которые сам поднял;
- [x] оставить понятное объяснение при каждом частом сбое.
- [x] иметь внутренний `self-check` для env diff / URL parse / classifier / report-contract fixtures.
- [x] иметь общий JSON-envelope для отчетов и документированную timeout policy.

---

## 16. Короткий итог

Разработку auto-bootstrapper стоит вести не как “написать большой запускатор”, а как последовательность безопасных слоев:

```text
read-only diagnose
→ safe env prep
→ DB readiness
→ backend readiness
→ frontend readiness
→ one-command up
→ smoke
→ stop/cleanup
→ hardening
```

Такой путь дает пользу уже с первого патча, не требует сразу решать все инфраструктурные проблемы и сохраняет главную философию инструмента:

```text
сначала понять окружение,
потом действовать,
в конце оставить человеку и AI понятный отчет.
```
