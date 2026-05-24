# devbootstrap v2 release gates plan

- Статус: Draft v2 plan; Phase 1–7 implemented in `tools/devbootstrap.py`
- Дата: 2026-05-24
- Назначение: спланировать развитие `tools/devbootstrap.py` до режима «одной волшебной кнопки» для проверки блока `7. Testing and release gates` из `docs/product/v1-remaining-checklist.md`.

---

## 1. Короткая формула

Devbootstrap v2 должен дать одну команду, которая:

```bash
python tools/devbootstrap.py release-gates
```

делает полный прогон release-gates, **не останавливается после первого падения**, сохраняет краткий глобальный итог и собирает микроархив со всеми детальными логами и отчетами.

Целевой пользовательский сценарий:

```text
запустил одну команду
→ получил один понятный summary
→ получил один маленький zip-архив с логами
→ передал архив на разбор человеку или AI
→ не собирал руками куски вывода из терминала
```

---

## 2. Почему v1 smoke/up недостаточно

В v1 уже есть полезные команды:

```bash
python tools/devbootstrap.py up --smoke-level quick|standard|full
python tools/devbootstrap.py smoke --level quick|standard|full
```

Но для release-gates этого недостаточно по нескольким причинам.

1. `smoke` сейчас работает как последовательный gate и обычно short-circuit-ит после падения зависимого шага.
2. `up --smoke-level ...` проверяет запуск runtime и выбранный smoke level, но не является полной матрицей release checks.
3. `cargo test` в обычном виде может завершиться `ok`, хотя DB integration tests были `ignored` из-за отсутствующего `TEST_DATABASE_URL` или `DATABASE_URL`.
4. Browser smoke может падать по infrastructure-причине, например отсутствуют скачанные Playwright browser binaries.
5. Человеку неудобно вручную собирать stdout/stderr, markdown/json-отчеты, browser artifacts и итоговую классификацию.
6. При падении раннего шага важно всё равно проверить независимые зоны: frontend build/tests, Rust syntax/tests, browser prerequisites, README/release docs.

Devbootstrap v2 не должен заменять существующие команды. Он должен стать надстройкой-агрегатором над ними.

---

## 3. Цель v2

Цель v2: добавить release-gates runner, который покрывает весь блок `7. Testing and release gates`.

Минимальный целевой интерфейс:

```bash
python tools/devbootstrap.py release-gates
```

Полезные флаги:

```bash
python tools/devbootstrap.py release-gates --with-startup
python tools/devbootstrap.py release-gates --allow-dev-db-write
python tools/devbootstrap.py release-gates --install-playwright-browsers
python tools/devbootstrap.py release-gates --timeout-seconds 900
python tools/devbootstrap.py release-gates --output-dir .dev-bootstrap/runs/manual-release-gates
python tools/devbootstrap.py release-gates --json
```

Ожидаемое поведение по умолчанию:

- `keep-going=true`: не останавливаться после первого failed gate;
- `--dry-run` проверяет контракт bundle и планируемую матрицу gates, но не должен требовать установленный `node_modules`, скачанные Playwright browsers или live test DB;
- не делать destructive DB reset;
- не удалять Docker volumes;
- не убивать foreign processes;
- не перезаписывать env без явного подтверждения;
- маскировать secrets в логах;
- сохранять максимум диагностической информации.

---

## 4. Матрица gates

### 4.1. Core backend gates

| Gate | CWD | Команда | Цель |
|---|---|---|---|
| `backend_cargo_test_default` | `backend` | `cargo test` | Проверить обычный Rust test profile. |
| `backend_cargo_test_db_ignored` | `backend` | `cargo test -- --include-ignored` | Принудительно выполнить DB integration tests, если есть DB URL. |
| `backend_python_smoke_first` | `backend` | `python tests/smoke_core_api.py` | Проверить live backend API happy-path/negative cases. |
| `backend_python_smoke_second` | `backend` | `python tests/smoke_core_api.py` | Проверить идемпотентность повторного smoke-прогона. |

