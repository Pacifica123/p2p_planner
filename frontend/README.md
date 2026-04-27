# P2P Planner frontend

## Быстрый старт

```bash
cd frontend
npm install
npm run dev
```

По умолчанию клиент ожидает backend на `http://127.0.0.1:18080/api/v1` и работает через текущий auth/session flow. После sign-in/sign-up frontend хранит access token in-memory и отправляет его как `Authorization: Bearer ...`; refresh происходит через cookie.

Если backend живет на другом адресе, создай `.env.local`:

```bash
VITE_API_BASE_URL=http://127.0.0.1:18080/api/v1
VITE_ENABLE_PROJECT_ROADMAP_SEED=true
```

## Что покрыто сейчас

- workspace list / switcher;
- boards list внутри workspace;
- board screen с колонками и карточками;
- drag-and-drop карточек между колонками;
- card details drawer;
- board activity panel;
- user appearance / board appearance;
- loading / empty / error states;
- базовый create / edit / archive / delete wiring для уже стабильного backend flow.

## Что недавно было причесано

- board surface разложена на более мелкие UI-компоненты;
- убран разъехавшийся вертикальный stretch в board layout;
- sidebar списки стали аккуратнее при большом количестве элементов;
- глобальные стили собраны без дублирования и с более предсказуемым responsive-поведением.


## Тестирование

### Unit и integration

После установки зависимостей:

```bash
npm run test:run
```

Для watch-режима:

```bash
npm test
```

### Browser smoke

Один раз установи браузеры Playwright:

```bash
npx playwright install
```

После этого можно запускать короткий browser smoke:

```bash
npm run test:browser
```

Smoke использует mocked API responses, проходит через auth screen и временно отключает автосид dev-roadmap board, чтобы сценарий оставался быстрым и детерминированным.

Подробная инструкция по тестированию всего приложения: `../docs/architecture/testing-application-guide-v1.md`.
