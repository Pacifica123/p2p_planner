# Release evidence checkpoint — 2026-06-04

- Status: accepted local evidence checkpoint
- Target release line: `v1.0.0-beta.2`
- Source run: `20260604_050815_release-gates`
- Command: `python tools/devbootstrap.py release-gates --profile full-local-release`
- Bundle: `.dev-bootstrap/runs/20260604_050815_release-gates/release-gates_20260604_051022.zip`
- Related docs: `docs/development/release-confidence-scorecard-v1.md`, `docs/product/v1.0.0-beta.2-release-notes.md`, `docs/product/v1.0.0-beta.2-release-artifacts.md`, `docs/product/v1-known-limitations.md`

## Result

```text
Overall: ok
Classification: release_gates_ok
Profile: full-local-release
Score: 89/100
Raw class: beta_candidate
Effective class: internal_candidate
Active hard cap: repeatability-not-proven
Unknown ratio: 0.0
```

This run closes the previous `release-evidence` question for the current machine: the real backend product path is now proven through `frontend_uiux_real_backend_core_flow` against a managed backend/frontend/test DB pair.

## Passed gates

The run passed the release-relevant stack:

- managed PostgreSQL test database create/drop;
- frontend dependency preparation;
- backend dependency warmup;
- `self_check` and `diagnose`;
- DB-enabled backend tests gate;
- managed backend startup;
- backend Python smoke twice;
- frontend build;
- frontend unit/integration tests;
- UIX scenario validation;
- browser discovery;
- managed frontend startup;
- UIX boot;
- UIX mocked core flow;
- UIX real-backend core flow;
- frontend browser smoke;
- README / release notes / v1 checklist docs gates;
- clean-machine sandbox;
- owned frontend/backend teardown;
- managed test DB retention/drop.

## Accepted non-blocking signals

- `browser_real_backend_path` was skipped because it is the legacy explicit opt-in Playwright no-mock gate. The preferred real-backend proof is now `frontend_uiux_real_backend_core_flow`, which passed.
- `backend_cargo_test_default` reported `PARTIAL_PASS` because some Rust tests are ignored by default. The release profile separately ran the DB-enabled ignored-test gate successfully.

## Remaining release cap

The only active hard cap is `repeatability-not-proven`.

This means the project has enough evidence to prepare `v1.0.0-beta.2` release artifacts, but the release should remain a GitHub **Pre-release** until the beta.2 candidate is checked by at least one more full-local-release run after release-prep/docs packaging changes.

## Next action

Prepare the beta.2 release surface:

1. publish release notes and known limitations for `v1.0.0-beta.2`;
2. define the GitHub release asset contract for Windows `.exe` bundle and Linux `.AppImage`;
3. rerun `python tools/devbootstrap.py release-gates --profile full-local-release` after the release-prep patch;
4. attach the final release-gates bundle, checksums and platform artifacts to a GitHub Draft Release / Pre-release.
