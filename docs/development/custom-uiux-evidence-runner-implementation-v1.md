# Custom UI/UX Evidence Runner v1 — implementation notes

This document records the first executable implementation slice for the Playwright exit strategy described in `custom-uiux-evidence-manifesto-v1.md` and `custom-uiux-evidence-runner-development-plan-v1.md`.

## Implemented scope

The patch introduces a Python stdlib UI/UX runner under `tools/uiux_evidence.py` and `tools/uiux/`.

The runner can:

- discover an already installed Chromium-compatible browser without downloading Playwright browser revisions;
- launch the browser with a temporary profile and a local Chrome DevTools Protocol endpoint;
- drive basic UI actions through CDP: navigation, visibility assertions, text input, clicks, visible-text assertions and network assertions;
- start a runner-owned mock API for deterministic frontend-only evidence;
- optionally start the Vite frontend with an injected `VITE_API_BASE_URL`;
- produce evidence artifacts: JSON/Markdown report, DOM snapshot, DOM excerpt, console events, runtime errors, network log, storage snapshots and mock API request log.

## Scenarios

The first scenario set lives in `tools/uiux/scenarios/`:

- `boot` proves that the auth route opens and renders without fatal runtime errors;
- `mocked-core-flow` proves the workspace → board → column → card UI path against the runner-owned mock API;
- `real-backend-core-flow` proves the same path against managed frontend/backend/test database runtime.

## Frontend contract

The patch adds stable `data-testid` markers to the app shell, auth page, workspace list, board list, board screen, column/card creation controls, status banners and shared loading/error components.

The marker contract is intentionally checked from source by `python -B tools/uiux_evidence.py validate-scenarios --json`, so accidental marker drift is caught before a browser is even launched.

## devbootstrap integration

`release-gates` now includes these UIX gates:

- `frontend_uiux_validate_scenarios`;
- `frontend_uiux_browser_discovery`;
- `frontend_uiux_boot`;
- `frontend_uiux_mocked_core_flow`;
- `frontend_uiux_real_backend_core_flow`.

The real-backend UIX flow is required only when managed runtime is requested and a safe managed test DB/runtime is available. Without managed runtime it is reported as an optional skip, matching the existing safety model for DB-writing browser paths.

Legacy Playwright gates remain present but are optional during the transition. Profile defaults no longer request Playwright browser installation.

## Environment behavior

The runner never downloads browsers. Missing browsers or browser policies that block local navigation are classified as environment prerequisites rather than product regressions. This keeps release evidence honest: a blocked browser environment is visible, but it is not mislabeled as a broken frontend.

## Current non-goals

This first slice does not yet implement drag-and-drop, visual screenshots, accessibility tree checks, multi-tab flows or full Playwright dependency removal. Those remain follow-up slices after the new runner proves stable on boot/core-flow evidence.
## Hardening follow-up: CDP input and console classification

The first manual Linux run proved browser discovery and frontend startup, but exposed two runner-level issues rather than product regressions:

- CDP `fill` initially assigned `element.value` directly. That updated the DOM value but could leave React controlled component state unchanged, so form submit handlers saw stale empty state. The runner now uses the native input/textarea value setter and dispatches a bubbling `InputEvent` plus `change`, which matches the React-controlled form contract more closely.
- Chromium `Log.entryAdded` reports ordinary failed HTTP resources, such as expected unauthenticated refresh probes, with `level=error`. These events are now kept in console evidence but are not treated as JavaScript runtime crashes. Fatal evidence remains explicit `console.error`/`console.assert`, CDP `Runtime.exceptionThrown`, and browser `fatal` log entries. Network failures stay visible in `network.json` and the report counters.

This keeps `boot` focused on “the app can open and React does not crash”, while `mocked-core-flow` and `real-backend-core-flow` remain responsible for proving the actual user path and API behavior.

