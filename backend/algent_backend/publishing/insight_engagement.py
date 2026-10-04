"""Engagement snapshots for insight posts — what worked, not a vanity dashboard."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from algent_backend.agent_system.runs.control_plane.fsio import atomic_write_text
from algent_backend.publishing.x_client import tweet_public_metrics

_LOG = Path("runs_data") / "insight_engagement.jsonl"


def log_path() -> Path:
    return _LOG


def fetch_metrics(ids: list[str]) -> list[dict[str, Any]]:
    return tweet_public_metrics(ids)


def append_snapshots(rows: list[dict[str, Any]], *, path: Path | None = None) -> int:
    if not rows:
        return 0
    p = path or log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).isoformat()
    existing = p.read_text(encoding="utf-8") if p.exists() else ""
    extra = "".join(
        json.dumps({**row, "collected_at": now}, ensure_ascii=False) + "\n" for row in rows
    )
    atomic_write_text(p, existing + extra)
    return len(rows)


def tweet_id_from_url(url: str) -> str:
    text = (url or "").rstrip("/")
    if "/status/" not in text:
        return ""
    return text.rsplit("/status/", 1)[-1].split("?")[0].strip()
