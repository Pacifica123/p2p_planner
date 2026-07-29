#!/usr/bin/env python3
"""Проверяет статический контракт Android -> coordinator -> web для beta.6."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def require(relative: str, *needles: str) -> None:
    content = read(relative)
    missing = [needle for needle in needles if needle not in content]
    if missing:
        raise SystemExit(f"FAIL: {relative} is missing: {', '.join(missing)}")


def main() -> None:
    version = read("VERSION").strip()
    frontend = json.loads(read("frontend/package.json"))
    if version != "1.0.0-beta.6" or frontend.get("version") != version:
        raise SystemExit("FAIL: beta.6 versions are not aligned")

    require(
        "backend/src/modules/cards/service.rs",
        "pub(crate) fn normalize_status",
        '"todo" | "in_progress" | "blocked"',
        '"done"',
    )
    require(
        "backend/src/transports/roaming.rs",
        "normalized_card_status",
        "insert into checklists",
        "insert into checklist_items",
        "not (id = any($2::uuid[]))",
        "insert into activity_entries",
        '"source": "roaming"',
    )
    require(
        "backend/migrations/0012_roaming_activity_echo_guard.sql",
        "payload_jsonb ->> 'source'",
        "= 'roaming'",
        "return new",
    )
    require(
        "frontend/src/features/cards/hooks/useCards.ts",
        "refetchInterval: 3_000",
        "refetchInterval: 4_000",
    )
    require(
        "frontend/src/features/checklists/hooks/useChecklists.ts",
        "refetchInterval: 4_000",
    )
    require(
        "frontend/src/features/comments/hooks/useComments.ts",
        "refetchInterval: 5_000",
    )
    require(
        "frontend/src/features/labels/hooks/useLabels.ts",
        "refetchInterval: 5_000",
    )
    require(
        "docs/product/github-devctl-project-integration-concept-v1.md",
        "```mermaid",
        ".p2pkanban/project.json",
        "EvidenceReceipt",
        "receiptId",
    )
    require(
        "docs/product/stable-v1-readiness-2026-07-29.md",
        "Android → web",
        "full-local-release",
        "Вердикт: функционально близко, релизно ещё не готово",
    )
    print("OK: roaming ingest, web refresh, release audit and integration concept are aligned")


if __name__ == "__main__":
    main()
