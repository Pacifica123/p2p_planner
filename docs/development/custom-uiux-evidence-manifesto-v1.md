# Манифест отказа от Playwright и перехода к кастомному UI/UX Evidence Runner v1

- Статус: Draft v1
- Дата: 2026-05-28
- Назначение: зафиксировать новую инженерную веху после Phase 0–7 release stabilization: заменить Playwright-зависимый browser smoke слой на собственный легковесный механизм доказательства UI/UX-жизнеспособности.

---

## 1. Почему эта веха появилась

Стабилизационная программа Phase 0–7 строилась вокруг простой идеи: перестать лечить отдельные stacktrace и начать собирать доказательства. Она сработала: Windows/MSVC linker шум был отделен от реального backend состояния, frontend dependency blocker был снят, managed DB и runtime были выведены в отдельные безопасные профили, а каждый run получил ledgers, confidence score и remediation bundle.

Но после этого проявился новый системный дефект: Playwright сам стал источником release-noise.

Сначала browser smoke был заблокирован отсутствующим browser revision. Затем был добавлен fix, который должен был принудительно запускать install gate при `--install-playwright-browsers`. Затем сам install начал падать по timeout, а итоговый релизный сигнал снова стал зависеть не от приложения, а от тяжелого внешнего browser cache / download / revision lifecycle.

Это означает, что проблема уже не в одном missing executable. Проблема глубже:

```text
Мы хотели проверить, что пользователь может открыть приложение.
Но начали проверять, способен ли Playwright скачать и синхронизировать свой Chromium revision.
```

Такой слой полезен для крупных e2e suites, но он слишком тяжел для нашей роли `release-gates diagnostic`: дать быстрый, воспроизводимый, объяснимый сигнал о том, жив ли web UI.

---

## 2. Решение в одну фразу

Мы не переписываем Playwright.

Мы строим **UI/UX Evidence Runner** — узкий, легковесный, доказательный runner, который проверяет только те пользовательские свойства, которые нужны нашему проекту перед v1:

```text
open app
mount JS runtime
observe route
find actionable controls
perform minimal user scenario
verify form/network/state effects
collect console/network/DOM/storage evidence
```

Цель не в том, чтобы сделать универсальный browser automation framework. Цель — сделать наш release-gate менее зависимым от чужого тяжелого e2e стека и более связанным с рисками конкретного продукта.

---

## 3. Что именно должен заменить кастомный слой

Playwright в проекте сейчас пытается закрыть такие вопросы:

1. Страница реально открывается в браузере.
2. JS runtime не падает на boot.
3. Router не ломает entry path.
4. Основной container/root не пустой.
5. Кнопка или ссылка существует и доступна пользователю.
6. Форма принимает ввод и отправляет действие.
7. Mocked или real backend path не расходится с frontend ожиданиями.
8. `localStorage` / `sessionStorage` / session bootstrap ведут себя ожидаемо.
9. Browser smoke падает на `pageerror`, а не молча пропускает white screen.
10. Итоговый run дает артефакты, которые можно прислать на анализ.

Кастомный runner обязан покрыть эти цели настолько полно, насколько это возможно без превращения в новый Playwright.

---

## 4. Что не нужно строить

Нельзя превратить эту веху в переписывание универсального e2e-фреймворка.

Запрещенные направления на v1 runner:

- полноценный selector engine уровня Playwright;
- сложные auto-wait heuristics;
- трассировка всех browser protocols;
- pixel-perfect visual regression;
- cross-browser matrix;
- бесконечные retries, скрывающие flaky поведение;
- собственный пакетный менеджер браузеров;
- магическая установка системных зависимостей;
- универсальный DSL для всех будущих UI-сценариев.

Runner должен быть маленьким и скучным. Его сила — не в богатстве API, а в том, что он проверяет ровно наш критический путь и оставляет понятные артефакты.

---

## 5. Техническая опора: системный браузер вместо bundled browser revision

Главная архитектурная развилка:

```text
Playwright model:
  npm package -> browser revision cache -> download -> run browser

Custom runner model:
  locate installed browser -> launch isolated temp profile -> collect evidence
```

Поддерживаемые browser candidates:

- `chromium`;
- `chromium-browser`;
- `google-chrome`;
- `google-chrome-stable`;
- `brave-browser`;
- в будущем при необходимости `msedge`.