Для `backend_cargo_test_db_ignored` runner должен подготовить окружение:

1. если `TEST_DATABASE_URL` уже задан — использовать его;
2. иначе если `DATABASE__URL` есть в `backend/.env` — временно передать его как `TEST_DATABASE_URL`;
3. иначе пометить gate как `skipped_prerequisite`, но явно объяснить причину.

Важно: `skipped` для DB integration tests в release-gates не должен выглядеть как полноценный pass.

### 4.2. Frontend gates

| Gate | CWD | Команда | Цель |
|---|---|---|---|
| `frontend_build` | `frontend` | `npm run build` | Проверить TypeScript/Vite production build. |
| `frontend_unit_integration` | `frontend` | `npm run test:run` | Проверить Vitest unit/integration tests. |
| `frontend_browser_smoke` | `frontend` | `npm run test:browser` | Проверить Playwright browser smoke. |

Для browser smoke нужен отдельный prerequisite detector:

- проверить наличие Playwright package;
- проверить наличие ожидаемых browser binaries;
- если binaries отсутствуют и передан `--install-playwright-browsers` — выполнить `npx playwright install` отдельным gate/log;
- если binaries отсутствуют и флаг не передан — пометить `frontend_browser_smoke` как `infra_failed` / `browser_smoke_prerequisite` с подсказкой.

### 4.3. Real backend browser path

Текущий browser smoke может быть mocked. Для release-gates нужен отдельный gate:

```text
browser_real_backend_path
```

Требование к будущему e2e-сценарию:

- не использовать `page.route` mocks для core API;
- работать с живым backend на `VITE_API_BASE_URL`;
- проходить минимальный путь: sign-up/sign-in → workspace → board → column → card → card details;
- явно проверять, что Network calls идут в `http://127.0.0.1:18080/api/v1/...` или в configured API base;
- сохранять Playwright trace/screenshot/video при падении, если это включено конфигом.

До появления такого spec gate должен честно возвращать `not_implemented`, а не маскироваться под pass.

### 4.4. Clean-machine quickstart gate

Этот gate тяжелее остальных, поэтому его стоит сделать optional:

```bash
python tools/devbootstrap.py release-gates --include-clean-machine
```

Идея:

1. создать временный каталог;
2. скопировать или распаковать проект без `.git`, `.dev-bootstrap`, `target`, `node_modules`, `dist`, `build`;
3. выполнить safe sequence:

```bash
python tools/devbootstrap.py self-check
python tools/devbootstrap.py diagnose
python tools/devbootstrap.py plan
python tools/devbootstrap.py prepare-env
python tools/devbootstrap.py up --dry-run --smoke-level quick
```

Реальный `up` на clean-machine можно оставить отдельным explicit-флагом, потому что он запускает runtime и может конфликтовать с уже поднятым основным проектом.

### 4.5. Documentation gates

| Gate | Проверка | Цель |
|---|---|---|
| `readme_startup_commands_present` | README содержит актуальные devbootstrap команды | README соответствует реальному запуску. |
| `release_notes_known_limitations_present` | Release notes / known limitations существуют или явно отмечены как missing | Не выпускать v1 без честных ограничений. |
| `v1_remaining_checklist_release_gates_present` | `docs/product/v1-remaining-checklist.md` содержит Testing and release gates | Gate matrix синхронизирована с продуктовым checklist. |

Документационные gates не должны быть сложным markdown-linter. Их цель — ловить отсутствие критичных release docs.

---

## 5. Report bundle contract

Каждый запуск должен создавать run directory:

```text
.dev-bootstrap/runs/YYYYMMDD_HHMMSS_release-gates/
  release-gates.md
  release-gates.json
  summary.txt
  logs/
    01_self_check.log
    02_diagnose.log
    03_backend_cargo_test_default.log
    04_backend_cargo_test_db_ignored.log
    05_backend_python_smoke_first.log
    06_backend_python_smoke_second.log
    07_frontend_build.log
    08_frontend_unit_integration.log
    09_playwright_install.log
    10_frontend_browser_smoke.log
    11_browser_real_backend_path.log
    12_docs_gates.log
  reports/
    self-check/report.md
    diagnose/report.md
    smoke/report.md
  artifacts/
    playwright/
      test-results/...          # only if present and reasonably small
  release-gates_YYYYMMDD_HHMMSS.zip
```

