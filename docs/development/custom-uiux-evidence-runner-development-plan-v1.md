# Custom UI/UX Evidence Runner development plan v1

- Статус: canonical implementation plan for `REL-UIUX-001`
- Дата: 2026-05-28
- Родительские документы:
  - `docs/development/custom-uiux-evidence-manifesto-v1.md`
  - `docs/development/release-stabilization-program-v1.md`
  - `docs/architecture/testing-strategy-v1.md`
  - `docs/dev-bootstrap/devbootstrap-v2-release-gates-plan.md`
- Цель: заменить mandatory Playwright browser smoke на маленький project-specific evidence runner, не потеряв пользовательский release-сигнал.

---

## 1. Decision boundary

Этот план не отменяет общий testing layer. Он закрывает только один больной слой: browser/UI evidence, который сейчас завязан на Playwright и периодически превращается в `REL-BROWSER` blocker вместо доказательства работоспособности продукта.

Новая цель:

```text
release-gates must prove that a user can open the web UI and pass the critical Kanban path,
while failures are classified as app/runtime/scenario/prerequisite issues instead of opaque Playwright setup noise.
```

Ключевое ограничение:

```text
Do not build a general browser automation framework.
Build a small release evidence probe for this project.
```

---

## 2. Relationship map

| Source | What it contributes to this plan |
|---|---|
| `custom-uiux-evidence-manifesto-v1.md` | Core decision, goals to preserve, non-goals, high-level UIX-0..UIX-7 migration outline. |
| `release-stabilization-program-v1.md` | Release loop, `REL-*` taxonomy, confidence score, requirement that red gates become classified evidence. |
| `release-stabilization-problem-ledger.md` | `REL-BROWSER-001..003` remain legacy; `REL-UIUX-001` becomes implementation track. |
| `release-stabilization-profile-side-effects-v1.md` | Browser discovery is read-only; managed runtime/DB are controlled mutators; release-gates must not edit source. |
| `testing-strategy-v1.md` | UI/UX evidence is one layer among build/unit/API/DB/backend smoke; not a replacement for all tests. |
| `testing-application-guide-v1.md` | Current local commands still mention legacy `npm run test:browser`; target command must become `tools/uiux_evidence.py`. |
| `devbootstrap-v2-release-gates-plan.md` | Gate matrix must gain `frontend_uiux_evidence_*` gates and eventually remove Playwright from mandatory gates. |
| `frontend/package.json` | Current `test:browser*` scripts are Playwright-based legacy entry points. |
| `frontend/e2e/smoke/*` | Existing mocked and real-backend scenarios are the behavioral seed for v1 scenarios. |
| `frontend/src/**` | Current UI has accessible labels and headings, but lacks enough stable `data-testid` markers for a non-magical custom runner. |
| Backend smoke/Rust tests | Real-backend UI scenario must reuse managed runtime/test DB safety rather than invent a second E2E environment. |
| Docs archive budget | Evidence artifacts must live under `.dev-bootstrap/runs/**` and be summarized compactly; source docs should not grow into trace dumps. |

Implicit dependencies:

- the runner depends on frontend build/dev server health, but must classify this as `REL-FE` or prerequisite, not `REL-UIUX`;
- real-backend scenarios depend on managed DB/runtime safety, so missing safe DB is `REL-DB` / `skipped_prerequisite`, not UI failure;
- browser executable absence is `REL-ENV` with `uiux_browser_prerequisite` detail, not product failure;
- scenario failures after app boot and satisfied prerequisites are `REL-UIUX` or downstream `REL-FE`/`REL-BE` based on evidence;
- captured storage/network/DOM artifacts are diagnostic evidence and must pass redaction policy before entering shareable bundles.

---

## 3. Current state inventory

### 3.1 Existing good signals to preserve

- Frontend build: `cd frontend && npm run build`.
- Frontend unit/integration: `cd frontend && npm run test:run`.
- Backend Rust/API smoke and managed DB/runtime gates through `tools/devbootstrap.py`.
- Mocked browser smoke behavior: auth boot, mocked sign-in, workspace list rendering.
- Real-backend browser behavior: sign-up, workspace creation, board creation, column creation, card creation, API request evidence.

### 3.2 Existing weak spots

