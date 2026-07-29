# Что осталось до стабильного v1.0.0

- Актуально на: 2026-07-29
- Базовая линия: `v1.0.0-beta.6`

## Закрыто функционально

- [x] Web CRUD workspace/board/column/card.
- [x] Метки, чек-листы, комментарии, activity и audit.
- [x] Web local snapshot и очередь карточек.
- [x] Backend push/pull baseline и roaming transport.
- [x] Export, preview и board import-as-copy.
- [x] Zero-config Docker bootstrap, update и rollback кода.
- [x] Native auth и Android-клиент.
- [x] Базовый Android CRUD и перенос карточек между колонками.
- [x] Исправление направления Android → backend → web.
- [x] Актуальная карта документации и универсальная концепция GitHub/devctl.

## Блокирует stable

- [ ] Выполнить два последовательных
  `python -B tools/devbootstrap.py release-gates --profile full-local-release`
  на одном чистом commit.
- [ ] Собрать release ZIP из точного тега через
  `python tools/build_release_bundle.py --require-tag`.
- [ ] Проверить распакованный ZIP на чистой Windows-машине.
- [ ] Проверить тот же ZIP на Linux.
- [ ] Подтвердить сохранение данных после stop/start, update и rollback.
- [ ] Выполнить PostgreSQL backup/restore drill по runbook и сверить counts.
- [ ] Пройти cross-client матрицу web → Android и Android → web для create,
  edit, move, archive и checklist CRUD.
- [ ] Решить границу релиза: Android входит в stable v1 либо остаётся явно
  помеченным beta-клиентом.
- [ ] Подтвердить import-as-copy smoke на итоговом bundle.
- [ ] Проверить ZIP на секреты, `.env`, локальные БД и generated-каталоги.
- [ ] Выбрать публичную лицензию либо явно зафиксировать отсутствие лицензии.
- [ ] После исправлений повторить gates и сохранить evidence bundle с
  контрольными суммами.

## Полезное полевое доказательство, но не замена release gates

- Продукт используется владельцем с `beta.3`; серьёзных потерь данных не
  замечено.
- Stop/start и обычная работа выглядят устойчиво в реальном сценарии.
- Это снижает риск, но не заменяет воспроизводимый update/rollback/restore
  прогон точного beta.6 commit.

## Не блокирует stable автоматически

- GitHub/devctl и другие внешние интеграции;
- coordinator-free режим;
- Iroh в браузере;
- MFA/passkeys;
- E2EE локальных snapshot;
- merge/destructive import;
- AppImage и отдельный Windows `.exe`.

Стабильность здесь означает проверенную узкую границу продукта, а не завершение
всех будущих направлений.
