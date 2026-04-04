# p2p-planner backend skeleton v1

## What is included
- axum-based bootable HTTP server
- config loading from `config/default.toml` + environment variables
- sqlx PostgreSQL pool
- startup migrations
- app state + tracing + error envelope
- modular router skeleton for `auth`, `users`, `workspaces`, `boards`, `cards`, `labels`, `checklists`, `comments`, `sync`, `audit`

## Run locally
1. Create PostgreSQL database `p2p_planner`
2. Copy `.env.example` to `.env` and adjust values if needed
3. Start backend:
   ```bash
   cargo run
   ```

Health endpoints:
- `GET /health`
- `GET /api/v1/health`

## Core CRUD during pre-auth stage
Until full auth/session handlers are implemented, core CRUD endpoints expect an `X-User-Id` header with an existing `users.id` UUID. This is a temporary bridge so workspaces/boards/columns/cards can already be exercised against the real PostgreSQL schema.

Smoke tests:
- `tests/core_crud_smoke.rs`
- integration tests are marked `#[ignore]` and require `TEST_DATABASE_URL` or `DATABASE_URL` pointing to PostgreSQL