| Weak spot | Impact | Target fix |
|---|---|---|
| Playwright browser revision/cache/install coupling | Infra noise blocks release signal. | Use system browser discovery; never download browsers by default. |
| `frontend_browser_smoke` is coupled to `npm run test:browser` | release-gates still interprets UI evidence through Playwright. | Add first-class `frontend_uiux_evidence_*` gates. |
| Scenario selectors rely heavily on labels/headings/classes | Custom runner would become brittle or too clever. | Add stable `data-testid` markers only for critical user path. |
| Mocking currently uses Playwright route API | Replacement needs another deterministic mock strategy. | Use project-owned mock API server or CDP request fulfill, not Playwright fixtures. |
| Real-backend path requires safe DB/runtime | Unsafe local DB writes would create false confidence/regressions. | Run only under managed DB/runtime or explicit safe target proof. |
| UI evidence artifacts can become huge | Archive bloat and privacy risk. | Keep compact JSON/MD/HTML excerpts; screenshot optional and size-limited. |

---

## 4. Product path scope for v1

### 4.1 Mandatory v1 critical path

The first mandatory real-browser path should prove:

1. app opens and React mounts;
2. auth screen renders;
3. sign-up or sign-in path works;
4. workspace list route renders;
5. workspace can be created or selected;
6. board can be created or opened;
7. column can be created;
8. card can be created;
9. final DOM contains created card;
10. console/runtime has no fatal errors;
11. network evidence includes expected API families;
12. local/session storage evidence is captured and classified.

### 4.2 Optional v1.1 path extensions

These are not required to remove Playwright from mandatory gates, but should be designed as natural follow-up scenarios:

- card details drawer opens and saves a description;
- board activity feed receives the create-card event;
- board/user appearance save path applies visible theme/density evidence;
- export/backup button creates a downloadable JSON response;
- sync/local-first status banner does not spam or fail during the path.

### 4.3 Explicitly out of scope for v1

- cross-browser matrix;
- visual regression snapshots;
- video/tracing subsystem;
- general selector language;
- drag-and-drop scenario automation;
- full comments/checklists/labels coverage;
- a public framework API for arbitrary tests.

---

## 5. Evidence contract

Every run writes a compact evidence directory:

```text
.dev-bootstrap/runs/<run-id>/uiux-evidence/<scenario-name>/
  report.md
  report.json
  dom-final.html
  dom-excerpt.txt
  console.json
  runtime-errors.json
  network.json
  storage-before.json
  storage-after.json
  screenshot.png          optional, size-limited
```

`report.json` minimum schema:

```json
{
  "schemaVersion": 1,
  "tool": "uiux_evidence",
  "scenario": "real-backend-core-flow",
  "status": "ok|failed|skipped_prerequisite|infra_failed",
  "classification": "REL-UIUX|REL-ENV|REL-FE|REL-BE|REL-DB|REL-PROC|REL-SEC",
  "baseUrl": "http://127.0.0.1:5173/",
  "browser": {
    "name": "chromium",
    "executable": "/usr/bin/chromium",
    "version": "..."
  },
  "steps": [
    {
      "name": "create card",
      "status": "ok",
      "evidence": {
        "selector": "[data-testid='create-card-input']",
        "url": "...",
        "domExcerptPath": "dom-excerpt.txt"
      }
    }
  ],
  "console": {
    "fatalCount": 0,
    "warningCount": 0
  },
  "network": {
    "apiRequestCount": 0,
    "failedApiRequestCount": 0
  },
  "storage": {
    "localStorageChanged": true,
    "sessionStorageChanged": false
  },
  "artifacts": {
    "domFinal": "dom-final.html",
    "console": "console.json",
    "network": "network.json"
  }
}
```

Redaction rules:

- redact bearer tokens, refresh/session values, cookies, passwords, emails unless scenario explicitly uses generated `@local.test` identities;
- truncate request/response bodies by default;
- preserve URL path, method, status and timing;
- never store full `.env`, arbitrary localStorage secrets or complete cookies;
- mark `REL-SEC` if redaction cannot be proven.

---

## 6. Runner architecture

### 6.1 File layout

Target source layout:

```text
tools/uiux_evidence.py
  CLI entry point and report orchestration

tools/uiux/
  __init__.py
  browser_discovery.py
  chrome_launcher.py
  cdp_client.py
  evidence.py
  mock_api.py
  scenarios.py
  report.py
  selectors.py
```

