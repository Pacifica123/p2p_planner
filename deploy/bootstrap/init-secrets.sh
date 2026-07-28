#!/bin/sh
set -eu

SECRETS_DIR=/run/p2pkanban-secrets
mkdir -p "$SECRETS_DIR"
umask 077

generate_hex() {
  byte_count="$1"
  od -An -N "$byte_count" -tx1 /dev/urandom | tr -d ' \n'
}

generate_base64() {
  byte_count="$1"
  head -c "$byte_count" /dev/urandom | base64 | tr -d '\r\n'
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
ensure_secret "$SECRETS_DIR/nostr-secret-key" 32
if [ ! -s "$SECRETS_DIR/nostr-master-key" ]; then
  generate_base64 32 > "$SECRETS_DIR/nostr-master-key"
  printf '\n' >> "$SECRETS_DIR/nostr-master-key"
  chmod 0444 "$SECRETS_DIR/nostr-master-key"
fi
printf '2\n' > "$SECRETS_DIR/schema-version"
chmod 0444 "$SECRETS_DIR/schema-version"

echo "p2pKanban bootstrap secrets are ready."
