# Deployment / packaging v1

- Статус: Draft v1
- Дата: 2026-04-16
- Назначение: зафиксировать **картину поставки, сборки, окружений и runtime-конфига** после фиксации core architecture, local-first направления, auth/session baseline, optional relay abstraction, security baseline и testing strategy.

> Этот документ опирается на `ADR-001`, `ADR-004`, `docs/product/mvp-scope-v1.md`, `docs/architecture/auth-and-identity-v1.md`, `docs/architecture/p2p-relay-bootstrap-abstraction-v1.md`, `docs/architecture/security-privacy-threat-model-v1.1.md`, `docs/architecture/testing-strategy-v1.md` и `docs/architecture/testing-application-guide-v1.md`.

---

## 1. Что считаем целью этапа

На этом этапе нужно собрать **практичную v1-картину поставки**, не притворяясь, что у проекта уже есть окончательный production runbook.

Нужно определить:
- какие deployment units есть у системы сейчас;
- какие окружения нам реально нужны на ближайшем горизонте;
- как запускать проект локально и в self-host режиме;
- какие env-переменные считаются runtime-контрактом;
- что именно собирается как backend artifact, frontend artifact и optional future service;
- как сделать процесс разработки и последующих патчей **простым, воспроизводимым и удобным для human + AI-assisted workflow**.

Этот этап **не** обещает:
- финальную облачную инфраструктуру;
- Kubernetes и multi-region схему;
- окончательный production hardening всех security деталей;
- обязательный relay/p2p deployment уже в MVP;
- окончательную CI/CD систему.

---

## 2. Главный вывод

Для текущего проекта фиксируется **простая и консервативная deployment-модель**:
- `backend` — обязательный stateful HTTP/API и auth/session service;
- `postgres` — обязательное постоянное хранилище backend-состояния;
- `frontend` — отдельный web artifact со статической сборкой;
- `relay/bootstrap` — **необязательный future service**, отделенный от backend deployment unit.

Практическая формула v1:
- в **local dev** backend и frontend запускаются нативно ради скорости итераций, а Docker используется прежде всего для PostgreSQL;
- в **self-host alpha / preview** backend поставляется как отдельный service/container, frontend — как статическая сборка, PostgreSQL — как отдельная база;
- **same-origin или same-site deployment** предпочтительнее cross-site схемы, потому что это проще для cookie/session security;
- optional relay не вшивается в core deployment и не должен маскироваться под обязательную часть MVP.

Иными словами:
**проект поставляется как modular monolith backend + web client + PostgreSQL, а relay/p2p остается отдельной будущей эволюцией transport layer.**

---

## 3. Что считаем deployment units

## 3.1. Обязательные units текущей версии

### A. Backend service
Отвечает за:
- HTTP API;
- auth/session flow;
- бизнес-логику workspace / board / column / card;
- appearance;
- activity / audit;
- startup migrations;
- будущую coordinator-роль для sync.

Deployment unit:
- один процесс / один контейнер / один release artifact.

### B. PostgreSQL
Отвечает за:
- каноническое server-side состояние;
- identity/session tables;
- workspace/board/card data;
- activity/audit/change foundations.

Deployment unit:
- отдельная database service.

### C. Frontend web artifact
Отвечает за:
- browser UI;
- app shell;
- auth/session bootstrap в браузере;
- workspace/board/card UX;
- future local-first клиентский слой.

Deployment unit:
- статическая сборка (`vite build`) для CDN, reverse proxy или simple static hosting.

## 3.2. Необязательные future units

### D. Relay / bootstrap service
На текущем этапе:
- **не обязателен для MVP deployment**;
- не должен считаться частью минимального локального или self-host запуска;
- позже может появиться как отдельный service для transport hints, rendezvous или relay-assisted delivery.

Принцип:
- relay — это **transport helper**, а не semantic owner конфликтов и не замена coordinator backend.

---

## 4. Модель окружений

Для проекта фиксируются следующие окружения.

## 4.1. `local_dev`
Назначение:
- одиночная разработка;
- быстрые патчи;
- работа вместе с AI по архивам и точечным изменениям;
- ручная отладка backend/frontend/test flow.

