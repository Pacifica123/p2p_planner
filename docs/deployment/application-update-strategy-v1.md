# Обновление server-client без потери данных

- Статус: первая рабочая реализация
- Команда: `python bootstrap.py update`
- Канал по умолчанию: GitHub-ветка `main`
- Область: zero-config Docker bootstrap

## Пользовательский путь

Если release bundle содержит адрес исходного репозитория:

```bash
python bootstrap.py update
```

Если старый bundle ещё не содержал адрес, он задаётся один раз:

```bash
python bootstrap.py update \
  --repository https://github.com/owner/repository
```

Для локальной проверки новой копии исходников:

```bash
python bootstrap.py update --source-dir ../new-p2pkanban
```

Посмотреть план без Docker-переключения:

```bash
python bootstrap.py update --source-dir ../new-p2pkanban --dry-run
```

## Что updater меняет

Backend и frontend являются заменяемыми Docker images. PostgreSQL и секреты
хранятся в постоянных named volumes.

Updater:

1. получает exclusive lock;
2. проверяет работающий stack и свободное место;
3. скачивает `main` в отдельный локальный каталог;
4. проверяет структуру, `VERSION`, Compose и встроенный bootstrap-check;
5. собирает versioned backend/web images, пока текущие контейнеры работают;
6. создаёт `pg_dump` вне Docker volumes;
7. помечает текущие images отдельным rollback-тегом;
8. запускает новые контейнеры на прежних volumes;
9. ждёт `/healthz`;
10. сравнивает число пользователей, пространств, досок и карточек;
11. сохраняет несекретный JSON-отчёт и активный source/image tag.

Ни на одном шаге updater не выполняет `docker compose down --volumes`.

## Где остаются данные

| Данные | Место |
|---|---|
| PostgreSQL | прежний named volume |
| JWT secret и пароль БД | прежний закрытый volume |
| Backup перед update | `.dev-bootstrap/backups/update-*/p2pkanban.dump` |
| Полученные исходники | `.dev-bootstrap/releases/<update>/source` |
| Отчёт | `.dev-bootstrap/update-reports/<update>.json` |
| Несекретное состояние | `.dev-bootstrap/container-stack.json` |

Каталог `.dev-bootstrap` не входит в Git и Docker build context.

## Отказ до переключения

Если не скачался архив, не прошла проверка или не собрались images, работающие
контейнеры не трогаются. Backup БД создаётся после успешной сборки, но до
переключения.

## Автоматический откат

Если новые контейнеры не стали готовы либо контрольные counts уменьшились,
updater:

1. запускает сохранённые старые backend/web images;
2. использует тот же PostgreSQL volume;
3. сохраняет отчёт со статусом `rolled_back`;
4. не восстанавливает dump автоматически.

Автоматическое восстановление БД из dump не выполняется: это отдельная
разрушительная операция.

## Ручной rollback

После успешного update можно вернуть прошлый код:

```bash
python bootstrap.py rollback
```

Перед переключением создаётся ещё один `pg_dump`. БД остаётся текущей. Поэтому
миграции обновляемой линии должны следовать expand/contract:

1. добавить совместимые nullable/default поля;
2. выпустить код, понимающий старую и новую форму;
3. перенести данные;
4. удалять старую форму только в более позднем релизе.

## Почему не `git pull` внутри контейнера

Работающий контейнер не хранит Git credentials и не является редактируемым
сервером исходников. Новая версия строится рядом со старой и получает отдельный
image tag. Это позволяет проверить сборку до переключения и сохранить
предыдущий image для rollback.

## Почему пока нет кнопки в web-клиенте

Updater управляет Docker, backup и заменой серверных процессов. Обычная
web-сессия пользователя не должна автоматически получать такие права.

До появления отдельного локального control plane с собственной авторизацией
безопасный пользовательский вход — команда `python bootstrap.py update`.

## Доверие к источнику

Первая реализация следует пожеланию проекта и обновляется из плавающей `main`.
HTTPS защищает передачу, а source fingerprint и адрес записываются в отчёт, но
`main` не является неизменяемым релизом.

Для публичной стабильной версии следующий шаг — update manifest на GitHub
Release с точным commit, SHA-256 и immutable image digest. Текущая реализация
уже разделяет источник, сборку, активную версию и volumes, поэтому переход не
потребует менять модель хранения данных.

## Обязательный smoke на машине с Docker

1. Запустить beta.3 и создать аккаунт, пространство, доску и карточку.
2. Выполнить `python bootstrap.py update`.
3. Проверить вход тем же аккаунтом и содержимое доски.
4. Проверить `status` и JSON-отчёт.
5. Остановить и снова запустить stack.
6. Выполнить `rollback` и повторно проверить данные.
7. Убедиться, что `.dev-bootstrap/backups` содержит два читаемых `pg_dump`.

Этот сценарий нужен на Windows с Docker Desktop и Linux с Docker Engine.
