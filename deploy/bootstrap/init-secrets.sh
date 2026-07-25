#!/bin/sh
set -eu

SECRETS_DIR=/run/p2pkanban-secrets
mkdir -p "$SECRETS_DIR"
umask 077

generate_hex() {
  byte_count="$1"
  od -An -N "$byte_count" -tx1 /dev/urandom | tr -d ' \n'
}

ensure_secret() {
  target="$1"
  byte_count="$2"
  if [ -s "$target" ]; then
    return
  fi

  temporary="${target}.tmp.$$"
  generate_hex "$byte_count" > "$temporary"
  printf '\n' >> "$temporary"
  chmod 0444 "$temporary"
  mv "$temporary" "$target"
}

ensure_secret "$SECRETS_DIR/postgres-password" 32
ensure_secret "$SECRETS_DIR/jwt-secret" 64
printf '1\n' > "$SECRETS_DIR/schema-version"
chmod 0444 "$SECRETS_DIR/schema-version"

echo "p2pKanban bootstrap secrets are ready."