Свойства:
- backend и frontend запускаются нативно;
- PostgreSQL поднимается через Docker Compose или локально установленный сервис;
- порты фиксированы и предсказуемы;
- допустимы dev-only послабления вроде `cookie_secure=false` и локальных origins.

Предпочтительная схема:
- frontend: `http://127.0.0.1:5173`
- backend: `http://127.0.0.1:18080`
- postgres: `127.0.0.1:5432`

## 4.2. `shared_dev` / `test_local`
Назначение:
- воспроизводимый запуск на другой машине;
- smoke/integration/browser checks;
- сверка патчей, присланных частями.

Свойства:
- максимально похож на `local_dev`, но с большей дисциплиной по `.env` и тестовой БД;
- `DATABASE_URL` / `TEST_DATABASE_URL` должны быть заданы явно;
- тестовые прогоны не должны зависеть от случайно "грязной" dev-базы.

## 4.3. `preview_self_host_alpha`
Назначение:
- self-host proof-of-use;
- ранний демонстрационный сервер;
- первая сборка, которую можно поднять вне dev-машины.

Свойства:
- backend собирается в release artifact;
- frontend собирается как статический bundle;
- база отдельная и постоянная;
- auth/session flow уже реальный, без притворства, что это только dev bridge;
- same-origin или same-site схема предпочтительнее.

## 4.4. `beta_hardened`
Назначение:
- следующий этап перед более серьезным self-host использованием.

Свойства:
- `Secure` cookies;
- строгий CORS allowlist;
- явная cookie/CSRF posture;
- секреты и ротация ключей;
- release gates из security/testing docs должны быть реально выполнены.

## 4.5. `future_relay_assisted`
Назначение:
- optional transport evolution после MVP.

Свойства:
- relay/bootstrap появляется как отдельный deployment unit;
- coordinator backend остается валидным fallback;
- отсутствие relay не делает систему неработоспособной.

---

## 5. Build profiles

Проекту нужны не "десять профилей на все случаи", а несколько практичных режимов.

## 5.1. Dev profile

### Backend
- запуск через `cargo run`;
- логирование `pretty`;
- migrations применяются на старте;
- `.env` читается через `dotenvy`;
- допускается `APP__ENV=local`.

### Frontend
- запуск через `npm run dev`;
- Vite dev server;
- API адрес задается через `VITE_API_BASE_URL`.

### Назначение
- максимальная скорость обратной связи;
- удобно править код и сразу перепроверять;
- удобно присылать и применять патчи только по измененным файлам.

## 5.2. Test / verification profile

### Backend
- `cargo test`;
- `python tests/smoke_core_api.py`;
- отдельная тестовая БД через `TEST_DATABASE_URL` или `DATABASE_URL`.

### Frontend
- `npm run test:run`;
- `npm run test:browser`.

### Назначение
- короткий локальный gate перед коммитом или упаковкой очередного патча.

## 5.3. Release / self-host profile

### Backend
- `cargo build --release`;
- отдельный runtime env;
- реальный `AUTH__JWT_SECRET`;
- осознанная cookie policy.

### Frontend
- `npm run build`;
- публикация `dist/` как static artifact.

### Назначение
- self-host alpha / preview deployment без dev-only допущений в runtime policy.

---

## 6. Packaging strategy

## 6.1. Backend packaging

Backend поставляется как:
- **предпочтительно один release binary** для ручного/self-host запуска;
- либо как контейнер вокруг этого binary.

Причина:
- это соответствует modular monolith архитектуре;
- не раздувает MVP микросервисной сложностью;
- удобно и для ручной разработки, и для AI-assisted patch workflow.

Ключевое правило:
- migrations живут рядом с backend и применяются на старте;
- изменение `migrations/` требует корректной пересборки, что уже учитывается через `build.rs`.

## 6.2. Frontend packaging

Frontend поставляется как:
- статическая web-сборка (`dist/`);
- может обслуживаться отдельным static host, reverse proxy или CDN.

Ключевое правило:
- frontend **не хранит runtime secrets**;
- `VITE_*` переменные — это build-time/public config, а не secret storage.

## 6.3. Database packaging

PostgreSQL не должен маскироваться под внутреннюю часть backend-binary.

Правило:
- база — отдельный управляемый service;
- для local dev допускается Docker Compose;
- для self-host допускается отдельный контейнер/managed PostgreSQL.

