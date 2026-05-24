# v1 known limitations

Этот документ фиксирует known limitations для v1/beta перед финальным release review. Он нужен не как маркетинговые release notes, а как честная граница того, что release-gates должны подсветить перед выпуском.

## Ограничающие условия release-gates

- `python tools/devbootstrap.py release-gates` агрегирует backend, frontend, browser, docs и optional clean-machine checks, но результат нельзя считать полным v1 release signal, если есть `skipped_prerequisite`, `infra_failed`, `partial_pass` или `not_implemented` gates.
- Mocked browser smoke проверяет boot/auth/workspace rendering, но не закрывает real backend browser path. Для этого есть отдельный gate `browser_real_backend_path`, который запускается через `--include-real-backend-browser` и требует live backend + write-safe DB permission.
- Clean-machine quickstart сделан optional: его нужно включать явно через `--include-clean-machine`, потому что он копирует проект во временный каталог и прогоняет safe bootstrap sequence.
- DB-writing smoke/browser gates не должны писать в обычную dev-БД без явного `TEST_DATABASE_URL` или `--allow-dev-db-write`.
- Playwright browser binaries считаются infrastructure prerequisite. Их отсутствие классифицируется отдельно и не должно маскироваться как frontend regression.

## Продуктовые ограничения v1/beta

- P2P-синхронизация остается future-ready слоем, а не обязательным пользовательским сценарием v1.
- Conflict handling ограничен baseline duplicate/out-of-order/rejected markers, без полноценного merge UI.
- Import execution остается non-destructive boundary; destructive restore не входит в v1.
- MFA/passkeys/E2EE и local snapshot encryption не входят в v1 hardening.
- Attachment blobs зарезервированы, но не экспортируются в baseline backup bundle.
