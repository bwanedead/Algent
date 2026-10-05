"""
Collector — run the providers and append what is new to the store.

One series at a time, each isolated: a provider being down, blocked (needs a key) or returning
something unparseable is recorded in the report and never stops the others. If a provider's FIRST
series of the run fails at the network level, the rest of that provider's series are skipped for
this run (they would only repeat the same retries); a later series failing alone is just that
series' problem (a bad symbol, say).

Window: a normal fetch asks each provider for everything since a little before the newest stored
period (the overlap is what lets revisions show up); a first fetch with nothing stored takes the
provider's default recent window. ``backfill`` asks for ``BACKFILL_DAYS`` of history — bounded so a
one-off fill stays a few dozen polite requests, not an archive crawl.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from . import store
from .catalog import CATALOG, get_series
from .contracts import Series, period_date
from algent_backend.polite_http import SourceError, SourceUnavailable
from .sources import PROVIDERS

BACKFILL_DAYS = 5 * 365
OVERLAP_DAYS = 14


def _since(series: Series, backfill: bool, today: date) -> date | None:
    if backfill:
        return today - timedelta(days=BACKFILL_DAYS)
    hist = store.history(series.id)
    return period_date(hist[-1].period) - timedelta(days=OVERLAP_DAYS) if hist else None


def collect(series_ids: list[str] | None = None, *, backfill: bool = False, today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    todo = [get_series(i) for i in series_ids] if series_ids else CATALOG
    down: set[str] = set()
    worked: set[str] = set()
    rows: list[dict[str, Any]] = []
    for s in todo:
        row: dict[str, Any] = {"id": s.id, "provider": s.fetcher}
        if s.fetcher in down:
            rows.append({**row, "status": "skipped", "error": "provider failed earlier in this run"})
            continue
        try:
            obs = PROVIDERS[s.fetcher](s, _since(s, backfill, today))
            res = store.append(s.id, obs)
            worked.add(s.fetcher)
            rows.append({**row, "status": "ok", "fetched": len(obs), **res.model_dump()})
        except SourceUnavailable as exc:
            down.add(s.fetcher)
            rows.append({**row, "status": "blocked", "error": str(exc)})
        except SourceError as exc:
            if s.fetcher not in worked:
                down.add(s.fetcher)
            rows.append({**row, "status": "error", "error": str(exc)})
        except Exception as exc:   # a parser/shape surprise must not take the other providers down
            rows.append({**row, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
    tally = {st: sum(r["status"] == st for r in rows) for st in ("ok", "blocked", "error", "skipped")}
    return {"backfill": backfill, "as_of": today.isoformat(), **tally, "series": rows}