## 6.4. Relay packaging

Future relay/bootstrap service должен поставляться **отдельно**.

Он не должен:
- внедряться внутрь frontend bundle;
- подменять собой backend;
- становиться обязательным элементом локального запуска.

---

## 7. Runtime config boundaries

## 7.1. Backend runtime config

Backend runtime-конфиг читается из:
- `config/default.toml`;
- environment variables;
- локального `.env` в dev.

Границы backend runtime config:
- сетевые параметры (`app.*`);
- база данных (`database.*`);
- HTTP limits/CORS (`http.*`);
- auth/cookie/token/rate-limit параметры (`auth.*`).

Это **runtime config**, а не compile-time feature matrix.

## 7.2. Frontend runtime/build config

Frontend использует только публичный Vite-конфиг (`VITE_*`).

Границы frontend config:
- API base URL;
- несекретные feature flags.

Frontend **не должен** получать через `VITE_*`:
- JWT secret;
- cookie secret;
- database credentials;
- любые иные приватные server secrets.

## 7.3. Предпочтительная граница между frontend и backend

Предпочтительно:
- один site-контекст или same-site схема;
- backend управляет auth/session cookies;
- frontend хранит access token только как короткоживущий in-memory state.

Не рекомендуется считать baseline v1:
- сложный cross-site deployment с отдельной CSRF-платформой, если можно обойтись проще.

---

## 8. `.env` contract v1

Ниже фиксируется минимальный env-контракт, который уже согласован с текущим кодом и ближайшей поставкой.

## 8.1. Backend env contract

| Переменная | Обязательность | Dev default | Назначение |
|---|---|---:|---|
| `APP__NAME` | optional | `p2p-planner-backend` | Имя сервиса для логов/диагностики |
| `APP__ENV` | recommended | `local` | Среда выполнения: `local`, `dev`, `preview`, `production` и т.п. |
| `APP__HOST` | optional | `127.0.0.1` | Адрес bind для HTTP сервера |
| `APP__PORT` | optional | `18080` | Порт backend |
| `APP__LOG_FORMAT` | optional | `pretty` | `pretty` или `json` |
| `DATABASE__URL` | required | `postgres://postgres:postgres@127.0.0.1:5432/p2p_planner` | Подключение к PostgreSQL |
| `DATABASE__MAX_CONNECTIONS` | optional | `20` | Верхний лимит пула |
| `DATABASE__MIN_CONNECTIONS` | optional | `1` | Нижний лимит пула |
| `DATABASE__CONNECT_TIMEOUT_SECS` | optional | `5` | Таймаут коннекта к БД |
| `HTTP__BODY_LIMIT_MB` | optional | `4` | Размер request body |
| `HTTP__CORS_ALLOWED_ORIGINS` | recommended | `http://localhost:5173,http://127.0.0.1:5173` | Allowlist origins для browser access |
| `AUTH__JWT_SECRET` | required вне demo/dev | `change-me-local-dev-secret` | Секрет подписи access token |
| `AUTH__PREVIOUS_JWT_SECRETS` | optional | пусто | Старые ключи для ротации |
| `AUTH__ACCESS_TOKEN_TTL_MINUTES` | optional | `15` | TTL access token |
| `AUTH__REFRESH_TOKEN_TTL_DAYS` | optional | `30` | TTL refresh session |
| `AUTH__PUBLIC_SIGNUP_ENABLED` | optional | `true` | Разрешить публичный sign-up |
| `AUTH__REFRESH_COOKIE_NAME` | optional | `p2p_planner_refresh` | Имя refresh cookie |
| `AUTH__DEVICE_COOKIE_NAME` | optional | `p2p_planner_device` | Имя device cookie |
| `AUTH__COOKIE_SAME_SITE` | recommended | `lax` | `lax`, `strict` или `none` |
| `AUTH__COOKIE_SECURE` | recommended | `false` в local dev | `true` для HTTPS deployment |
| `AUTH__ENABLE_DEV_HEADER_AUTH` | optional | `false` | Dev-only fallback для `X-User-Id`, не baseline для normal web flow |
| `AUTH__AUTH_RATE_LIMIT_WINDOW_SECS` | optional | `60` | Окно rate limit для auth routes |
| `AUTH__AUTH_RATE_LIMIT_MAX_ATTEMPTS` | optional | `20` | Лимит попыток auth |
| `AUTH__SENSITIVE_RATE_LIMIT_WINDOW_SECS` | optional | `60` | Окно для sensitive actions |
| `AUTH__SENSITIVE_RATE_LIMIT_MAX_ATTEMPTS` | optional | `60` | Лимит для sensitive actions |