Scenario definitions should stay reviewable and small:

```text
tools/uiux/scenarios/
  boot.json
  mocked-core-flow.json
  real-backend-core-flow.json
```

### 6.2 CLI surface

```bash
python -B tools/uiux_evidence.py discover-browser
python -B tools/uiux_evidence.py boot --base-url http://127.0.0.1:5173/
python -B tools/uiux_evidence.py scenario --name mocked-core-flow --base-url http://127.0.0.1:5173/
python -B tools/uiux_evidence.py scenario --name real-backend-core-flow --base-url http://127.0.0.1:5173/ --api-base-url http://127.0.0.1:18080/api/v1
python -B tools/uiux_evidence.py report --input .dev-bootstrap/runs/<run-id>/uiux-evidence
```

### 6.3 Technical stance

Preferred implementation:

- launch an installed Chromium-compatible browser with `--headless=new`, `--remote-debugging-port=0`, temporary user data dir and disabled first-run prompts;
- speak only the small CDP subset needed for Page/Runtime/Network/Log/Input evidence;
- implement direct CSS selector actions through explicit JavaScript snippets, not a general selector engine;
- use temporary project-owned mock API for deterministic mocked scenario unless CDP `Fetch.fulfillRequest` is simpler and stable;
- keep dependencies at Python standard library unless a future decision explicitly accepts one tiny dependency.

Allowed CDP command families for v1:

| Family | Purpose |
|---|---|
| `Page.*` | navigate, load events, screenshot. |
| `Runtime.*` | evaluate exact selector actions and storage snapshots. |
| `Log.*` / `Runtime.exceptionThrown` | console/runtime failure capture. |
| `Network.*` | request/response evidence and failed API calls. |
| `Input.*` | fallback clicks/typing when DOM JS action is insufficient. |

Disallowed in v1:

- general auto-wait engine;
- browser video/tracing by default;
- dependency on Playwright/Puppeteer browser downloads;
- shadow framework with fixtures, reporters and test discovery.

---

## 7. Scenario DSL

The scenario format stays deliberately small:

```json
{
  "schemaVersion": 1,
  "name": "real-backend-core-flow",
  "description": "Create workspace, board, column and card through the real UI.",
  "requires": {
    "browser": true,
    "frontend": true,
    "backend": true,
    "safeDatabase": true
  },
  "steps": [
    { "goto": "/auth" },
    { "assertVisible": "[data-testid='auth-page']" },
    { "click": "[data-testid='auth-mode-sign-up']" },
    { "fill": "[data-testid='auth-email']", "valueFrom": "generated.email" },
    { "fill": "[data-testid='auth-password']", "valueFrom": "generated.password" },
    { "click": "[data-testid='auth-submit']" },
    { "assertVisible": "[data-testid='workspace-list-page']" },
    { "fill": "[data-testid='workspace-name-input']", "valueFrom": "generated.workspaceName" },
    { "click": "[data-testid='workspace-create-submit']" },
    { "assertVisible": "[data-testid='workspace-boards-page']" },
    { "fill": "[data-testid='board-name-input']", "valueFrom": "generated.boardName" },
    { "click": "[data-testid='board-create-submit']" },
    { "assertVisible": "[data-testid='board-page']" },
    { "fill": "[data-testid='column-name-input']", "valueFrom": "generated.columnName" },
    { "click": "[data-testid='column-create-submit']" },
    { "fill": "[data-testid='card-create-input']", "valueFrom": "generated.cardTitle" },
    { "click": "[data-testid='card-create-submit']" },
    { "assertVisibleText": { "selector": "[data-testid='board-column']", "textFrom": "generated.cardTitle" } },
    { "assertNetworkSeen": "POST /api/v1/boards/*/cards" },
    { "assertNoFatalConsole": true }
  ]
}
```

Rules:

- every action step must record selector, current URL, visibility/enabled state and a DOM excerpt on failure;
- every scenario must state whether it requires backend and safe DB;
- random/generated values must be written to `report.json` for reproducibility;
- waits must be explicit: `waitForVisible`, `waitForText`, `waitForNetworkIdle` with fixed timeout and failure evidence;
- no hidden retries that convert a flaky UI into green evidence.

---

## 8. Frontend testability requirements

Before the custom runner becomes mandatory, the frontend must expose stable markers on the critical path.

Minimum markers:

