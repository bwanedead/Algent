"""
The headline base — what the heat detector clusters and measures coverage against.

Our own headline radar is ~40 headlines on the days it runs and nothing on the days it does not, and it
reflects our sampling. A theater's heat read from it alone is the radar's opinion. So the base is three
SOURCE CLASSES, each tagged on every headline:

* ``radar``     — the radar editions (what our newsroom surfaced);
* ``wikipedia`` — Wikipedia's Current Events portal: events that happened, cited, global by construction;
* ``library``   — titles of recent documents in our own crawled trusted-source library (ministries,
                  wires, international bodies, think tanks).

A class that fails to load is simply absent (the base is best-effort; the radar alone is the old behaviour).

SHARES, NOT VOLUME. Coverage is measured per class as members / headlines of that class in the window
(``heat.measure`` then averages the classes that have data), so a class with ten times the volume does not
outvote the others and the radar's gaps do not read as a quiet world.

BOUNDING THE MODEL'S INPUT. Every headline is a line the clustering call must read and then cite by id.
Near-identical titles inside a class are dropped first (same content words: a reprint is one headline,
not two). The rest is cut to ``CLUSTER_LINE_BUDGET`` lines by water-filling: each class gets an equal share
of the budget and a class that needs less hands the surplus back to the others, so a small class is
shown whole and the large one is thinned, never the reverse. Within a class the cut is spread: days take
turns, and inside a day the class's own groups (library source, portal category, radar edition) take turns,
so one prolific feed or one busy day cannot fill the quota. The per-class, per-day count of what was
SHOWN is the denominator for shares: the model's sample is the population it was asked about.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from itertools import zip_longest
from typing import Any

RADAR, WIKIPEDIA, LIBRARY = "radar", "wikipedia", "library"
AI_SOURCES, AI_COMMUNITY = "ai_sources", "ai_community"        # the AI desk's classes (``domains.AI``)
CLASSES = (RADAR, WIKIPEDIA, LIBRARY)
AI_CLASSES = (AI_SOURCES, AI_COMMUNITY)

# ~600 lines is ~25k input tokens (a title plus a short thesis is ~40) and ~2k output tokens of ids: well
# inside one low-effort call, while a week of a 40-a-day radar, a day's portal and a thinned library fit.
CLUSTER_LINE_BUDGET = 600

_WORD = re.compile(r"[a-z0-9]+")

Head = dict[str, Any]       # {id, day, kind, edition, n, title, thesis, sources, group}
Loader = Callable[[int, date], list[Head]]


@dataclass
class Base:
    """The window's headlines as shown to the clusterer, and the per-class denominators."""

    heads: dict[str, Head] = field(default_factory=dict)                  # id -> head (shown lines only)
    sizes: dict[str, dict[str, int]] = field(default_factory=dict)        # class -> day -> shown headlines
    pool: dict[str, int] = field(default_factory=dict)                    # class -> headlines before the budget cut

    def summary(self) -> dict[str, dict[str, int]]:
        return {c: {"pool": self.pool.get(c, 0), "shown": sum(self.sizes.get(c, {}).values())}
                for c in (*CLASSES, *AI_CLASSES) if c in self.pool}


# ── loaders (best-effort; each returns heads of one class) ────────────────────────────────────
def radar_heads(editions: list[dict], *, days: int, today: date) -> list[Head]:
    start = today - timedelta(days=days - 1)
    out = []
    for e in editions:
        day = date.fromisoformat(e["slug"][:10])
        if start <= day <= today:
            for lead in e.get("leads") or []:
                out.append({"id": f"{e['slug']}#{lead['n']}", "day": day.isoformat(), "kind": RADAR,
                            "edition": e["slug"], "n": lead["n"], "title": lead.get("title", ""),
                            "thesis": lead.get("thesis", ""), "sources": lead.get("sources", []), "group": e["slug"]})
    return out


def wikipedia_heads(days: int, today: date) -> list[Head]:
    """Current Events entries for the window. Free (a few page reads); [] when the portal is unreachable."""
    from algent_backend.data_ingestion.newsroom.sources.wikipedia_events import fetch_current_events

    try:
        hits = fetch_current_events(days=days, now=datetime(today.year, today.month, today.day, 23, 59, tzinfo=UTC))
    except Exception:  # noqa: BLE001 - the base is an aid; a dead portal must not cost the board
        return []
    out = []
    for i, h in enumerate(hits, 1):
        day = h.get("seendate", "")
        if day:
            out.append({"id": f"wiki-{day}#{i}", "day": day, "kind": WIKIPEDIA, "edition": f"{day}-wiki", "n": i,
                        "title": h["title"], "thesis": "", "sources": [h["url"]], "group": h.get("category", "")})
    return out


def _library(days: int, today: date, *, ai: bool, kind: str, prefix: str) -> list[Head]:
    """Titles of the library's latest documents published in the window, from the AI sources (``ai``) or from all the others
    (a read-only query; [] when the library is absent)."""
    from algent_backend.library import store
    from algent_backend.library.ai_sources import AI_SOURCE_IDS

    conn: sqlite3.Connection | None = None
    try:
        conn = store.connect(create=False)
        if conn is None:
            return []
        start = (today - timedelta(days=days - 1)).isoformat()
        rows = conn.execute(
            "SELECT url, title, source_id, COALESCE(NULLIF(published,''), fetched_at) AS at FROM documents"
            " WHERE latest=1 AND title<>'' AND substr(COALESCE(NULLIF(published,''), fetched_at),1,10) >= ?"
            " ORDER BY at DESC", (start,)).fetchall()
    except Exception:  # noqa: BLE001
        return []
    finally:
        if conn is not None:
            conn.close()
    out = []
    for i, r in enumerate((r for r in rows if (r["source_id"] in AI_SOURCE_IDS) == ai), 1):
        day = r["at"][:10]
        if day <= today.isoformat():             # a feed's clock a day ahead is not the future
            out.append({"id": f"{prefix}-{day}#{i}", "day": day, "kind": kind, "edition": f"{day}-{kind}", "n": i,
                        "title": " ".join(r["title"].split()), "thesis": r["source_id"], "sources": [r["url"]],
                        "group": r["source_id"]})
    return out


