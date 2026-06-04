# v1 known limitations

Этот документ фиксирует known limitations для v1/beta перед финальным release review. Он нужен не как маркетинговые release notes, а как честная граница того, что release-gates должны подсветить перед выпуском.

Freshness note: текущий implementation-status см. в `docs/product/v1-execution-roadmap.md`. Закрытые baseline-slices не исчезают из limitations: они становятся зонами, которые release-gates должны доказать или честно классифицировать, а не будущими blocker-работами сами по себе.

Evidence note: первый accepted checkpoint зафиксирован в `docs/product/release-evidence-checkpoint-2026-06-04.md`. `full-local-release` прошёл `ok` со score `89/100`; внешний beta всё ещё ограничен hard cap `repeatability-not-proven`.

## Ограничающие условия release-gates

- `python tools/devbootstrap.py release-gates` агрегирует backend, frontend, browser, docs и optional clean-machine checks; для внешней beta важно смотреть не только `Overall`, но и `release-confidence-gate.md`.
- На 2026-06-04 `frontend_uiux_real_backend_core_flow` прошёл и закрыл real-backend product-path cap; legacy `browser_real_backend_path` остается optional transition signal через `--include-real-backend-browser`.
- Текущий главный release-confidence cap — `repeatability-not-proven`: один успешный `full-local-release` run достаточен для internal candidate, но не для внешнего beta claim.
- Clean-machine quickstart в `full-local-release` прошёл как dry sandbox signal; более строгие clean-machine/deps/runtime профили можно запускать отдельно, если release review требует большего.
- DB-writing smoke/browser gates не должны писать в обычную dev-БД без явного `TEST_DATABASE_URL`, managed test DB или `--allow-dev-db-write`.
- Playwright browser binaries считаются infrastructure prerequisite. Их отсутствие классифицируется отдельно и не должно маскироваться как frontend regression.

## Продуктовые ограничения v1/beta

- P2P-синхронизация остается future-ready слоем, а не обязательным пользовательским сценарием v1.
- Conflict handling ограничен baseline duplicate/out-of-order/rejected markers, без полноценного merge UI.
- Import execution остается non-destructive boundary; destructive restore не входит в v1.
- MFA/passkeys/E2EE и local snapshot encryption не входят в v1 hardening.
- Attachment blobs зарезервированы, но не экспортируются в baseline backup bundle.
