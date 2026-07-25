#!/bin/sh
set -eu

SECRETS_DIR=/run/p2pkanban-secrets

read_secret() {
  path="$1"
  if [ ! -s "$path" ]; then
    echo "Required bootstrap secret is missing: $path" >&2
    exit 1
  fi
  tr -d '\r\n' < "$path"
}

postgres_password="$(read_secret "$SECRETS_DIR/postgres-password")"
jwt_secret="$(read_secret "$SECRETS_DIR/jwt-secret")"

export DATABASE__URL="postgres://p2pkanban:${postgres_password}@postgres:5432/p2pkanban"
export AUTH__JWT_SECRET="$jwt_secret"

unset postgres_password jwt_secret
exec /usr/local/bin/p2p-planner-backend "$@"
