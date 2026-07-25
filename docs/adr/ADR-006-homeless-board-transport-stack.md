# ADR-006: Homeless board transport stack

Status: accepted for staged implementation, 2026-07-25.

## Context

p2pKanban must let several devices work with one board without making a
subscription VPS the permanent owner of the data. The current implementation is
local-first at the client boundary but still uses one Rust/PostgreSQL
coordinator for authorization, dedupe, cursor and `serverOrder`.

BitTorrent, IPFS and direct WebRTC do not by themselves deliver small changes
between users who are never online at the same time. Git hosting can store
encrypted batches but is a poor low-latency multiwriter event queue.

## Decision

Adopt a staged, replaceable stack:

1. Current Rust/PostgreSQL coordinator can run on a home machine reachable over
   Tailscale.
2. Sync event shape, deterministic ordering and envelope authentication live in
   the independent `backend/crates/sync-core` crate.
3. Accepted events are copied through a PostgreSQL outbox to at least three
   Nostr relays. Relay payloads are authenticated and encrypted; Nostr is a
   shadow store-and-forward path, not the authority.
4. Iroh carries the same signed envelope directly between online peers. Delivery
   speed does not affect merge results.
5. A separate Cloudflare Durable Object may replace only the compatibility
   coordinator surface: membership, dedupe, cursor, `serverOrder`, WebSocket and
   compact event log.

The existing domain backend and PostgreSQL projections are not moved into the
Durable Object.

## Invariants

- A transport cannot decide a same-field conflict.
- Network delivery can be duplicated and reordered.
- `eventId` and `(replicaId, replicaSeq)` remain idempotency keys.
- Nostr or Iroh failure must not reject an event already accepted by the current
  coordinator.
- Nostr relays never receive plaintext workspace IDs or domain payloads.
- `serverOrder` is compatibility delivery order, not the semantic merge winner.
- Secrets are runtime configuration and must not enter Git or devctl payloads.

## Consequences

The first usable deployment remains coordinator-backed. Nostr recovery can now
be tested without making relay availability part of the write path. Iroh is an
implemented Rust adapter but needs a Rust-capable desktop/mobile client runtime
before the web UI can use it. The Durable Object is deployable, but it is not
authorization-equivalent to the Rust backend until client signatures and
owner-signed membership epochs are implemented.

Coordinator-free mode remains a separate decision.