def library_heads(days: int, today: date) -> list[Head]:
    """The geopolitics desk's library class: every crawled source except the AI desk's."""
    return _library(days, today, ai=False, kind=LIBRARY, prefix="lib")


def ai_library_heads(days: int, today: date) -> list[Head]:
    """The AI desk's main class: lab blogs, AI research and policy shops, AI trade press (``library/ai_sources``)."""
    return _library(days, today, ai=True, kind=AI_SOURCES, prefix="ai")


HN_URL = "https://hn.algolia.com/api/v1/search_by_date"
HN_QUERIES = ("LLM", "artificial intelligence", "AI model", "AI chips GPU", "AI regulation")
HN_MIN_POINTS = 40


def ai_community_heads(days: int, today: date) -> list[Head]:
    """What AI practitioners are discussing: Hacker News stories matching generic AI terms with real engagement (Algolia's public API,
    no key). Free; [] when unreachable."""
    import json

    from algent_backend import polite_http

    start = datetime(today.year, today.month, today.day, tzinfo=UTC) - timedelta(days=days - 1)
    seen: dict[str, Head] = {}
    for q in HN_QUERIES:
        try:
            payload = json.loads(polite_http.get(HN_URL, {"tags": "story", "query": q, "hitsPerPage": 60,
                                                          "numericFilters": f"points>{HN_MIN_POINTS},created_at_i>{int(start.timestamp())}"}))
        except Exception:  # noqa: BLE001 - the base is an aid
            continue
        for hit in payload.get("hits", []):
            oid, title = str(hit.get("objectID", "")), " ".join(str(hit.get("title") or "").split())
            day = str(hit.get("created_at", ""))[:10]
            if oid and title and day and day <= today.isoformat() and oid not in seen:
                seen[oid] = {"id": f"hn-{oid}", "day": day, "kind": AI_COMMUNITY, "edition": f"{day}-hn", "n": len(seen) + 1, "title": title,
                             "thesis": f"{hit.get('points', 0)} points", "sources": [hit.get("url") or f"https://news.ycombinator.com/item?id={oid}"],
                             "group": day}
    return list(seen.values())


def default_loaders() -> dict[str, Loader]:
    return {WIKIPEDIA: wikipedia_heads, LIBRARY: library_heads}


# ── assembly ──────────────────────────────────────────────────────────────────────────────────
def _key(title: str) -> frozenset[str]:
    return frozenset(w for w in _WORD.findall(title.lower()) if len(w) > 2 or w.isdigit())


def dedupe(heads: Iterable[Head]) -> list[Head]:
    """Drop titles with the same content words as an earlier one (a reprint is one headline)."""
    seen: set[frozenset[str]] = set()
    out = []
    for h in heads:
        k = _key(h["title"])
        if k and k in seen:
            continue
        seen.add(k)
        out.append(h)
    return out


def quotas(pool: dict[str, int], budget: int) -> dict[str, int]:
    """Water-filling: equal shares of ``budget``; a class smaller than its share keeps all it has and the
    surplus is re-split among the rest."""
    left, out, remaining = dict(pool), {}, budget
    while left:
        share = remaining // len(left)
        small = {c: n for c, n in left.items() if n <= share}
        if not small:
            out.update({c: share for c in left})
            break
        for c, n in small.items():
            out[c] = n
            remaining -= n
            del left[c]
    return out


def spread(heads: list[Head], quota: int) -> list[Head]:
    """``quota`` heads, days taking turns (newest first) and, inside a day, groups taking turns."""
    if len(heads) <= quota:
        return heads
    by_day: dict[str, dict[str, list[Head]]] = {}
    for h in heads:
        by_day.setdefault(h["day"], {}).setdefault(h["group"], []).append(h)
    lanes = []
    for day in sorted(by_day, reverse=True):
        groups = list(by_day[day].values())
        lanes.append([h for row in zip_longest(*groups) for h in row if h is not None])
    picked = [h for row in zip_longest(*lanes) for h in row if h is not None][:quota]
    return sorted(picked, key=lambda h: (h["day"], h["id"]))


def assemble(editions: list[dict], *, days: int, today: date | None = None,
             loaders: dict[str, Loader] | None = None, budget: int = CLUSTER_LINE_BUDGET) -> Base:
    """The window's base: radar editions plus whatever ``loaders`` (class -> loader) return."""
    # With outside classes loaded the window ends today (the radar may not have run: its newest edition is not "now").
    last = today or (date.today() if loaders else
                     max((date.fromisoformat(e["slug"][:10]) for e in editions), default=date.today()))
    classes: dict[str, list[Head]] = {RADAR: radar_heads(editions, days=days, today=last)}
    for cls, load in (loaders or {}).items():
        classes[cls] = load(days, last)
    classes = {c: dedupe(hs) for c, hs in classes.items()}
    classes = {c: hs for c, hs in classes.items() if hs or c == RADAR}
    take = quotas({c: len(hs) for c, hs in classes.items()}, budget)
    base = Base(pool={c: len(hs) for c, hs in classes.items()})
    for cls, hs in classes.items():
        shown = spread(hs, take[cls])
        base.sizes[cls] = {}
        for h in shown:
            base.heads[h["id"]] = h
            base.sizes[cls][h["day"]] = base.sizes[cls].get(h["day"], 0) + 1
    return base
