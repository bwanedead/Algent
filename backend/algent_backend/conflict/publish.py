"""
Publish the attack log as documents (the site reads documents, never tables: docs/architecture/published-content.md).

    conflict/recent.json          the newest ``RECENT_DAYS`` days, the strongest ``RECENT_MAX`` events (curated and fatal first, then most-reported), the per-day
                                  counts of the last ``COUNT_DAYS`` days over the WHOLE stored record, which sources are live, and each source's coverage note
    conflict/country/<ISO>.json   one country's strongest events of the last ``COUNTRY_DAYS`` days (its globe panel / country view)

Built from the local store in one streaming pass (a shard is never held whole), so the stored record stays the single source and the documents are
rebuildable at will. A document that did not change hashes the same and costs no request (``publishing/object_docs``). Never raises: the local record
is the record, publishing is an addition.
"""

from __future__ import annotations

import heapq
from datetime import date
from typing import Any

from algent_backend.publishing import site_data

from . import flags, store
from .contracts import COVERAGE, SOURCES, ConflictEvent

#: The keyed sources: built and inactive until the operator adds the key (docs/credentials.md). ``active`` in the document says which are producing.
KEYED = ("reliefweb", "acled", "ucdp")


def row(e: ConflictEvent) -> dict[str, Any]:
    """One event as the site reads it. ``coverage_note`` is per source (document level), not repeated on 1,200 rows."""
    return {"id": e.id, "source": e.source, "on_date": e.date, "type": e.type, "lat": e.lat, "lon": e.lon, "place": e.place, "country": e.country,
            "actor1": e.actor1, "actor2": e.actor2, "fatalities": e.fatalities, "articles": e.articles, "title": e.title, "urls": e.urls,
            "coding": e.coding, "confidence": e.confidence, "basis": e.basis, "assets": [a.model_dump() for a in e.assets]}


def strength(e: ConflictEvent) -> tuple:
    return (e.coding == "curated", e.fatalities or 0, e.articles, e.date, e.id)


class _Top:
    """The strongest ``n`` events seen so far (a bounded min-heap): memory is ``n`` events however long the stream is."""

    def __init__(self, n: int) -> None:
        self.n, self.heap, self.seen = n, [], 0

    def add(self, e: ConflictEvent) -> None:
        self.seen += 1
        item = (strength(e), e.id, e)
        if len(self.heap) < self.n:
            heapq.heappush(self.heap, item)
        elif item[0] > self.heap[0][0]:
            heapq.heapreplace(self.heap, item)

    def rows(self) -> list[dict[str, Any]]:
        """Newest day first, strongest first within a day (the order every reader wants)."""
        ordered = sorted((x[2] for x in self.heap), key=strength, reverse=True)
        return [row(e) for e in sorted(ordered, key=lambda e: e.date, reverse=True)]


def source_state() -> dict[str, dict[str, Any]]:
    st = store.load_status()
    out = {}
    for src in SOURCES:
        s = st.get(src, {})
        out[src] = {"keyed": src in KEYED, "active": bool(s.get("last_ok")) and not s.get("needs_key"), "last_ok": s.get("last_ok", "")}
    return out


def documents(today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    recent, countries, country_newest = _Top(flags.RECENT_MAX), {}, {}
    recent_floor = (today.toordinal() - flags.RECENT_DAYS)
    newest = ""
    for e in store.iter_events(max(flags.COUNTRY_DAYS, flags.RECENT_DAYS), today):
        newest = max(newest, e.observed_at)
        if date.fromisoformat(e.date).toordinal() >= recent_floor:
            recent.add(e)
        if len(e.country) == 2 and (e.country == e.country.upper()):
            countries.setdefault(e.country, _Top(flags.COUNTRY_MAX)).add(e)
            country_newest[e.country] = max(country_newest.get(e.country, ""), e.observed_at)
    by_day = store.day_counts(flags.COUNT_DAYS, today)
    in_window = sum(v["events"] for d, v in by_day.items() if date.fromisoformat(d).toordinal() >= recent_floor)
    docs: dict[str, Any] = {"conflict/recent.json": {
        "as_of": newest, "since": store.collecting_since(), "window_days": flags.RECENT_DAYS, "total": in_window, "shown": len(recent.heap),
        "capped": in_window > len(recent.heap), "by_day": by_day, "sources": source_state(), "coverage": COVERAGE, "rows": recent.rows()}}
    # A country's as_of is ITS newest event, not the feed's: the global stamp moves every 15 minutes and would rewrite all ~150 country
    # documents each pass (most of the R2 write budget, 2026-10-28) when only the countries with new events changed.
    for iso, top in sorted(countries.items()):
        docs[f"conflict/country/{iso}.json"] = {"iso": iso, "as_of": country_newest[iso], "window_days": flags.COUNTRY_DAYS, "total": top.seen,
                                                "capped": top.seen > len(top.heap), "rows": top.rows()}
    return docs


def publish(*, today: date | None = None, http: Any = None) -> dict[str, Any]:
    return site_data.publish_built(lambda: documents(today), http=http)
