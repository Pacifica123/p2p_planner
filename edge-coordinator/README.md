# p2pKanban edge coordinator

Small Cloudflare Durable Object compatibility anchor. It deliberately stores
only:

- active membership rows and membership epoch;
- `(eventId)` / `(replicaId, replicaSeq)` dedupe keys;
- monotonically increasing `serverOrder`;
- per-replica cursors;
- compact JSON event log;
- hibernatable WebSocket sessions.

It does not contain cards, columns, appearance settings, PostgreSQL tables or
the domain merge policy.

## Local checks

```bash
npm ci
npm run typecheck
npm test
```

## First deployment

```bash
npx wrangler secret put COORDINATOR_ADMIN_TOKEN
npm run deploy
```

Provisioning and client request examples live in
`docs/deployment/free-hosting-transports-v1.md`. Do not put the admin token or
board tokens into `wrangler.jsonc`.
