# p2pKanban

p2pKanban — экспериментальный local-first планировщик задач с досками,
колонками и карточками. Проект можно держать у себя, менять под собственный
клиент и постепенно переводить с обычного координатора на сменяемые P2P/relay
транспорты.

Сейчас это beta: основной web-сценарий работает, но полностью бессерверная
синхронизация ещё не готова.

## Быстрый запуск

Нужен только запущенный Docker Desktop либо Docker Engine с Compose v2.

Из корня проекта:

```bash
python bootstrap.py
```

На Windows вместо `python` может использоваться `py`:

```powershell
py bootstrap.py
```

Bootstrap сам:

- найдёт свободный web-порт;
- создаст контейнеры;
- сгенерирует и сохранит случайные секреты;
- создаст PostgreSQL-роль и БД;
- соберёт backend и frontend;
- применит миграции;
- дождётся готовности приложения;
- откроет его в браузере.

Создавать `.env`, устанавливать PostgreSQL, Rust или Node и вручную выполнять
SQL не нужно. Первый build может занять несколько минут.

## Обычные команды

| Действие | Команда |
|---|---|
| Запустить или обновить stack | `python bootstrap.py` |
| Посмотреть состояние | `python bootstrap.py status` |
| Посмотреть последние логи | `python bootstrap.py logs` |
| Следить за логами | `python bootstrap.py logs --follow` |
| Остановить, сохранив данные | `python bootstrap.py stop` |

После `stop` БД остаётся в Docker volume и вернётся при следующем запуске.

Полный сброс удаляет локальные данные и потому требует явного подтверждения:

```bash
python bootstrap.py reset --yes
```

Если Docker установлен, но закрыт, bootstrap остановится сразу и попросит
запустить Docker Desktop. Он не будет пытаться использовать или перенастраивать
случайный PostgreSQL с компьютера.

Подробности: [`docs/deployment/zero-config-bootstrap-v1.md`](docs/deployment/zero-config-bootstrap-v1.md).

## Что уже работает

- регистрация, вход и refresh-сессия;
- workspaces, boards, columns и cards;
- перемещение карточек;
- описание, статус и приоритет карточки;
- labels, checklists и comments;
- история активности и audit API;
- настройки внешнего вида пользователя и доски;
- локальный snapshot и очередь pending operations;
- backend-координируемая push/pull синхронизация;
- экспорт доски/workspace и импорт board-level JSON как новой копии;
- независимый `sync-core`;
- Nostr shadow outbox/recovery и native Iroh adapter как экспериментальный
  transport foundation.

## Что пока не готово

- coordinator-free P2P как основной режим;
- полноценный mobile-клиент;
- merge и destructive restore/import поверх существующих данных;
- законченный conflict-resolution UI;
- production-ready integrations/webhooks.

Не считайте наличие будущего контракта в коде готовой пользовательской
функцией. Актуальная карта состояния:
[`docs/product/v1-execution-roadmap.md`](docs/product/v1-execution-roadmap.md).

### Перенос доски через JSON

На открытой доске кнопка сохранения скачивает board-level backup JSON. Чтобы
восстановить его, откройте список досок нужного workspace, выберите
`Импорт доски из JSON`, проверьте состав и нажмите `Создать копию`.

Импорт не перезаписывает существующую доску и не переносит сессии, старые ID,
авторов или старую activity history. Подробности:
[`docs/architecture/import-export-backup-v1.md`](docs/architecture/import-export-backup-v1.md).

## Как это устроено

```text
browser
   |
web gateway (Nginx + React/Vite)
   |
Rust/Axum backend
   |
PostgreSQL
```

В обычном bootstrap-режиме наружу опубликован только web-gateway. PostgreSQL и
backend остаются во внутренней Docker-сети, поэтому порт `5432` на компьютере
не занимается.

Данные доски при работе приложения также сохраняются локально в клиенте.
Сетевой координатор пока принимает общий порядок изменений и проверяет права.
Nostr, Iroh и Durable Object являются дополнительным направлением развития, а
не скрытой заменой текущего backend.

## Доступ из локальной сети

По умолчанию приложение доступно только на текущем компьютере.

Для доверенной локальной сети:

```bash
python bootstrap.py start --listen lan
```

Это обычный HTTP-режим. Не публикуйте его порт напрямую в интернет. Для
удалённого приватного доступа используйте профиль
[`deploy/home-coordinator`](deploy/home-coordinator/README.md) с Tailscale.

## Разработка без контейнеров

Для работы над исходниками остаётся старый host-native путь:

```bash
python tools/devbootstrap.py self-check --no-write-report
python tools/devbootstrap.py diagnose --no-write-report
python tools/devbootstrap.py up --dry-run
```

Он предназначен для разработчиков, release gates и подробной диагностики. В
этом режиме нужны локальные Rust, Node и PostgreSQL либо отдельный dev-compose.

Backend запускается однозначно:

```bash
cd backend
cargo run --bin p2p-planner-backend
```

Frontend:

```bash
cd frontend
npm ci
npm run dev
```

## Документация

- [`docs/README.md`](docs/README.md) — карта документации;
- [`docs/product/v1-execution-roadmap.md`](docs/product/v1-execution-roadmap.md) — что реально готово;
- [`docs/architecture/project-structure.md`](docs/architecture/project-structure.md) — структура проекта;
- [`docs/api/openapi.yaml`](docs/api/openapi.yaml) — HTTP API;
- [`docs/deployment/zero-config-bootstrap-v1.md`](docs/deployment/zero-config-bootstrap-v1.md) — новый bootstrap;
- [`docs/deployment/free-hosting-transports-v1.md`](docs/deployment/free-hosting-transports-v1.md) — бесплатные transport-варианты;
- [`docs/adr/ADR-006-homeless-board-transport-stack.md`](docs/adr/ADR-006-homeless-board-transport-stack.md) — выбранная transport-архитектура;
- [`docs/dev-bootstrap/devbootstrap-v1-operations.md`](docs/dev-bootstrap/devbootstrap-v1-operations.md) — расширенная локальная диагностика.

## Проверки

Минимальная проверка нового bootstrap:

```bash
python -B tools/check_zero_config_bootstrap.py
```

Полный набор локальных release gates:

```bash
python -B tools/devbootstrap.py release-gates --profile full-local-release
```
