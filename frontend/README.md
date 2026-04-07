# P2P Planner frontend

## Быстрый старт

```bash
cd frontend
npm install
npm run dev
```

По умолчанию клиент ожидает backend на `http://127.0.0.1:18080/api/v1`
и использует dev user id `11111111-1111-7111-8111-111111111111`.

Если backend живет на другом адресе, создай `.env.local`:

```bash
VITE_API_BASE_URL=http://127.0.0.1:18080/api/v1
VITE_DEV_USER_ID=11111111-1111-7111-8111-111111111111
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