Микроархив должен включать:

- `release-gates.md`;
- `release-gates.json`;
- `summary.txt`;
- все `logs/*.log`;
- вложенные devbootstrap reports, если команда их создала;
- Playwright error context / screenshots / traces, если они есть;
- никаких `node_modules`, `target`, `dist`, `build`, `__pycache__`, `.pytest_cache`, `.env`, secrets.

Пример `summary.txt`:

```text
# release-gates summary

Overall: failed
Started: 2026-05-24T11:00:00Z
Finished: 2026-05-24T11:05:30Z

> cargo test
status: partial_pass
reason: command exited 0, but DB integration tests were ignored
log: logs/03_backend_cargo_test_default.log

> python tests/smoke_core_api.py
status: failed
reason: ACCESS_TOKEN local/global smoke bug
log: logs/05_backend_python_smoke_first.log

> npm run build
status: ok
log: logs/07_frontend_build.log

> npm run test:browser
status: infra_failed
reason: Playwright browser executable is missing; run npx playwright install
log: logs/10_frontend_browser_smoke.log
```

---

## 6. JSON contract

`release-gates.json` должен быть машинно читаемым:

```json
{
  "schemaVersion": 1,
  "command": "release-gates",
  "toolVersion": "2.0.0-draft",
  "generatedAt": "2026-05-24T11:00:00Z",
  "projectRoot": "/path/to/project",
  "overallStatus": "failed",
  "classification": "release_gates_failed",
  "archivePath": ".dev-bootstrap/runs/.../release-gates_...zip",
  "gates": [
    {
      "name": "frontend_build",
      "command": ["npm", "run", "build"],
      "cwd": "frontend",
      "status": "ok",
      "classification": "ok",
      "returncode": 0,
      "durationMs": 901,
      "logPath": "logs/07_frontend_build.log"
    }
  ],
  "findings": [
    {
      "severity": "fail",
      "code": "backend_smoke_access_token_scope_bug",
      "message": "backend Python smoke failed because ACCESS_TOKEN is treated as a local variable inside main()."
    }
  ],
  "nextActions": [
    "Fix backend/tests/smoke_core_api.py ACCESS_TOKEN scope and rerun release-gates."
  ]
}
```

---

## 7. Classification rules

Suggested statuses:

| Status | Meaning |
|---|---|
| `ok` | Command passed and post-processing found no warning condition. |
| `partial_pass` | Command returned 0 but output shows hidden skipped/ignored critical checks. |
| `failed` | Product/code/test failure. |
| `infra_failed` | Local prerequisite failure: browser binary missing, command unavailable, service unreachable. |
| `skipped_prerequisite` | Gate could not run because required environment was explicitly absent. |
| `not_implemented` | Gate is part of v1 checklist but no automated implementation exists yet. |
| `timeout` | Gate exceeded timeout. |

Overall status rules:

- all gates `ok` → `ok`;
- any `failed` → `failed`;
- only infra failures → `infra_failed`;
- any skipped required prerequisite or `not_implemented` gate → `incomplete`;
- any `partial_pass` without hard failures → `partial_pass`;

---

## 8. Implementation phases

### Phase 1 — Generic keep-going gate runner

Status in this patch: **implemented as the release-gates scaffold**.

Implemented internal primitives:

- `GateSpec`;
- `GateResult`;
- `ReleaseGatesResult`;
- `run_gate_process_step(...)`;
- common log writer;
- stdout/stderr capture;
- duration, return code and timeout handling;
- output classifiers for `ok`, `partial_pass`, `failed`, `infra_failed`, `timeout` and `not_implemented`.

Backend/frontend gate matrix is implemented in Phase 3/4; Phase 5/6/7 add the real-backend browser gate, docs gates, optional clean-machine quickstart and self-check fixtures.

