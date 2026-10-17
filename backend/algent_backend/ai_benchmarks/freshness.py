"""
Per-source freshness — is each source still being collected, and is it still publishing?

Three independent ways a source goes bad, each reported by name so the doctor and the site can say which:
* ``not fetched``  — no good fetch within ``flags.STALE_HOURS`` (the timer stopped, the host is down);
* ``broken``       — the last fetch failed to parse or shrank below ``flags.MIN_KEEP_FRACTION`` (the format changed);
* ``not updating`` — the newest result the source carries is older than its own allowance (upstream stopped publishing).
Pure functions of the status file; the page reads the same rows from the published document.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from . import flags, store
from .sources import INFO


def _age_hours(iso: str, now: datetime) -> float | None:
    try:
        return (now - datetime.fromisoformat(iso)).total_seconds() / 3600
    except ValueError:
        return None


def source_health(now: datetime | None = None, status: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now(UTC)
    status = status if status is not None else store.load_status()
    rows = []
    for src, st in sorted(status.items()):
        age = _age_hours(st.get("last_ok", ""), now) if st.get("last_ok") else None
        newest = st.get("newest_result", "")
        newest_age = None
        if newest:
            try:
                newest_age = (now.date() - date.fromisoformat(newest)).days
            except ValueError:
                pass
        limit = (flags.NEWEST_STALE_DAYS.get(src, flags.DEFAULT_NEWEST_STALE_DAYS))
        reasons = []
        if src != "self_reported":
            if age is None:
                reasons.append("never fetched")
            elif age > flags.STALE_HOURS:
                reasons.append(f"not fetched for {age:.0f} h")
            if newest_age is not None and newest_age > limit:
                reasons.append(f"not updating upstream (newest result {newest_age} days old)")
        elif age is not None and age > 24 * 3:
            reasons.append(f"discovery has not run for {age:.0f} h")
        if st.get("broken"):
            reasons.append(f"format changed or unreadable: {st.get('last_error', '')[:140]}")
        rows.append({"source": src, "name": INFO.get(src, (src,))[0], "last_ok": st.get("last_ok", ""), "last_error": st.get("last_error", ""),
                     "rows": st.get("rows", 0), "newest_result": newest, "stale": bool(reasons), "reasons": reasons})
    return rows
