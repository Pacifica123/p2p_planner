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
