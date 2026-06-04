# Release evidence checkpoint 2026-06-04

- Status: accepted internal release evidence checkpoint
- Source run: `.dev-bootstrap/runs/20260604_050815_release-gates/`
- Command: `python tools/devbootstrap.py release-gates --profile full-local-release`
- Report archive: `release-gates_20260604_051022.zip`
- Related policy: `docs/development/release-confidence-scorecard-v1.md`

## Result

The configured `full-local-release` checkpoint passed on Windows with managed PostgreSQL test DB, managed backend, managed frontend and UIX evidence:

```text
Overall: ok
Classification: release_gates_ok
Profile: full-local-release
Release confidence score: 89/100
Raw class: beta_candidate
Effective class: internal_candidate
Decision: internal_candidate_only
Unknown ratio: 0.0
Active hard cap: repeatability-not-proven
```

This closes the previous "fresh release evidence is missing" blocker. It does not by itself authorize external beta naming, because repeatability has not reached the accepted threshold yet.

## Gates that matter for the product path

| Gate | Result | Why it matters |
| --- | --- | --- |
| `managed_test_db_prepare` | OK | DB-writing checks used a disposable managed PostgreSQL database. |
| `backend_python_smoke_first` | OK | Backend core/API smoke passed once against the managed runtime. |
| `backend_python_smoke_second` | OK | Backend smoke was immediately repeatable within the same run. |
| `frontend_build` | OK | The web client built successfully. |
| `frontend_unit_integration` | OK | Frontend unit/integration checks passed. |
| `frontend_uiux_boot` | OK | Browser boot reached the managed frontend. |
| `frontend_uiux_mocked_core_flow` | OK | Custom UIX runner proved the mocked frontend core flow. |
| `frontend_uiux_real_backend_core_flow` | OK | Custom UIX runner proved the preferred real-backend product path. |
| `frontend_browser_smoke` | OK | Legacy browser smoke still passed as transition coverage. |
| `clean_machine_sandbox` | OK | Clean sandbox quickstart signal passed. |

`browser_real_backend_path` was skipped because the legacy no-mock browser gate was not opted in. This is not the active product-path blocker anymore: the scorecard now accepts `frontend_uiux_real_backend_core_flow` as the preferred proof. It remains optional transition coverage when explicitly requested.

## Confidence interpretation

The scorecard produced raw `beta_candidate`, but the effective class stayed `internal_candidate` because of the active hard cap:

```text
repeatability-not-proven: No accepted two-run/repeatability evidence at threshold 0.8.
```

Therefore the safe interpretation is:

- internal/manual beta-style testing is now justified;
- external beta naming still needs repeatability evidence or an explicit release decision accepting the cap;
- the next evidence task is another same-profile run, not another broad feature patch.

## Next decision points

1. Rerun the same profile from the current source state:
   `python tools/devbootstrap.py release-gates --profile full-local-release`.
2. If repeatability reaches the accepted threshold, update release notes/known limitations and decide the beta naming profile.
3. If repeatability remains capped, inspect `remediation/repeatability-loop.*` and fix only the smallest unstable family.
4. After the repeatability decision, choose one product slice: account-management/auth UX hardening or import-as-copy execution after preview.
