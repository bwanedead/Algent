"""
Search ledger — one JSONL line per web search, so we can measure what the free stack buys us.

Lives at ``<runs_data>/search_ledger.jsonl``. Records only: ts, kind, the provider that answered (``"none"`` when
nothing did), the providers tried, cached flag, result count, elapsed ms and the query's LENGTH — never the
query text and never any result. Summarised by ``newsroom search-usage``; the questions it answers are "how
much do the free engines carry", "where do we still fall through to paid", and "where does search fail".

``providers_tried`` is the chain up to and including the answerer (or the whole chain when none answered):
earlier entries were skipped, circuit-open, capped or failed — the facade does not say which.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from algent_backend.agent_system.runs.control_plane.layout import runs_data_root

#: Answered from a paid or metered source (counted against caps / the run's cost meter).
_MODEL_PROVIDERS = frozenset({"muse"})


def ledger_path() -> Path:
    return runs_data_root() / "search_ledger.jsonl"


def record(*, kind: str, provider: str, tried: list[str], cached: bool, results: int,
           elapsed_ms: int, query_len: int) -> None:
    """Append one line; never raises (telemetry must not break a search)."""
    line = {"ts": datetime.now(UTC).isoformat(timespec="seconds"), "kind": kind, "provider": provider or "none",
            "tried": tried, "cached": cached, "n": results, "ms": elapsed_ms, "qlen": query_len}
    try:
        path = ledger_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line) + "\n")
    except OSError:
        pass


def record_result(kind: str, query: str, result: dict[str, Any], chain: list[str], *, cached: bool,
                  elapsed_ms: int) -> None:
    """Derive the ledger line from a facade result (``provider`` / ``results`` / ``error``)."""
    provider = str(result.get("provider") or "none") if not result.get("error") else "none"
    rows = result.get("results") or result.get("posts")
    n = len(rows) if isinstance(rows, list) else (rows if isinstance(rows, int) else 0)
    if provider == "library":                       # every open-web engine failed; our own index answered
        tried = [*chain, "library"]
    elif provider in chain:
        tried = chain[: chain.index(provider) + 1]
    else:
        tried = list(chain) if provider == "none" else [provider]
    record(kind=kind, provider=provider, tried=tried, cached=cached, results=n,
           elapsed_ms=elapsed_ms, query_len=len(query or ""))


def _load(path: Path, since: datetime) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    rows = []
    for raw in text.splitlines():
        try:
            row = json.loads(raw)
            if datetime.fromisoformat(row["ts"]) >= since:
                rows.append(row)
        except (ValueError, KeyError, TypeError):
            continue
    return rows


def _tier(provider: str, paid: frozenset[str]) -> str:
    if provider == "none":
        return "none"
    if provider in paid:
        return "paid"
    if provider in _MODEL_PROVIDERS:
        return "model"
    return "free"


def summarise(days: int = 7, *, path: Path | None = None, now: datetime | None = None) -> dict[str, Any]:
    """Searches by answering provider, free/paid share, failure rate, latency per provider, paid use vs caps."""
    from . import quota

    paid = frozenset(quota.MONTHLY_CAPS) | {"x"}
    since = (now or datetime.now(UTC)) - timedelta(days=days)
    rows = _load(path or ledger_path(), since)
    live = [r for r in rows if not r.get("cached")]
    total = len(live)
    by_provider: dict[str, list[int]] = defaultdict(list)
    for r in live:
        by_provider[r.get("provider", "none")].append(int(r.get("ms", 0)))
    tiers: dict[str, int] = defaultdict(int)
    for provider, lat in by_provider.items():
        tiers[_tier(provider, paid)] += len(lat)
    answered = total - len(by_provider.get("none", []))
    fell_through = sum(1 for r in live if r.get("provider") != "none" and len(r.get("tried") or []) > 1)

    def pct(n: int, d: int) -> float:
        return round(100.0 * n / d, 1) if d else 0.0

    return {
        "days": days, "searches": len(rows), "cached": len(rows) - total, "live": total,
        "by_provider": {p: {"n": len(lat), "share_pct": pct(len(lat), total),
                            "avg_ms": round(sum(lat) / len(lat)) if lat else 0}
                        for p, lat in sorted(by_provider.items(), key=lambda kv: -len(kv[1]))},
        "free_share_pct": pct(tiers["free"], total), "paid_share_pct": pct(tiers["paid"], total),
        "model_share_pct": pct(tiers["model"], total),
        "failure_rate_pct": pct(total - answered, total),
        "empty_result_pct": pct(sum(1 for r in live if r.get("provider") != "none" and not r.get("n")), total),
        "fell_through_pct": pct(fell_through, total),
        "paid_quota_this_month": quota.summary(),
    }
