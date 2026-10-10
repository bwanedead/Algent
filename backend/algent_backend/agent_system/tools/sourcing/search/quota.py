"""
Monthly caps on the PAID search and read services — insurance that free tiers are never drained.

The free engines (our SearXNG, DDG, Bing, Google News) answer first; a paid engine is reached only when they
all failed. This ledger makes that last resort bounded too: every paid call is counted per calendar month and
an engine refuses itself once its month's cap is spent, so a bad day (a blocked free engine, a looping agent)
costs at most the cap, never the plan. October 2026 is why: one engine's block handed a run's searches to
Tavily and the month's credits ran out.

Caps are standing operator knobs (edit them here, not in ``.env``); set a provider to 0 to switch it off.
State lives in ``runs_data/paid_quota.json`` (``{"YYYY-MM": {provider: count}}``) — mechanics only.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

#: Calls per calendar month. Set near each free plan's monthly allowance, with headroom; raise if you buy more.
MONTHLY_CAPS: dict[str, int] = {
    "tavily": 800,      # free plan: 1,000 credits/month
    "exa": 300,
    "brave": 1500,      # free plan: 2,000 queries/month (when a key is configured)
    "firecrawl": 400,   # free plan: 500 pages/month
}

_lock = threading.Lock()


def _path() -> Path:
    from algent_backend.agent_system.runs.control_plane.layout import runs_data_root

    return Path(runs_data_root()) / "paid_quota.json"


def _month(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).strftime("%Y-%m")


def _load() -> dict[str, dict[str, int]]:
    try:
        return json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def used(provider: str, *, now: datetime | None = None) -> int:
    return int(_load().get(_month(now), {}).get(provider, 0))


def allow(provider: str, *, now: datetime | None = None) -> bool:
    """False once ``provider`` has spent its month's cap. Unknown providers are not capped here."""
    cap = MONTHLY_CAPS.get(provider)
    return cap is None or used(provider, now=now) < cap


def spend(provider: str, n: int = 1, *, now: datetime | None = None) -> None:
    """Count ``n`` paid calls for this month (only for capped providers)."""
    if provider not in MONTHLY_CAPS:
        return
    with _lock:
        data = _load()
        month = data.setdefault(_month(now), {})
        month[provider] = int(month.get(provider, 0)) + n
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def summary(*, now: datetime | None = None) -> dict[str, dict[str, int]]:
    """This month's use against each cap, for ``newsroom reads``."""
    return {p: {"used": used(p, now=now), "cap": cap} for p, cap in MONTHLY_CAPS.items()}
