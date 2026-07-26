# Документация p2pKanban

Этот каталог описывает фактическое состояние проекта. Если старый план
противоречит коду или более новому документу, приоритет у следующего порядка:

1. `VERSION`, главный `README.md` и работающий код;
2. `product/v1-execution-roadmap.md`;
3. ADR;
4. текущие архитектурные и эксплуатационные документы;
5. исторические планы разработки.

## С чего начать

Обычному пользователю достаточно:

- [`../README.md`](../README.md) — запуск и основные команды;
- [`deployment/zero-config-bootstrap-v1.md`](deployment/zero-config-bootstrap-v1.md) — как работает запуск без `.env`;
- [`deployment/application-update-strategy-v1.md`](deployment/application-update-strategy-v1.md) — безопасная граница будущего автообновления;
- [`product/v1-known-limitations.md`](product/v1-known-limitations.md) — честные ограничения;
- [`product/v1.0.0-beta.3-release-notes.md`](product/v1.0.0-beta.3-release-notes.md) — текст текущего релиза.

Разработчику:

- [`product/v1-execution-roadmap.md`](product/v1-execution-roadmap.md) — что
  готово, частично готово и отложено;
- [`architecture/project-structure.md`](architecture/project-structure.md) —
  структура репозитория;
- [`api/openapi.yaml`](api/openapi.yaml) — HTTP API;
- [`architecture/testing-strategy-v1.md`](architecture/testing-strategy-v1.md)
  — проверки;
- [`dev-bootstrap/devbootstrap-v1-operations.md`](dev-bootstrap/devbootstrap-v1-operations.md)
  — расширенная локальная диагностика.

Для понимания синхронизации:

- `domain/` — сущности и права;
- `sync/` — протокол и конфликты;
- `adr/` — принятые архитектурные решения;
- [`deployment/free-hosting-transports-v1.md`](deployment/free-hosting-transports-v1.md)
  — домашний координатор, Nostr, Iroh и edge coordinator.

## Текущее состояние

| Область | Фактическое решение |
|---|---|
| Версия | `v1.0.0-beta.3`, GitHub Pre-release |
| Основной запуск | `python bootstrap.py`, весь runtime в Docker |
| Канонический путь | React/Vite → Nginx → Rust/Axum → PostgreSQL |
| Local-first | Локальный snapshot и очередь исходящих операций для основного web-сценария |
| Синхронизация | Backend-координируемая; клиентский pull ещё не строит все проекции автоматически |
| P2P | `sync-core`, Nostr shadow и Iroh adapter реализованы как экспериментальный фундамент |
| Edge coordinator | Отдельный совместимый прототип; не заменяет основной backend |
| Mobile | Отложен до стабилизации web/sync |
| Релиз | Основной артефакт — self-host bootstrap ZIP, а не AppImage и не одинокий `.exe` |

## Важная граница

p2pKanban пока не является полностью бессерверной P2P-системой. У каждого
клиента есть локальные данные, но права и каноническое принятие общих изменений
в обычном режиме всё ещё определяет Rust/PostgreSQL-координатор.

Nostr, Iroh и Durable Object не должны описываться как готовый пользовательский
режим, пока не завершены подписи устройств, эпохи состава участников,
автоматическое восстановление проекций и полноценная интеграция с клиентами.

## Команды

Обычный запуск:

```bash
python bootstrap.py
```

Статические проверки релизной подготовки:

```bash
python -B tools/check_release_prep.py
python -B tools/check_zero_config_bootstrap.py
```

Полный локальный релизный прогон:

```bash
python -B tools/devbootstrap.py release-gates --profile full-local-release
```

Сборка основного релизного архива из помеченного тегом commit:

```bash
python tools/build_release_bundle.py --require-tag
```

## Политика артефактов

В Git хранятся исходники, миграции, OpenAPI, документация, устойчивые примеры и
небольшие fixtures.

Не хранятся `.env`, секреты, `.dev-bootstrap`, `node_modules`, `target`, `dist`,
логи, локальные БД и крупные релизные архивы. Итоги release gates и собранные
артефакты прикладываются к релизу отдельно.

## Язык

Основной язык документации — русский. Имена протоколов, API-полей, команд,
типов, файлов и общепринятые технические обозначения остаются без перевода.
Английская версия сохраняется только там, где она нужна конечному получателю,
например в тексте GitHub Release и `README_RELEASE_EN.md`.