### Важные правила

1. Для non-dev deployment нельзя оставлять тестовый `AUTH__JWT_SECRET`.
2. Для HTTPS deployment `AUTH__COOKIE_SECURE=true`.
3. Для strict self-host нужно явно зафиксировать cookie/CORS posture вместе с выбранной доменной схемой.
4. `AUTH__ENABLE_DEV_HEADER_AUTH` не должен включаться по привычке в preview/prod.
5. Если dev header auth включен, browser-access routes должны продолжать корректно пропускать `X-User-Id` через CORS allowlist.

## 8.2. Frontend env contract

| Переменная | Обязательность | Dev default | Назначение |
|---|---|---:|---|
| `VITE_API_BASE_URL` | recommended | `http://127.0.0.1:18080/api/v1` | Базовый URL backend API |
| `VITE_ENABLE_PROJECT_ROADMAP_SEED` | optional | `true` | Автосид внутренней roadmap-доски в dev/demo окружении |

### Важные правила

1. `VITE_*` переменные считаются публичными.
2. В frontend env нельзя хранить secrets.
3. Для self-host same-origin схемы допустимо собирать frontend с `VITE_API_BASE_URL=/api/v1`.
4. `VITE_ENABLE_PROJECT_ROADMAP_SEED` лучше отключать в preview/beta, если нужен чистый демонстрационный инстанс.

---

## 9. Docker / dev setup

## 9.1. Главный выбор для dev

Для текущего этапа выбирается **не fully-containerized dev**, а более простой режим:
- PostgreSQL — в Docker Compose;
- backend — нативно (`cargo run`);
- frontend — нативно (`npm run dev`).

Почему это правильно именно сейчас:
- быстрее править код и перепроверять изменения;
- проще для AI-assisted патчей по архивам;
- меньше скрытой инфраструктурной магии;
- меньше ложных проблем вокруг volume mounts, live reload и container networking.

## 9.2. Минимальный Docker scope

В репозитории допустим `docker-compose.dev.yml` только для инфраструктуры, без попытки завернуть в него весь workflow насильно.

Минимум:
- `postgres`;
- volume для данных;
- healthcheck.

## 9.3. Когда можно контейнеризовать больше

Полная контейнеризация backend/frontend оправдана позже, если появится явная потребность:
- демонстрационный сервер;
- унификация окружений в команде;
- CI images;
- self-host templates.

Но это не должно усложнять обычную локальную разработку раньше времени.

---

## 10. Local dev workflow v1

Рекомендуемый минимальный поток работы:

### 10.1. Поднять PostgreSQL

Из корня проекта:

```bash
docker compose -f docker-compose.dev.yml up -d postgres
```

### 10.2. Подготовить backend env

```bash
cp backend/.env.example backend/.env
```

Потом при необходимости скорректировать `DATABASE__URL` и `AUTH__JWT_SECRET`.

### 10.3. Запустить backend

```bash
cd backend
cargo run
```

Проверка:
- `GET /health`
- `GET /api/v1/health`

### 10.4. Подготовить frontend env

```bash
cp frontend/.env.example frontend/.env.local
```

### 10.5. Запустить frontend

```bash
cd frontend
npm install
npm run dev
```

### 10.6. Пройти базовый UI flow

- открыть web-клиент;
- создать пользователя через sign-up;
- убедиться, что `auth/session` восстановился;
- открыть/создать workspace и board.

### 10.7. Прогнать минимальный local gate

```bash
cd frontend
npm run test:run
```

```bash
cd backend
python tests/smoke_core_api.py
```

```bash
cd frontend
npm run test:browser
```

---

## 11. Self-host baseline v1

## 11.1. Предпочтительная схема

### Вариант A — same-origin reverse proxy
Рекомендуемый baseline для self-host:
- один публичный origin;
- frontend static files и backend API доступны через один site-контекст;
- cookies работают в более предсказуемом режиме.

