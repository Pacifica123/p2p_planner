# Frontend browser smoke

Здесь живет короткий browser smoke слой на Playwright.

Он намеренно остается маленьким и проверяет только критичный пользовательский путь:
- boot;
- auth screen;
- sign-in transition;
- workspace list rendering;
- отсутствие white screen / uncaught page errors.

Запуск:

```bash
npm run test:browser
```


## Real-backend browser path

`auth-and-workspaces.smoke.spec.ts` intentionally uses Playwright `page.route` mocks and only checks deterministic boot/auth/workspace rendering. It does **not** satisfy the release checklist item for a real backend browser path.

The dedicated no-mock path lives in `smoke/real-backend.smoke.spec.ts` and is executed by:

```bash
npm run test:browser:real-backend
```

In `devbootstrap release-gates` this path is opt-in via `--include-real-backend-browser` and also requires write-safe DB permission through `TEST_DATABASE_URL` or `--allow-dev-db-write`.
