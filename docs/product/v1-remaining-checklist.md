# Что осталось до стабильного v1.0.0

## Уже закрыто

- [x] Основной CRUD workspace/board/column/card.
- [x] Метки, чек-листы и комментарии.
- [x] Настройки внешнего вида.
- [x] Activity и audit.
- [x] Local-first snapshot и pending queue для основного сценария.
- [x] Backend push/pull sync baseline.
- [x] Export и import preview.
- [x] Базовый auth/security hardening.
- [x] Zero-config Docker bootstrap.
- [x] Экспериментальный transport foundation.
- [x] Версия и релизные документы выровнены на `v1.0.0-beta.3`.

## До публикации beta.3

- [ ] Выполнить `python -B tools/check_release_prep.py`.
- [ ] Выполнить `python -B tools/check_zero_config_bootstrap.py --frontend-build`.
- [ ] Выполнить `python -B tools/devbootstrap.py release-gates --profile full-local-release`.
- [ ] Исправить все ошибки обязательных gates.
- [ ] Пометить чистый commit тегом `v1.0.0-beta.3`.
- [ ] Собрать архив через `python tools/build_release_bundle.py --require-tag`.
- [ ] Проверить распакованный архив на Windows.
- [ ] Проверить распакованный архив на Linux.
- [ ] Приложить `SHA256SUMS.txt` и последний `release-gates_*.zip`.
- [ ] Отметить GitHub Release как Pre-release.

## До stable v1.0.0

- [ ] Повторить полный релизный прогон после исправлений, а не полагаться на
      один успешный запуск.
- [ ] Подтвердить сохранение данных после stop/start и обновления контейнеров.
- [ ] Зафиксировать backup/restore runbook для PostgreSQL volume.
- [ ] Выбрать и добавить лицензию либо явно оставить проект без публичной
      лицензии.
- [ ] Решить, достаточно ли import preview для stable v1.
- [ ] Решить, считается ли неполное применение входящего sync-log блокером
      stable v1.
- [ ] Удалить или явно оставить optional старые Playwright-пути.
- [ ] Убедиться, что release/snapshot не содержит секретов и тяжёлых generated
      каталогов.

## Не блокирует v1.0.0 автоматически

- mobile;
- coordinator-free P2P;
- Iroh в браузере;
- E2EE;
- MFA/passkeys;
- production integrations/webhooks;
- AppImage и отдельный Windows `.exe`.

Эти функции могут стать причиной следующего minor/major релиза, но не должны
бесконечно удерживать уже работающий self-host web-продукт в beta.