Примерно:
- `https://planner.example.com/` -> frontend static bundle
- `https://planner.example.com/api/v1/` -> backend

Плюсы:
- проще cookie/session posture;
- проще CORS;
- меньше шансов сломать auth на конфигурации.

### Вариант B — same-site split
Допустимый второй вариант:
- `https://app.example.com`
- `https://api.example.com`

Требования:
- явный CORS allowlist;
- проверенная cookie policy;
- безопасный HTTPS-only режим.

## 11.2. Что пока не делаем baseline-решением

Не считаем baseline v1:
- cross-site deployment с отдельными site-контекстами без крайней необходимости;
- relay как обязательный интернет-facing service;
- смешивание preview/self-host и production-grade hardening в один неразличимый режим.

---

## 12. Release channels

Для проекта фиксируются такие каналы.

## 12.1. `dev-local`
Для ежедневной разработки.

Свойства:
- локальные порты;
- `.env` рядом с кодом;
- `pretty` logs;
- Docker только для БД или вообще без Docker.

## 12.2. `alpha-preview`
Для ручного demo/self-host preview.

Свойства:
- release backend binary или container;
- static frontend build;
- отдельная БД;
- уже реальный session flow;
- но без обещания production-grade ops maturity.

## 12.3. `beta-candidate`
Для следующей стадии качества.

Свойства:
- security release gates выполнены;
- test gates стабильны;
- cookie/CORS posture явно проверена;
- dev-only режимы отключены.

## 12.4. `future-relay-experimental`
Отдельный будущий экспериментальный канал для relay/bootstrap.

Свойства:
- не ломает обычный coordinator-only deploy;
- не внедряется silently в стандартный self-host baseline.

---

## 13. План внедрения deployment слоя

## Phase 0 — фиксируем базовый контракт
- `deployment-packaging-v1.md`;
- `.env.example` для backend;
- `frontend/.env.example` как публичный build-config baseline;
- `docker-compose.dev.yml` для PostgreSQL.

## Phase 1 — стабилизируем local/self-host alpha
- актуализировать README и launch steps;
- проверить quickstart на чистой машине;
- держать dev workflow простым и предсказуемым.

## Phase 2 — beta hardening
- cookie/CORS/CSRF policy по выбранной схеме;
- secrets и key rotation discipline;
- явное отключение dev-only auth paths;
- release checklist из security/testing docs.

## Phase 3 — optional relay packaging
- отдельный relay/bootstrap service;
- отдельный env contract;
- fallback на coordinator-only mode;
- transport-level rollout без переписывания core deployment.

---

## 14. Что делает этот deployment слой удобным для AI-assisted разработки

Для проекта это особенно важно, потому что патчи часто готовятся по архиву и измененным файлам, а не через постоянный живой shared runtime.

Поэтому фиксируются следующие правила:

1. **Минимум скрытой магии.**
   Dev flow должен работать через явные команды, а не через труднообъяснимую оркестрацию.

2. **Предсказуемые порты и файлы.**
   `5432`, `18080`, `5173`, `.env.example`, `docker-compose.dev.yml`.

3. **Docker только там, где он реально помогает.**
   На текущем этапе это прежде всего PostgreSQL.

4. **Backend и frontend остаются простыми отдельными artifacts.**
   Это облегчает анализ, патчи и ручную проверку.

5. **Документация должна описывать реальный workflow, а не желаемый когда-нибудь.**
   То есть current deployment docs обязаны отражать текущий auth/session baseline, реальные env-переменные и реальные команды запуска.

---

## 15. Короткий итог

Для проекта фиксируется **простая, self-host-friendly и AI-friendly deployment-модель**:
- backend как один release/service;
- PostgreSQL как отдельная база;
- frontend как static web artifact;
- local dev через native backend/frontend + Docker Compose для БД;
- self-host alpha без обязательного relay;
- relay/p2p как отдельная будущая transport-эволюция;
- `.env` контракт и runtime boundaries фиксируются явно, без скрытых зависимостей.

Это дает достаточно устойчивую основу для ближайших этапов, не притворяясь, что инфраструктурная часть уже доведена до окончательного production handbook.