Original Phase 1 target:


- `GateSpec`;
- `GateResult`;
- `run_gate_process_step(...)`;
- common log writer;
- stdout/stderr capture;
- duration, return code and timeout handling;
- output classifiers.

Acceptance:

```bash
python -c "import ast,pathlib; ast.parse(pathlib.Path('tools/devbootstrap.py').read_text(encoding='utf-8'))"
python tools/devbootstrap.py self-check --no-write-report
python tools/devbootstrap.py release-gates --dry-run
```

### Phase 2 — Release-gates command and summary bundle

Status in this patch: **implemented as a runnable command and report-bundle contract**.

Implemented:

- `python tools/devbootstrap.py release-gates`;
- `--dry-run` mode for safe plan/report generation;
- optional `--output-dir`;
- `release-gates.md`;
- `release-gates.json`;
- `summary.txt`;
- `logs/*.log`;
- `release-gates_YYYYMMDD_HHMMSS.zip`;
- archive exclusion rules for `__pycache__`, `.pytest_cache`, `node_modules`, `target`, `dist`, `build`, `.env*`, local DB files and bytecode.

The command now runs the implemented scaffold, backend and frontend gates. It still includes explicit `not_implemented` gates for Phase 5/6, so it cannot be mistaken for a complete v1 release pass until the real-backend browser path, clean-machine and docs gates are implemented.

Original Phase 2 target:


```bash
python tools/devbootstrap.py release-gates
```

Implement:

- run directory;
- `release-gates.md`;
- `release-gates.json`;
- `summary.txt`;
- zip archive creation;
- archive excludes.

Acceptance:

- archive exists;
- archive contains summary/logs/json;
- archive does not contain forbidden directories/files.

### Phase 3 — Backend gates

Status in this patch: **implemented**.

Implemented:

- `backend_cargo_test_default` → `cargo test`;
- `backend_cargo_test_db_ignored` → `cargo test -- --include-ignored`;
- DB env propagation for ignored tests: `TEST_DATABASE_URL`, or `DATABASE_URL`, or backend env `TEST_DATABASE_URL` / `DATABASE__URL` / `DATABASE_URL` mapped to `TEST_DATABASE_URL`;
- explicit `skipped_prerequisite` when no DB URL can be found for DB integration tests;
- `backend_python_smoke_first`;
- `backend_python_smoke_second` for idempotency;
- smoke write guard: smoke runs when `TEST_DATABASE_URL` is explicitly present or `--allow-dev-db-write` is passed; otherwise it is reported as `skipped_prerequisite`;
- keep-going semantics: backend failures/skips do not prevent frontend gates from running;
- exact command logs in `logs/*.log`.

Acceptance:

- ignored DB tests are detected and classified;
- smoke failures do not prevent frontend gates from running;
- logs point to exact command output.

### Phase 4 — Frontend gates

Status in this patch: **implemented**.

Implemented:

- `frontend_build` → `npm run build`;
- `frontend_unit_integration` → `npm run test:run`;
- Playwright package/browser prerequisite detector;
- `frontend_browser_smoke` → `npm run test:browser`;
- optional `playwright_install` → `npx playwright install` only when `--install-playwright-browsers` is explicitly passed and browser binaries are missing;
- missing Playwright package/browser state is classified as `browser_smoke_prerequisite` / `infra_failed`;
- keep-going semantics preserve build/unit results even when browser smoke is skipped or fails.

Acceptance:

- missing browser executable is classified as `browser_smoke_prerequisite` / `infra_failed`;
- successful build/unit results are preserved even if browser smoke fails.

### Phase 5 — Real backend browser path gate

Status in this patch: **implemented as a dedicated opt-in real-backend browser gate**.

Implemented:

- separate Playwright spec `frontend/e2e/smoke/real-backend.smoke.spec.ts` without `page.route` API mocks;
- npm script `npm run test:browser:real-backend`;
- release-gates flag `--include-real-backend-browser`;
- real-backend browser write guard: the gate requires `TEST_DATABASE_URL` or explicit `--allow-dev-db-write`;
- report details that mocked browser smoke does not satisfy `browser_real_backend_path`;
- if the spec is absent in a future branch, the gate returns `not_implemented` rather than silently passing.