Если системного браузера нет, gate должен честно вернуть `browser_executable_missing` и дать одну понятную next action: установить системный Chromium/Chrome штатным способом ОС.

Это принципиально легче, чем управлять Playwright revision cache:

- нет npm-managed browser binary;
- нет hidden cache drift;
- нет `chromium_headless_shell-XXXX` mismatch;
- нет отдельного `npx playwright install` lifecycle;
- меньше сетевых side effects внутри release-gates.

---

## 6. Возможен ли подход вообще без браузера

Часть целей можно закрыть без браузера:

| Проверка | Можно без браузера? | Инструмент |
|---|---:|---|
| TypeScript compile | Да | `tsc -b` |
| Vite build | Да | `vite build` |
| Unit/integration UI logic | Да | Vitest + Testing Library + jsdom |
| API contract shape | Да | fixtures / OpenAPI checks |
| Route table sanity | Частично | static/import analysis |
| Form state reducer | Да | unit/integration tests |
| localStorage helper semantics | Да | jsdom/unit tests |
| Real JS bundle boot in browser engine | Нет | browser required |
| Real browser console errors | Нет | browser required |
| Real navigation/click/form event through DOM/browser APIs | Почти нет | browser required |
| Real CORS/fetch/browser security behavior | Нет | browser required |

Вывод: полностью без браузера нельзя доказать, что пользователь реально может открыть UI и пройти сценарий. Но можно резко сузить браузерную часть: не браузер как гигантский e2e framework, а браузер как runtime probe.

Идеальная модель:

```text
static/build/contract/jsdom layers catch most regressions cheaply;
custom browser evidence runner proves the thin real-browser vertical slice;
real-backend mode proves integration only when safe DB/runtime are available.
```

---

## 7. Минимальная архитектура UI/UX Evidence Runner

### 7.1. CLI surface

Предлагаемая команда:

```bash
python tools/uiux_probe.py --base-url http://127.0.0.1:5173/ --scenario mocked-auth-workspace
```

Встроенный release-gates gate:

```text
frontend_uiux_probe
```

Возможные режимы:

```text
mocked-ui
real-backend
readonly-boot
storage-state
```

### 7.2. Browser discovery

Runner должен:

1. найти browser executable;
2. записать candidate list в report;
3. не скачивать браузер;
4. не менять проектные файлы;
5. запускать browser с временным `--user-data-dir`;
6. удалять temp profile после прогона;
7. оставлять путь к artifacts.

### 7.3. Runtime collection

Минимальные артефакты:

- `uiux-probe-report.json`;
- `uiux-probe-report.md`;
- `dom-after-boot.html`;
- `console.log`;
- `network.jsonl` или упрощенный fetch log;
- `storage-before.json`;
- `storage-after.json`;
- `route-history.json`;
- optional screenshot, если системный браузер позволяет.

### 7.4. Scenario DSL

DSL должен быть очень маленьким:

```text
visit(path)
waitForText(text, timeout)
click(selector_or_testid)
type(selector_or_testid, value)
assertText(text)
assertRoute(path_or_pattern)
assertStorage(key, predicate)
assertNoConsoleErrors()
assertNoUnhandledRejections()
```

Желательно опираться на `data-testid` / стабильные product markers, а не на CSS layout.

### 7.5. Evidence-first failure model

Каждое падение должно классифицироваться:

| Failure | Meaning |
|---|---|
| `browser_executable_missing` | Нет системного браузера. Infra prerequisite, не product bug. |
| `browser_launch_failed` | Браузер найден, но не стартует. Infra/runtime issue. |
| `frontend_unreachable` | Dev server не отвечает. Runtime issue. |
| `ui_boot_timeout` | Страница открылась, app marker не появился. Product/runtime issue. |
| `js_runtime_error` | Browser console/page error. Product issue до доказательства обратного. |
| `route_assertion_failed` | Router/navigation mismatch. Product/frontend issue. |
| `control_missing` | Кнопка/форма не найдена. Product/frontend issue. |
| `control_not_actionable` | Элемент есть, но disabled/hidden/covered. Product/frontend issue. |
| `form_submit_failed` | UI action не приводит к ожидаемому effect. Product/integration issue. |
| `storage_state_failed` | local/session state не соответствует ожиданиям. Product/state issue. |
| `network_contract_failed` | frontend/backend не договорились о payload/status. Integration issue. |

---

## 8. Как проверять “кнопка есть и доступна пользователю” без Playwright

Минимальный достаточный подход:

