"""
Cross-source dedupe — the same event listed by two sources is one item that cites both.

Two items are the same event when they share a kind family, their days overlap, and their titles say the same thing: after dropping
filler words, one title's words are (almost) all in the other's (overlap coefficient >= ``SAME``), and when both name countries those
sets intersect. The survivor is the most trusted (grade, then the one with a window, then the earlier first_seen); it absorbs the
countries, theaters and situations of the others and lists every source in ``sources``. Items of one source never merge with each
other (two Fed meetings a week apart are two meetings), and the weekly stock reports are never compared (same title by design).
"""

from __future__ import annotations

import re
from collections import defaultdict

from .contracts import GRADE_RANK, CalendarItem

SAME = 0.6
_FILLER = {"the", "a", "an", "of", "and", "in", "on", "at", "for", "to", "s", "will", "be", "by", "with", "vs", "v"}
_FAMILY = {"election": "vote", "vote": "vote", "summit": "meet", "conference": "meet", "court": "court"}


def _words(title: str) -> frozenset[str]:
    return frozenset(w for w in re.findall(r"[a-z0-9]+", title.casefold()) if w not in _FILLER and len(w) > 1)


def _span(i: CalendarItem) -> tuple[str, str]:
    return i.date, i.end_date or i.date


def same_event(a: CalendarItem, b: CalendarItem) -> bool:
    if a.source == b.source or _FAMILY.get(a.kind, a.kind) != _FAMILY.get(b.kind, b.kind):
        return False
    (a0, a1), (b0, b1) = _span(a), _span(b)
    if a1 < b0 or b1 < a0:
        return False
    if a.countries and b.countries and not set(a.countries) & set(b.countries):
        return False
    wa, wb = _words(a.title), _words(b.title)
    return bool(wa and wb) and len(wa & wb) / min(len(wa), len(wb)) >= SAME


def _rank(i: CalendarItem) -> tuple:
    return (GRADE_RANK.get(i.grade, 0), bool(i.end_date), i.source != "corpus", -len(i.title))


def _cite(i: CalendarItem) -> list[dict[str, str]]:
    return i.sources or [{"source": i.source, "url": i.source_url}]


def merge(items: list[CalendarItem]) -> list[CalendarItem]:
    by_day: dict[str, list[int]] = defaultdict(list)
    for n, i in enumerate(items):
        by_day[i.date].append(n)
    parent = list(range(len(items)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for n, a in enumerate(items):
        if a.kind == "commodity_report" and a.source.startswith("eia_"):
            continue
        for day in {a.date, a.end_date or a.date}:
            for m in by_day.get(day, []):
                if m > n and same_event(a, items[m]):
                    parent[find(m)] = find(n)
    groups: dict[int, list[CalendarItem]] = defaultdict(list)
    for n, i in enumerate(items):
        groups[find(n)].append(i)
    out = []
    for grp in groups.values():
        best = max(grp, key=_rank)
        if len(grp) == 1:
            out.append(best)
            continue
        seen: dict[str, dict[str, str]] = {}
        for g in sorted(grp, key=_rank, reverse=True):
            for c in _cite(g):
                seen.setdefault(c["source"], c)
        out.append(best.model_copy(update={
            "countries": sorted({c for g in grp for c in g.countries}), "theaters": sorted({t for g in grp for t in g.theaters}),
            "situations": sorted({s for g in grp for s in g.situations}), "sources": list(seen.values())}))
    return sorted(out, key=lambda i: (i.date, i.id))
