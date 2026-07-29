#!/usr/bin/env python3
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
    if read("VERSION").strip() != "1.0.0-beta.6":
        raise SystemExit("FAIL: VERSION must be 1.0.0-beta.6")

    frontend = json.loads(read("frontend/package.json"))
    if frontend.get("version") != "1.0.0-beta.6":
        raise SystemExit("FAIL: frontend package version is not aligned")

    require(
        "backend/src/modules/cards/dto.rs",
        "checklist_item_count",
        "checklist_completed_item_count",
    )
    require(
        "backend/src/modules/activity/mod.rs",
        "/boards/{boardId}/productivity",
    )
    require(
        "backend/src/transports/roaming.rs",
        '"checklists"',
        "apply_checklist_bundle",
        "'checklistItemCount'",
    )
    require(
        "backend/migrations/0010_mobile_checklists_productivity_wallpapers.sql",
        "'image'",
        "'checklist_item'",
        "enqueue_roaming_card_activity",
    )
    require(
        "frontend/src/features/boards/pages/BoardPage.tsx",
        "card-checklist-progress",
        "ProductivityGraph",
    )
    require(
        "frontend/src/shared/appearance/theme.ts",
        "backgroundImage",
        "backgroundSize",
    )
    require(
        "docs/api/openapi.yaml",
        "/boards/{boardId}/productivity:",
        "checklistItemCount:",
        "- image",
    )
    print("OK: mobile/web features, migration, roaming payload and OpenAPI are aligned")


if __name__ == "__main__":
    main()
