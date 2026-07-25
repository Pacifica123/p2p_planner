# Структура проекта

Актуальная карта основных каталогов `v1.0.0-beta.3`:

```text
.
├── VERSION
├── README.md
├── bootstrap.py
├── backend/
│   ├── Cargo.toml
│   ├── migrations/
│   ├── crates/
│   │   ├── sync-core/
│   │   ├── nostr-transport/
│   │   └── iroh-transport/
│   ├── src/
│   │   ├── auth/
│   │   ├── db/
│   │   ├── http/
│   │   ├── modules/
│   │   ├── transports/
│   │   └── bin/nostr_recover.rs
│   └── tests/
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── features/
│   │   ├── shared/
│   │   └── test/
│   └── e2e/
├── edge-coordinator/
├── deploy/
│   ├── bootstrap/
│   └── home-coordinator/
├── docs/
│   ├── adr/
│   ├── api/
│   ├── architecture/
│   ├── deployment/
│   ├── dev-bootstrap/
│   ├── devctl/
│   ├── development/
│   ├── domain/
│   ├── product/
│   └── sync/
├── release/
└── tools/
    ├── container_bootstrap.py
    ├── build_release_bundle.py
    ├── check_release_prep.py
    ├── devbootstrap.py
    └── uiux/
```

## Правила

### Документация рядом с кодом

Product roadmap отвечает на вопрос «что готово». ADR объясняет принятые
решения. Architecture описывает контракты. Deployment содержит команды.
Generated evidence не хранится в `docs/`.

### Backend — модульный монолит

Доменные модули разделены по ответственности, но работают в одном процессе и
одной транзакционной PostgreSQL. Путь зависимости:

```text
handler → service → repo
```

Repo одного модуля не должен становиться неявным API для другого.

### Transport отделён

`sync-core` не зависит от конкретной сети. Nostr/Iroh находятся в отдельных
crates, backend transport outbox — в `src/transports`, а Cloudflare-прототип —
в отдельном `edge-coordinator`.

### Frontend — по пользовательским функциям

`features/` содержит сценарии, `shared/` — переиспользуемые API/types/UI,
`app/` — composition и routing. Local-first store не должен расползаться по
экранным компонентам.

### Deployment не смешивается с разработкой

`deploy/bootstrap` — обычный self-host путь. `deploy/home-coordinator` —
удалённый общий coordinator через Tailscale. Host-native запуск остаётся в
`tools/devbootstrap.py` для разработки и release gates.

### Generated каталоги

Не являются исходниками:

```text
.dev-bootstrap/
backend/target/
frontend/node_modules/
frontend/dist/
edge-coordinator/node_modules/
release/dist/
```

### Mobile позже

Отдельного mobile-каталога пока нет. Mobile должен использовать общие sync/API
контракты, но не добавляется до выбора runtime и модели защищённого локального
хранилища.