Acceptance:

- mocked browser smoke cannot accidentally close the real-backend checklist item;
- report explains which browser path was checked;
- write-capable browser path is explicit and cannot mutate a dev DB accidentally.

### Phase 6 — Clean-machine and docs gates

Status in this patch: **implemented**.

Implemented:

- optional `--include-clean-machine` gate that copies the project to a temporary clean-machine directory while excluding `.git`, `.dev-bootstrap`, `node_modules`, `target`, `dist`, `build`, `__pycache__`, `.pytest_cache`, local env files and bytecode;
- clean-machine safe sequence:

```bash
python tools/devbootstrap.py self-check --no-write-report
python tools/devbootstrap.py diagnose --no-write-report
python tools/devbootstrap.py plan --no-write-report
python tools/devbootstrap.py prepare-env --no-write-report
python tools/devbootstrap.py up --dry-run --smoke-level quick
```

- static docs gate `readme_startup_commands_present`;
- static docs gate `release_notes_known_limitations_present`;
- static docs gate `v1_remaining_checklist_release_gates_present`;
- `docs/product/v1-known-limitations.md` as the current known limitations boundary for v1/beta release review.

Acceptance:

- clean-machine gate can be enabled explicitly;
- README/release notes gaps are visible in report;
- docs gates write their own `logs/*.log` entries into the release-gates bundle.

### Phase 7 — Self-check fixtures for v2

Status in this patch: **implemented**.

Implemented pure stdlib self-check fixtures for:

- release-gates JSON envelope;
- summary rendering;
- archive exclusion rules;
- ignored-test output classifier;
- Playwright missing-browser classifier;
- keep-going behavior after a failed prerequisite.

Acceptance:

```bash
PYTHONDONTWRITEBYTECODE=1 python tools/devbootstrap.py self-check --no-write-report
```

passes without creating `__pycache__` or `.pytest_cache`.

---

## 9. Known issues discovered during current manual gate run

The current manual run surfaced issues that v2 should make obvious in one report.

1. `cargo test` can be green while DB integration tests are ignored.
2. `backend/tests/smoke_core_api.py` currently fails on `ACCESS_TOKEN` local/global scope inside `main()`.
3. `npm run build` and `npm run test:run` can pass independently and should still be reported even when backend smoke fails.
4. `npm run test:browser` can fail because Playwright browser binaries are missing; this is an infra prerequisite, not necessarily an app regression.
5. A mocked browser smoke is not the same as real backend browser path verification.
6. Early DB startup problems, such as a reachable PostgreSQL server with a missing configured database, should remain separately classified as bootstrap infra issues.

---

## 10. Risks and boundaries

Risks:

- one command may become too magical if it silently installs browsers, creates databases or mutates env;
- release-gates archive may accidentally grow large if it includes Playwright traces/videos without limits;
- smoke idempotency can still be affected by shared dev DB state;
- clean-machine gate can be slow and platform-sensitive.

Boundaries:

- no destructive DB reset by default;
- no automatic killing of foreign processes;
- no implicit global package installation;
- no secrets in reports or archive;
- no `__pycache__`, `.pytest_cache`, `target`, `node_modules`, `dist`, `build` in report archive.

---

## 11. Done criteria for v2 release-gates

Devbootstrap v2 release-gates can be considered ready when:

- one command runs all configured gates with keep-going semantics;
- failed backend smoke does not suppress frontend build/unit/browser diagnostics;
- ignored Rust DB integration tests are detected as `partial_pass` or fixed by env propagation;
- Playwright missing-browser state is classified cleanly;
- a zip report bundle is created every time unless explicitly disabled;
- the bundle is small enough to share in a chat;
- the bundle contains enough information to diagnose failures without asking the user to paste five separate terminal outputs;
- `self-check` covers the new report/archive/classifier contracts;
- docs explain how to run the command and how to interpret the archive.