1. сценарий ищет элемент по `data-testid`, role-like атрибутам или тексту;
2. browser-side JS проверяет:
   - элемент существует;
   - `offsetParent` / bounding rect не пустой;
   - `disabled` отсутствует;
   - `aria-disabled` не `true`;
   - computed style не `display:none`, `visibility:hidden`, `pointer-events:none`;
   - центр bounding box попадает в viewport;
   - `document.elementFromPoint(center)` совпадает с элементом или его потомком;
3. runner кликает через browser-side event only after actionability check;
4. после клика проверяется route/text/network/storage effect.

Это не универсальная модель actionability, но для нашего MVP достаточно. Главное — не притворяться, что это Playwright. Это осознанный ограниченный probe.

---

## 9. Как проверять JS runtime и console failures

Runner должен собирать:

- `window.onerror`;
- `unhandledrejection`;
- patched `console.error`;
- visible Vite/React fatal overlay markers;
- failed dynamic import markers;
- failed fetch summary.

Критерий:

```text
Любой uncaught runtime error в boot/smoke path = blocker,
если сценарий явно не пометил его как accepted known limitation.
```

---

## 10. Как проверять форму и backend interaction

Для mocked-ui режима:

- runner или frontend test harness предоставляет deterministic mock API;
- сценарий вводит данные;
- нажимает submit;
- проверяет DOM effect и local state.

Для real-backend режима:

- требуется managed runtime;
- требуется write-safe DB;
- runner получает `BASE_URL` и `API_BASE_URL` из release-gates runtime state;
- сценарий создает disposable user/workspace/card;
- cleanup выполняется API/smoke layer или disposable DB retention policy.

Real-backend UI probe нельзя запускать против общей dev-БД без явного consent.

---

## 11. Как проверять localStorage/session/state

Runner должен уметь выполнить browser-side snapshot:

```js
Object.fromEntries(Object.entries(localStorage))
Object.fromEntries(Object.entries(sessionStorage))
```

И сравнить:

- before/after boot;
- before/after login/mock-auth;
- before/after form submit;
- before/after reload.

Для local-first future layer отдельно понадобятся:

- pending ops count;
- last sync status marker;
- offline/online badge state;
- retry/failure marker;
- durable cache hydration after reload.

Но v1 runner не должен сразу покрывать весь future local-first runtime. Он должен оставить места расширения.

---

## 12. Что убрать из проекта при окончательном отказе от Playwright

Удаление должно быть отдельной миграционной фазой, только после того как custom runner пройдет acceptance parity.

Список мест, которые надо проверить:

### Frontend

- `frontend/package.json`:
  - удалить `@playwright/test` из `devDependencies`;
  - заменить `test:browser`, `test:browser:headed`, `test:browser:real-backend` на custom probe scripts или убрать;
- `frontend/package-lock.json`:
  - пересобрать lock без Playwright;
- `frontend/e2e/`:
  - перенести сценарии в custom runner или удалить;
- `playwright.config.*`, если появится/есть;
- traces, screenshots, reports, browser artifacts.

### Devbootstrap

- убрать `playwright_install` gate;
- убрать `--install-playwright-browsers`;
- заменить `frontend_browser_smoke` на `frontend_uiux_probe`;
- заменить classifiers `playwright_*` на `uiux_probe_*`;
- обновить self-check fixtures;
- обновить remediation next-actions;
- обновить archive/bundle artifact expectations.

### Docs

- `docs/architecture/testing-application-guide-v1.md`;
- `docs/architecture/testing-strategy-v1.md`;
- `docs/architecture/testing-pyramid-v1.md`;
- `docs/product/v1-remaining-checklist.md`;
- `docs/development/release-stabilization-problem-ledger.md`;
- README command examples.

### CI / future automation

Если появится CI:

- убрать Playwright browser install step;
- добавить system browser prerequisite или container image contract;
- upload custom UI/UX evidence artifacts.

---

## 13. Миграционный план

### Phase UIX-0 — Manifest and scope lock

Текущий документ. Цель: не начать хаотично удалять Playwright, пока не определены replacement goals.

Acceptance:

- есть манифест;
- есть ledger entries;
- docs ясно говорят, что Playwright считается временным legacy browser-smoke layer.

### Phase UIX-1 — Browser executable discovery probe

Добавить отдельную команду, которая только находит системный браузер и пишет report.

Acceptance:

- Linux/Windows discovery работает;
- отсутствие браузера классифицируется как prerequisite;
- нет network download.

### Phase UIX-2 — Boot evidence probe

Открыть frontend URL в системном headless browser и собрать DOM/console/storage.

Acceptance:

- white screen ловится;
- JS boot error ловится;
- route/root marker проверяется;
- artifacts входят в release-gates bundle.

### Phase UIX-3 — Mocked critical UI scenario

Перенести текущий mocked browser smoke смысл из Playwright в custom runner.

Acceptance:

- auth/workspace mocked path проходит;
- button/actionability/form checks работают;
- localStorage/session effects проверяются;
- Playwright больше не нужен для mocked UI smoke.

### Phase UIX-4 — Real-backend UI scenario

Подключить custom runner к managed runtime и write-safe DB.

Acceptance:

- сценарий запускается только при safe DB/runtime;
- создает disposable entities;
- проверяет network/API effect;
- artifacts связываются с runtime-state.

### Phase UIX-5 — Release-gates integration

Заменить gates:

```text
playwright_install -> removed
frontend_browser_smoke -> frontend_uiux_probe
browser_real_backend_path -> uiux_real_backend_probe
```

Acceptance:

- release confidence score учитывает новый runner;
- old Playwright failures больше не появляются;
- regression memory использует новые IDs.

### Phase UIX-6 — Playwright removal

Удалить Playwright из frontend deps/scripts/docs/devbootstrap.

Acceptance:

- `grep -R playwright` возвращает только changelog/legacy notes;
- `npm ci` не тянет Playwright;
- release-gates не содержит Playwright install/browser cache logic;
- docs command examples обновлены.

### Phase UIX-7 — Repeatability and clean-machine proof

Прогнать custom UI/UX evidence runner:

- fresh checkout;
- dirty workspace;
- managed runtime;
- clean-machine dry profile;
- repeated run.

Acceptance:

- no hidden browser downloads;
- artifacts complete;
- runner failures classified;
- confidence gate больше не зависит от Playwright.

---

## 14. Риски кастомного подхода

| Риск | Как ограничить |
|---|---|
| Начнем писать новый Playwright | Жесткий запрет на универсальный framework scope. Только project-specific probes. |
| Системный browser отличается у пользователей | Discovery report + минимальная supported browser matrix. |
| Headless flags отличаются по ОС | Сначала Linux/Chromium, затем Windows/Chrome; все flags фиксировать в report. |
| Недостаточно real-user fidelity | Использовать custom runner только для критического пути, остальные сценарии держать в unit/integration/contract. |
| Сложно кликать/вводить без Playwright | Ограниченный actionability алгоритм + stable `data-testid`. |
| Browser protocol implementation расползется | Не делать full CDP client, пока dump/injection approach достаточен; если нужен CDP — только минимальные методы. |
| Удалим Playwright слишком рано | Playwright removal только после acceptance parity. |
| Docs снова разойдутся с командами | Включить docs command gate в migration acceptance. |

---

## 15. Новая философия UI/UX testing

Мы больше не принимаем формулу:

```text
E2E framework installed = browser confidence
```

Новая формула:

```text
Evidence collected from real browser runtime + explicit scenario artifacts = browser confidence
```

Для нашего проекта важнее не престиж e2e framework, а доказуемость:

- что было открыто;
- каким браузером;
- на каком URL;
- какие console errors были;
- какой DOM получился;
- какие действия выполнены;
- какие network/storage effects возникли;
- почему failure классифицирован именно так.

Если runner маленький, но дает эти ответы, он лучше для v1 release-gates, чем огромный dependency, который сам регулярно становится blocker.

---

## 16. Итог

Playwright не объявляется плохим инструментом вообще. Он объявляется неподходящим как обязательный фундамент нашего локального release-gates слоя на текущем этапе проекта.

Мы заменяем его не потому, что хотим меньше тестов, а потому что хотим более чистый сигнал:

```text
Меньше магии.
Меньше download/cache/revision lifecycle.
Больше прямых доказательств о нашем UI.
```

Эта веха должна завершиться тем, что проверка пользовательского пути станет:

- легче;
- быстрее;
- объяснимее;
- менее сетезависимой;
- менее flaky;
- лучше встроенной в release-gates ledgers;
- достаточно реалистичной, чтобы не пропустить white screen, broken router, broken form, broken session/storage или frontend/backend contract mismatch.