| Surface | Required markers |
|---|---|
| App root/layout | `app-root`, `app-shell`, `main-nav`, `route-outlet`. |
| Auth | `auth-page`, `auth-mode-sign-in`, `auth-mode-sign-up`, `auth-email`, `auth-password`, `auth-display-name`, `auth-submit`, `auth-error`. |
| Workspace list | `workspace-list-page`, `workspace-create-form`, `workspace-name-input`, `workspace-description-input`, `workspace-create-submit`, `workspace-card`, `workspace-open-boards`. |
| Boards list | `workspace-boards-page`, `board-create-form`, `board-name-input`, `board-description-input`, `board-create-submit`, `board-card`, `board-open`. |
| Board page | `board-page`, `board-title`, `column-create-form`, `column-name-input`, `column-create-submit`, `board-column`, `card-create-input`, `card-create-submit`, `card-tile`. |
| Diagnostics | `local-first-status`, `sync-baseline-status`, `activity-feed`, `error-state`, `loading-state`. |

Policy:

- add markers only to critical flow surfaces, not every element;
- preserve accessible labels/headings for users and tests;
- markers are part of release evidence contract and should not be renamed casually;
- marker changes require updating scenario definitions and docs in the same patch.

---

## 9. Failure classification model

| Condition | Classification | Status |
|---|---|---|
| No supported browser executable found | `REL-ENV` or `REL-UIUX-PREREQ` | `skipped_prerequisite` |
| Browser starts but CDP endpoint never opens | `REL-UIUX` / `REL-PROC` | `infra_failed` |
| Frontend URL unreachable | `REL-FE` / `REL-PROC` | `skipped_prerequisite` or `infra_failed` |
| Backend API unreachable in real-backend scenario | `REL-BE` / `REL-PROC` | `skipped_prerequisite` or `failed` based on ownership |
| Safe DB proof missing for write-capable scenario | `REL-DB` | `skipped_prerequisite` |
| React root absent after page load | `REL-FE` or `REL-UIUX` | `failed` |
| Runtime exception/page fatal console | `REL-FE` | `failed` |
| Expected control missing/hidden/disabled | `REL-UIUX` | `failed` |
| Submit clicked but no network/backend state evidence | `REL-UIUX` or `REL-BE` | `failed` |
| Redaction cannot prove secrets are removed | `REL-SEC` | `failed` |
| Scenario definition invalid | `REL-UIUX` | `infra_failed` |

Mapping rule:

```text
If prerequisites are satisfied and the user-facing flow fails, do not classify it as browser tooling.
Classify it as product UI/backend evidence with the exact failing step and artifacts.
```

---

## 10. Release-gates integration

### 10.1 New gates

| Gate | Profile | Meaning |
|---|---|---|
| `frontend_uiux_browser_discovery` | diagnostic+ | Find supported system browser and record prerequisite evidence. |
| `frontend_uiux_boot` | prepared-local+ | Open app, capture DOM/console/storage boot evidence. |
| `frontend_uiux_mocked_core_flow` | prepared-local+ | Deterministic UI flow against mock API; no DB writes. |
| `frontend_uiux_real_backend_core_flow` | managed-runtime/full-local-release | Real UI flow against managed frontend/backend/test DB. |
| `frontend_browser_smoke_legacy` | optional transition | Existing Playwright signal, never required after parity. |

### 10.2 Profile behavior

| Profile | UIX behavior |
|---|---|
| `diagnostic` | discovery only; no browser launch unless explicitly accepted as read-only probe. |
| `prepared-local` | boot + mocked flow when frontend deps are present/prepared. |
| `isolated-db` | no UI requirement unless frontend/runtime is also available. |
| `managed-runtime` | boot + mocked + real-backend core flow with owned processes. |
| `full-local-release` | all UIX gates plus repeatability evidence; Playwright optional legacy only. |
| `clean-machine-dry` | scenario files, CLI help and artifact contract validation only. |
| `clean-machine-runtime` | browser discovery + boot + mocked flow inside sandbox if browser exists. |

### 10.3 Scorecard impact

Release Confidence hard caps should change as follows:

- `No real-backend product-path evidence` remains capped at `internal_candidate` until `frontend_uiux_real_backend_core_flow` is green or explicitly accepted as deferred.
- `Required gates skipped because prerequisites are absent` remains capped at `partial_signal` when UIX is mandatory and browser/runtime prerequisites are unresolved.
- `Playwright missing/timeout` must not cap the score after UIX parity and removal from mandatory gates.

