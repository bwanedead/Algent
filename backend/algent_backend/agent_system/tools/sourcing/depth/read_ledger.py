"""
Read ledger — one JSONL line per page read, so we can see which ladder rung actually rescues pages.

Lives at ``<runs_data>/read_ledger.jsonl``. Records only: ts, domain, final ``via``, ``quality``,
rungs tried, elapsed ms, ``not_found`` — never page content or URL paths/queries. Summarised by
``newsroom reads``; the question it answers is "is Playwright (or Firecrawl) worth its cost?".
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from algent_backend.agent_system.runs.control_plane.layout import runs_data_root

_PAID_OR_HEAVY = ("firecrawl", "playwright")


def ledger_path() -> Path:
    return runs_data_root() / "read_ledger.jsonl"


def record(url: str, *, via: str, quality: str, rungs: list[str], elapsed_ms: int,
           not_found: bool = False) -> None:
    """Append one line; never raises (telemetry must not break a read)."""
    line = {
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "domain": (urlsplit(url).hostname or "").lower(),
        "via": via, "quality": quality, "rungs": rungs,
        "ms": elapsed_ms, "not_found": not_found,
    }
    try:
        path = ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line) + "\n")
    except OSError:
        pass


def _load(path: Path, since: datetime) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return rows
    for raw in text.splitlines():
        try:
            row = json.loads(raw)
            if datetime.fromisoformat(row["ts"]) >= since:
                rows.append(row)
        except (ValueError, KeyError, TypeError):
            continue
    return rows


def summarise(days: int = 7, *, path: Path | None = None, now: datetime | None = None) -> dict[str, Any]:
    """Share of reads by final rung, failure rate, worst domains, and what only paid/heavy rungs saved."""
    since = (now or datetime.now(UTC)) - timedelta(days=days)
    rows = _load(path or ledger_path(), since)
    total = len(rows)
    ok = [r for r in rows if r.get("quality") == "good" and not r.get("not_found")]
    failed = [r for r in rows if r.get("quality") != "good"]  # includes not_found
    real_failures = [r for r in failed if not r.get("not_found")]
    by_rung = Counter(r.get("via", "none") for r in ok)
    rescued = Counter(r["via"] for r in ok if r.get("via") in _PAID_OR_HEAVY)
    free_rescued = Counter(r["via"] for r in ok if r.get("via") in ("jina", "wayback"))
    return {
        "days": days, "reads": total,
        "good_by_rung": dict(by_rung.most_common()),
        "good_share_by_rung": {k: round(v / total, 3) for k, v in by_rung.items()} if total else {},
        "failure_rate": round(len(failed) / total, 3) if total else 0.0,
        "not_found": len(failed) - len(real_failures),
        "top_failing_domains": Counter(r.get("domain", "") for r in real_failures).most_common(10),
        "rescued_only_by_paid_or_playwright": dict(rescued),
        "rescued_by_free_rungs": dict(free_rescued),
    }
