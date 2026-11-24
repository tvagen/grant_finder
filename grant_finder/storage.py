"""Local JSON storage for cached grants, shortlist/bookmarks, and custom RSS feeds."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from grant_finder.models import Grant, SourceStatus
from grant_finder.scoring import score_and_tag_grant

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CACHE_FILE = DATA_DIR / "grants_cache.json"
SHORTLIST_FILE = DATA_DIR / "shortlist.json"
CUSTOM_FEEDS_FILE = DATA_DIR / "custom_feeds.json"


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def save_cache(grants: list[Grant], statuses: list[SourceStatus]) -> None:
    _ensure_data_dir()
    payload = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "grants": [g.to_dict() for g in grants],
        "statuses": [s.to_dict() for s in statuses],
    }
    CACHE_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_cache() -> tuple[list[Grant], list[SourceStatus], str]:
    if not CACHE_FILE.exists():
        return [], [], ""
    try:
        payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        grants = [Grant.from_dict(d) for d in payload.get("grants", [])]
        # Backfill geography/themes if loading an older cache schema
        for g in grants:
            if not g.regions:
                score_and_tag_grant(g)
        statuses = [SourceStatus.from_dict(s) for s in payload.get("statuses", [])]
        updated_at = payload.get("updated_at", "")
        return grants, statuses, updated_at
    except Exception:
        return [], [], ""


def load_shortlist() -> dict[str, dict[str, Any]]:
    if not SHORTLIST_FILE.exists():
        return {}
    try:
        return json.loads(SHORTLIST_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_shortlist(shortlist: dict[str, dict[str, Any]]) -> None:
    _ensure_data_dir()
    SHORTLIST_FILE.write_text(
        json.dumps(shortlist, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_custom_feeds() -> list[dict[str, str]]:
    if not CUSTOM_FEEDS_FILE.exists():
        return []
    try:
        data = json.loads(CUSTOM_FEEDS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_custom_feeds(feeds: list[dict[str, str]]) -> None:
    _ensure_data_dir()
    CUSTOM_FEEDS_FILE.write_text(
        json.dumps(feeds, indent=2, ensure_ascii=False), encoding="utf-8"
    )