---

## 11. Development phases

### UIX-0 — Plan and contract lock

Goal: freeze what the runner is allowed to become.

Deliverables:

- this development plan;
- docs index link;
- accepted relation between `REL-BROWSER` legacy blockers and `REL-UIUX-001` implementation track.

Exit criteria:

- plan reviewed;
- no code behavior change yet;
- Playwright remains mandatory/legacy exactly as before until implementation evidence exists.

### UIX-1 — Browser discovery and prerequisite report

Goal: classify environment before touching product evidence.

Implementation:

- add `tools/uiux_evidence.py discover-browser`;
- search known executables:
  - Linux: `chromium`, `chromium-browser`, `google-chrome`, `google-chrome-stable`, `brave-browser`, `microsoft-edge`;
  - Windows: common Chrome/Edge/Brave install paths plus `PATH`;
  - macOS-ready path names may be documented but not mandatory if macOS is not supported baseline;
- run `--version` where available;
- emit JSON/MD report with candidates, chosen executable and install hints;
- never download browsers.

Checks:

```bash
python -B tools/uiux_evidence.py discover-browser --report-dir .dev-bootstrap/runs/manual-uiux/discover
```

Exit criteria:

- missing browser produces a clear `skipped_prerequisite` report;
- stale Playwright cache is irrelevant;
- devbootstrap dry-run can list this gate without needing frontend deps.

### UIX-2 — Boot evidence probe

Goal: prove page opens and JS runtime does not immediately explode.

Implementation:

- launch system browser with temporary profile;
- open `/auth` or configured base route;
- capture:
  - final URL;
  - document title;
  - root/app shell marker;
  - DOM final HTML/excerpt;
  - console/runtime errors;
  - localStorage/sessionStorage before/after;
  - network summary;
- write `report.json` and `report.md`.

Exit criteria:

- app boot failure is distinguishable from browser launch failure;
- report is readable without terminal scrollback;
- artifacts are small and redacted.

### UIX-3 — Frontend markers and scenario contract

Goal: make the critical UI path observable without a Playwright-like selector engine.

Implementation:

- add minimal `data-testid` markers listed in section 8;
- keep accessible labels/headings unchanged;
- add a static marker contract document or tests to prevent accidental removal;
- add scenario JSON schema validation.

Checks:

```bash
cd frontend && npm run test:run
python -B tools/uiux_evidence.py validate-scenarios
```

Exit criteria:

- boot and mocked scenario can target stable markers;
- no unrelated UI restyling;
- marker changes are documented.

### UIX-4 — Mocked core UI flow without Playwright

Goal: replace existing mocked Playwright smoke with deterministic custom evidence.

Implementation options, in preference order:

1. project-owned temporary mock API server started by the runner;
2. CDP `Fetch.fulfillRequest` for a tiny list of API routes;
3. Vite-only fixture mode if it stays explicit and does not pollute production code.

Scenario:

- open auth page;
- sign in/sign up against mock API;
- render workspace list;
- assert workspace card and route shell;
- capture console/storage/network.

Exit criteria:

- `frontend_uiux_mocked_core_flow` passes without backend/DB;
- no Playwright dependency is involved;
- failure report includes selector, URL, DOM excerpt and console/runtime evidence.

### UIX-5 — Real-backend core flow through managed runtime

Goal: replace the real-backend Playwright smoke as the release product-path proof.

Prerequisites:

- managed frontend/backend runtime is owned by `devbootstrap`;
- write-capable DB is `TEST_DATABASE_URL`, managed test DB, or explicit safe disposable DB;
- backend smoke is green or known non-blocking.

Scenario:

- create generated user through UI;
- create workspace;
- create board;
- create column;
- create card;
- assert final DOM and API evidence;
- optionally verify card exists through backend API after UI action;
- capture storage and session evidence.

Exit criteria:

- two consecutive same-profile runs pass or fail with same classification;
- cleanup/retention policy for generated user/workspace is documented;
- failure cannot be mistaken for Playwright cache/install failure.

### UIX-6 — devbootstrap release-gates integration

Goal: make UIX a first-class release-gates signal.

Implementation:

