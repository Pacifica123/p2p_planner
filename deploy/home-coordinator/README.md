# Home coordinator over Tailscale

This profile runs the current Rust coordinator and PostgreSQL on an old Linux
laptop or mini-PC. Only the Tailscale network namespace is exposed; PostgreSQL
has no host port.

## Start

```bash
cd deploy/home-coordinator
cp home-coordinator.example.env runtime.env
# Edit runtime.env. Never commit it.
docker compose --env-file runtime.env up -d --build
```

If no auth key was provided:

```bash
docker compose --env-file runtime.env exec tailscale tailscale up
```

Expose the API through Tailscale HTTPS so secure refresh cookies continue to
work:

```bash
docker compose --env-file runtime.env exec tailscale \
  tailscale serve --bg --https=443 http://127.0.0.1:18080
```

Then configure each client with:

```text
VITE_API_BASE_URL=https://p2p-kanban-home.<tailnet-name>.ts.net/api/v1
```

## Backups

The named volume `postgres_data` is the canonical coordinator state. Back it up
with `pg_dump`; do not treat the Tailscale state volume as a data backup. The
Nostr shadow outbox can later mirror accepted events, but it is not a substitute
for testing PostgreSQL restore until the relay-only recovery gate has passed.

To test the shadow mirror on the same machine, fill the `NOSTR_*` values in
`runtime.env`, keep at least three independent relays, set
`NOSTR_SHADOW_ENABLED=true` and follow the recovery gate in
`../../docs/deployment/free-hosting-transports-v1.md`. The compose profile
passes those values only to the backend container.
