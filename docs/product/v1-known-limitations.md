# v1 known limitations

Этот документ фиксирует known limitations для v1/beta перед GitHub Pre-release `v1.0.0-beta.2`. Он нужен не как маркетинговые release notes, а как честная граница того, что release-gates и artifact smoke должны подсветить перед выпуском.

Freshness note: текущий implementation-status см. в `docs/product/v1-execution-roadmap.md`. Release-evidence checkpoint от 2026-06-04 прошёл `Overall: ok`; оставшийся hard cap перед stable release — `repeatability-not-proven`.

## Ограничающие условия release-gates

- `python tools/devbootstrap.py release-gates --profile full-local-release` прошёл на 2026-06-04, но stable `v1.0.0` нельзя объявлять до repeatability checkpoint.
- `clean-machine` evidence остаётся обязательным маркером release-gates docs: clean-machine sandbox/quickstart должен проходить и быть сохранён в финальном release-gates bundle.
- Mocked browser/UIX smoke проверяет frontend behavior, но real backend product path закрывается только `frontend_uiux_real_backend_core_flow`; в принятом checkpoint этот gate прошёл.
- Legacy `browser_real_backend_path` остается optional transition signal через `--include-real-backend-browser`, но не является обязательным beta.2 blocker.
- DB-writing smoke/browser gates не должны писать в обычную dev-БД без явного `TEST_DATABASE_URL` или managed test DB.
- Playwright/browser binaries считаются infrastructure prerequisite. Их отсутствие классифицируется отдельно и не должно маскироваться как frontend regression.

## Продуктовые ограничения v1/beta

- P2P-синхронизация остается future-ready слоем, а не обязательным пользовательским сценарием v1.
- Conflict handling ограничен baseline duplicate/out-of-order/rejected markers, без полноценного merge UI.
- Import execution остается non-destructive boundary; destructive restore не входит в v1.
- MFA/passkeys/E2EE и local snapshot encryption не входят в v1 hardening.
- Attachment blobs зарезервированы, но не экспортируются в baseline backup bundle.


## Ограничения release artifacts для beta.2

- GitHub release должен быть отмечен как **Pre-release**.
- Windows `.exe` должен попадать в self-host bundle, а не выкладываться как одинокий бинарник без `README_RELEASE.md`, `.env.example`, frontend build и DB instructions.
- Linux `.AppImage` является обязательным beta.2 asset candidate, но его готовность должна подтверждаться artifact-level smoke на Linux, а не только source-level `release-gates`.
- AppImage должен явно документировать, что именно он запускает и какие внешние prerequisites остаются, особенно PostgreSQL, если он не включён в packaged runtime story.
- `SHA256SUMS.txt` обязателен для всех загружаемых binary/archive assets; GPG signature опциональна.
- Devctl snapshots/patches не должны включать большие `.zip`, `.exe`, `.AppImage` payloads; такие файлы загружаются только в GitHub Release assets.