- add UIX gate specs to `tools/devbootstrap.py`;
- preserve legacy `frontend_browser_smoke` as optional transition gate;
- add UIX artifacts to release-gates bundle contract;
- add `REL-UIUX` classifier mappings;
- update remediation hints and next-actions generation;
- update docs commands from `npm run test:browser` to `python -B tools/uiux_evidence.py ...` where appropriate.

Exit criteria:

- `release-gates --dry-run` lists UIX gates without running browser/download mutators;
- `release-gates --profile prepared-local --prepare-deps` can run boot + mocked UIX;
- `release-gates --managed-test-db --managed-runtime --prepare-deps` can run real-backend UIX;
- reports link to UIX evidence directory.

### UIX-7 — Repeatability, clean-machine and regression memory

Goal: prove UIX is stable enough to replace mandatory Playwright.

Implementation:

- add same-profile two-run probe;
- add clean-machine dry validation of scenario files and CLI;
- add clean-machine runtime probe where browser exists;
- add regression memory entries for `REL-UIUX` families;
- add failure fixtures for:
  - missing browser;
  - frontend URL unreachable;
  - selector missing;
  - fatal console error;
  - backend unreachable;
  - missing safe DB;
  - redaction failure.

Exit criteria:

- UIX failures map to stable IDs;
- old `REL-BROWSER-001..003` no longer block release when UIX gates are green;
- scorecard product-path confidence can use UIX artifacts.

### UIX-8 — Playwright removal from mandatory path

Goal: remove the mandatory dependency only after parity is proven.

Allowed after:

- UIX boot, mocked and real-backend gates are green in the target profiles;
- release-gates bundles include UIX artifacts;
- docs no longer require Playwright browser downloads for release proof;
- fallback/legacy path is explicitly optional.

Removal tasks:

- remove `@playwright/test` from mandatory dependencies if no optional tests remain;
- remove or archive `frontend/e2e/**` legacy specs outside source if no longer used;
- remove `playwright.config.ts` when no scripts reference it;
- replace `npm run test:browser` mandatory docs with UIX commands;
- remove `--install-playwright-browsers` from recommended release-gates ladder;
- keep `REL-BROWSER-*` as historical legacy IDs, not active blockers.

Exit criteria:

- clean source install no longer downloads Playwright browsers for mandatory checks;
- release confidence is based on UIX evidence;
- docs and package scripts do not contradict the new path.

---

## 12. Devbootstrap implementation notes

`tools/devbootstrap.py` should treat UIX as a product evidence layer, not as a dependency installer.

Suggested internal gate names:

```text
frontend_uiux_browser_discovery
frontend_uiux_boot
frontend_uiux_mocked_core_flow
frontend_uiux_real_backend_core_flow
```

Suggested outputs in release-gates bundle:

```text
logs/<gate>.log
uiux-evidence/<scenario>/report.md
uiux-evidence/<scenario>/report.json
uiux-evidence/<scenario>/dom-excerpt.txt
uiux-evidence/<scenario>/console.json
uiux-evidence/<scenario>/network.json
uiux-evidence/<scenario>/storage-before.json
uiux-evidence/<scenario>/storage-after.json
```

Migration behavior:

- before parity: run Playwright legacy only as current behavior says, but report that it is legacy;
- during parity: run both UIX and legacy Playwright when explicitly requested, compare classifications;
- after parity: UIX is mandatory, Playwright is optional/removed.

---

## 13. Security and privacy policy

UI evidence can accidentally capture sensitive state. The runner must therefore default to redaction rather than raw dumps.

Rules:

- generated identities use deterministic `local.test` domains and random suffixes;
- password values never enter reports;
- `Authorization`, `Cookie`, `Set-Cookie`, refresh/session/access token values are replaced with `<redacted>`;
- request/response bodies are omitted unless a scenario explicitly whitelists safe fixture fields;
- DOM snapshots may contain user-generated names, so generated names must be safe and non-personal;
- screenshot is optional and should be skipped by default in CI-like/headless diagnostic runs unless useful for failure diagnosis;
- redaction errors are release blockers under `REL-SEC`.

---

## 14. Cross-platform policy

