# Манифест отказа от Playwright и перехода к кастомному UI/UX Evidence Runner v1

## Decision

Playwright is no longer the desired mandatory browser-smoke foundation for this project. It may remain temporarily as a legacy transition layer, but the release signal must move to a custom lightweight UI/UX Evidence Runner.

## Why

Playwright repeatedly shifted attention from product evidence to tool maintenance:

- missing browser revision cache;
- stale Chromium cache considered “present” by the bootstrapper;
- `chromium_headless_shell` mismatch;
- install timeout;
- large browser downloads and OS-level dependencies;
- ambiguous classification: “UI broken” vs “Playwright setup broken”.

The project needs proof that the user can open the app and execute a critical scenario, not proof that a bundled automation ecosystem is healthy.

## Goals to preserve

The replacement must still check as much of the user-facing contract as possible:

| Goal | Required evidence |
|---|---|
| Page opens | HTTP status, DOM snapshot, app root mounted. |
| JS runtime does not crash | browser console/runtime error capture. |
| Routing works | URL changes and route-level DOM markers. |
| Button exists and is accessible | selector, bounding box, disabled/hidden state, accessible name when available. |
| Form can be filled/submitted | input value evidence, submit event, resulting DOM/network/backend state. |
| Local/session state works | localStorage/sessionStorage snapshot before/after scenario. |
| Backend contract is usable | observed network calls or API state checks. |
| Failure is diagnosable | JSON/MD report, screenshot/DOM/console/network evidence where practical. |

## What not to build

Do not reimplement Playwright:

- no general selector engine;
- no large fixture runner framework;
- no tracing/video subsystem as mandatory path;
- no cross-browser compatibility suite in v1;
- no attempt to hide async UI complexity behind magical waits.

The runner should be small, explicit and project-specific.

## Preferred technical direction

Use a system browser rather than bundled browser revisions:

1. discover installed executables: `chromium`, `google-chrome`, `chrome`, `brave`, etc.;
2. run headless with a temporary user data dir;
3. use Chrome DevTools Protocol or browser CLI capabilities;
4. collect DOM, console, runtime exception, localStorage/sessionStorage and selected network evidence;
5. drive only the minimal critical scenarios.

If no supported browser exists, classify as environment prerequisite and give an OS-specific install hint. Do not download large browsers by default.

## Browserless alternatives

Some goals can be checked without a real browser, but not all:

| Method | Good for | Not enough for |
|---|---|---|
| `npm run build` | Bundling, TypeScript, import graph. | Runtime DOM and user interaction. |
| Vitest + jsdom | Component logic, state reducers, simple forms. | Real browser layout, storage quirks, Vite/runtime integration. |
| API smoke | Backend contract. | UI wiring and routing. |
| Static DOM/build inspection | Asset presence. | User scenario proof. |

Conclusion: use browserless tests for cheaper coverage, but keep one lightweight real-browser evidence path for release.

## Minimal runner architecture

```text
tools/uiux_evidence.py
  discover-browser
  boot
  scenario --name mocked-core-flow
  scenario --name real-backend-core-flow
  report
```

Artifacts:

```text
.dev-bootstrap/runs/<run-id>/uiux-evidence/
  report.md
  report.json
  dom-final.html
  console.json
  storage-before.json
  storage-after.json
  network.json
  screenshot.png        optional
```

## Scenario style

Scenarios should be declarative enough to review, but not a new automation language:

```json
{
  "name": "core-board-flow",
  "steps": [
    {"assertVisible": "[data-testid='app-shell']"},
    {"click": "[data-testid='new-board']"},
    {"fill": "[data-testid='board-title']", "value": "Evidence Board"},
    {"click": "[data-testid='submit-board']"},
    {"assertVisibleText": "Evidence Board"}
  ]
}
```

If a step fails, report the exact selector, current URL, DOM excerpt, console errors and storage/network deltas.

## Migration plan

| Phase | Result |
|---|---|
| UIX-0 | Manifest and scope lock. |
| UIX-1 | Browser executable discovery and prerequisite report. |
| UIX-2 | Boot evidence probe: open app, capture DOM/console/runtime/storage. |
| UIX-3 | Mocked critical UI scenario. |
| UIX-4 | Real-backend critical scenario through managed runtime/test DB. |
| UIX-5 | release-gates integration and `REL-UIUX` taxonomy. |
| UIX-6 | Remove Playwright from mandatory gates, deps/scripts/docs. |
| UIX-7 | Repeatability proof and clean-machine proof. |

## Removal checklist

When parity is reached:

- remove Playwright scripts from `frontend/package.json` if no longer needed;
- remove `@playwright/test` from dependencies;
- delete legacy `frontend/e2e/**` specs or move to archive outside source;
- remove `playwright.config.*`;
- remove `--install-playwright-browsers` as mandatory path from devbootstrap;
- replace Playwright docs with UI/UX Evidence Runner docs;
- keep compatibility aliases only if they do not download browsers or hide failures.

## Risks

| Risk | Mitigation |
|---|---|
| Custom runner grows into a worse Playwright | Keep scope project-specific and scenario-minimal. |
| Browser discovery differs across OS | Make prerequisite report explicit and non-destructive. |
| CDP code becomes brittle | Use few commands, stable evidence contracts, self-checks. |
| Accessibility checks are too shallow | Start with visible/enabled/name evidence; add a11y library later only if needed. |
| False confidence | Keep backend API smoke, unit tests and build gates separate. |

## Definition of done

Playwright can leave the mandatory path when the custom runner proves:

- app boot with no runtime console fatal;
- core mocked UI flow;
- real-backend core flow with managed runtime/test DB;
- storage/session evidence;
- clear failure classification;
- stable reports in clean-machine dry profile;
- docs and release-gates no longer require Playwright browser downloads.
