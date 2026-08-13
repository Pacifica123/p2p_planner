# Roaming board protocol v1

`protocolVersion`: `p2p-kanban-roaming/1`

## Capability

`POST /api/v1/sync/roaming/capability`

Запрос:

```json
{ "boardId": "uuid" }
```

Ответ содержит `workspaceId`, `boardId`, `boardTag`, `boardKey`, минимум три
relay URL, сохраняемый Nostr kind и минимальное число подтверждений.
Capability выдаётся только администратору workspace.

`boardKey` выводится отдельно для каждой доски:

```text
HMAC-SHA256(masterKey, "p2p-kanban:roaming-board-key:v1" || 0x00 || boardId)
```

`boardTag`:

```text
base64url(HMAC-SHA256(boardKey, "p2p-kanban:board-tag:v1" || 0x00 || boardId))
```

## Relay record

Nostr kind `1979`, tags:

```json
[
  ["d", "<boardTag>"],
  ["t", "p2pkanban-roaming"],
  ["v", "1"]
]
```

`content`:

```json
{
  "version": 1,
  "boardTag": "<opaque>",
  "nonce": "<base64url 24 bytes>",
  "ciphertext": "<base64url XChaCha20-Poly1305>"
}
```

Открытый event body после расшифрования содержит стабильные UUID,
`replicaSeq`, `logicalClock`, `fieldMask`, полную карточку и `occurredAt`.

## Операции v1

- `board.snapshot` — стартовый read model для новой реплики;
- `card.put` — полная карточка плюс перечень изменённых полей;
- `card.delete` — глобальный tombstone карточки с `fieldMask: ["__lifecycle"]`;
- `fieldMask: ["*"]` — полное создание или server snapshot карточки.

Реплика читает журнал минимум из одного доступного реле, удаляет дубликаты по
Nostr event ID и protocol event ID, затем применяет события по порядку
`(logicalClock, replicaId, eventId)`. Для каждого поля хранится версия
победившего события.

`card.delete` не является обычным LWW-полем. Любой известный tombstone
безусловно блокирует последующие `card.put` и карточки из `board.snapshot`, пока
протокол не получит отдельную авторизованную операцию restore. Локальное
действие «Скрыть здесь» в roaming-журнал не попадает.

## Доставка

Публикация успешна после `minimumRelayAcks`. Неуспешная операция остаётся в
локальной очереди и повторяется. Backend использует durable outbox и backoff;
Android сохраняет очередь вместе с локальным snapshot.

Полный журнал запрашивается повторно, а локальные event ID дедуплицируются. Это
не даёт временно недоступному реле создать необратимую дыру в cursor.

## Модель угроз v1

- relay видит время, размер, Nostr pubkey и непрозрачный тег;
- relay не видит данные доски;
- подмена ciphertext обнаруживается AEAD;
- владение board key является capability;
- утрата ключа не восстанавливается из relay;
- отзыв участника требует ротации ключа и membership epoch в следующей версии.