| Area | Linux | Windows | Notes |
|---|---|---|---|
| Browser discovery | PATH + common package names. | PATH + Chrome/Edge/Brave install paths. | Missing browser is prerequisite, not failure. |
| Temporary profile | `tempfile.TemporaryDirectory`. | Same, watch locked files on cleanup. | Cleanup failure should be warning unless profile leaks secrets. |
| Process ownership | PID + command + temp dir proof. | PID + command + temp dir proof. | Do not kill foreign browsers. |
| Paths in reports | POSIX-style relative paths inside bundle. | Normalize separators. | Keep devctl archive portability. |
| Headless mode | `--headless=new` when supported. | Same; fallback to `--headless`. | Version evidence decides fallback. |

---

## 15. Acceptance matrix

| Capability | UIX-2 | UIX-4 | UIX-5 | UIX-7 | Required for Playwright removal |
|---|---:|---:|---:|---:|---:|
| System browser discovery | yes | yes | yes | yes | yes |
| App boot DOM proof | yes | yes | yes | yes | yes |
| Console/runtime fatal capture | yes | yes | yes | yes | yes |
| Mocked deterministic UI flow | no | yes | yes | yes | yes |
| Real backend critical path | no | no | yes | yes | yes |
| Storage before/after evidence | yes | yes | yes | yes | yes |
| Network/API evidence | basic | yes | yes | yes | yes |
| Safe DB/runtime integration | no | no | yes | yes | yes |
| Repeatability proof | no | no | partial | yes | yes |
| Clean-machine dry proof | no | no | no | yes | yes |
| Redacted bundle artifacts | yes | yes | yes | yes | yes |

---

## 16. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Runner grows into a bad Playwright clone | Maintenance burden returns. | Scenario DSL stays tiny; CDP command list is capped; no general framework promises. |
| Browser discovery is flaky across OS | False prerequisites. | Record candidate list/version and OS-specific install hints; do not auto-download. |
| CDP client is brittle | Infra failures. | Use a tiny command subset and fixture tests for protocol handling. |
| JS snippets hide accessibility regressions | Weak user evidence. | Combine `data-testid` targeting with visible/enabled/accessibility-name checks. |
| Mocked flow gives false confidence | Product path not proven. | Keep real-backend UIX gate mandatory for release candidate profiles. |
| Real-backend flow pollutes DB | Non-idempotent smoke. | Use generated names and managed/disposable DB; no shared fixed user assumptions. |
| Evidence leaks secrets | Security blocker. | Redaction-first network/storage reporting; `REL-SEC` fail closed. |
| Docs and package scripts drift | Users run obsolete Playwright path. | UIX-6/8 docs sweep is part of done criteria. |
| Archive grows again | Sharing friction. | Store only compact evidence; source docs link to run bundles instead of embedding dumps. |

---

## 17. First implementation patch sequence

Recommended patch order:

1. `docs-uiux-runner-plan` — this plan and docs index link.
2. `uiux-browser-discovery` — `tools/uiux_evidence.py discover-browser`, no frontend mutation.
3. `uiux-boot-evidence` — browser launch, `/auth` boot probe, compact report.
4. `uiux-testability-markers` — minimal `data-testid` markers and frontend unit/build checks.
5. `uiux-mocked-core-flow` — mock API strategy and deterministic custom scenario.
6. `uiux-real-backend-core-flow` — managed runtime/test DB scenario.
7. `uiux-release-gates-integration` — devbootstrap gates, bundle contract, classifiers.
8. `uiux-repeatability-clean-machine` — repeatability fixtures and regression memory.
9. `uiux-playwright-retirement` — remove/optionalize Playwright mandatory path.

Each patch should include only one conceptual layer and should not mix source behavior, docs sweep and dependency removal unless that layer cannot be verified independently.

---

## 18. Definition of done

The migration is done when:

- `release-gates --dry-run` documents UIX gates and their side effects;
- `release-gates --profile prepared-local --prepare-deps` can collect boot + mocked UIX evidence;
- `release-gates --managed-test-db --managed-runtime --prepare-deps` can collect real-backend UIX evidence;
- UIX report artifacts are included in release-gates bundles and are small/redacted;
- missing system browser is a clear prerequisite report, not product failure;
- fatal console/runtime errors fail the right gate with DOM/network/storage evidence;
- real-backend flow proves workspace → board → column → card creation through the UI;
- same profile can be repeated without dirty shared DB assumptions;
- `REL-UIUX` has stable classifier/probe/regression memory entries;
- Playwright browser downloads are no longer part of mandatory release proof.

