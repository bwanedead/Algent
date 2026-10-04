"""
The dossier's timeline: every development the desk ever reported on a theater, as one newest-first list
with repeats merged. Pure functions over plain dicts.

A theater's daily reports re-cover the same event on consecutive days, usually reworded, and a brief's
timeline often restates something a daily already carried. Shown raw, the timeline would say the same
thing four times. So near-duplicates are merged, and the rule is deliberately conservative: merging
two different events loses a fact, leaving two similar lines only costs a glance.

MERGE RULE. Two items merge into one entry when ALL hold:
  1. their dates are the same day or adjacent days (|delta| <= 1 day);
  2. they come from different reports (a report never merges two of its own developments: the writer
     kept those apart on purpose); and
  3. their wording is close: the cosine similarity of their tf-idf vectors over headline + detail is at
     least ``SIMILARITY`` (0.2) AND they share at least ``MIN_SHARED`` (3) content words. Content words are
     lower-case alphanumerics of 3+ characters (numbers kept whole, "15,500" -> "15500"), stopwords
     removed. The idf is computed over the theater's own entries, so words that run through the whole
     dynamic ("Russian", "drones") count for little and the distinctive ones (a place, a figure) decide.
     On the real stores, genuine repeats scored 0.23-0.5 and different events below 0.2.
The surviving entry is the best member, chosen by: researched before reported, then the most detail
(headline + detail length), then the newest. Its text, date, place and origin are kept; its
``verification`` is "researched" if ANY member was researched; ``sources`` is the union of every member's
http(s) sources (the survivor's first, then newer members', order preserved, no repeats).
The rule errs toward keeping two lines: merging two different events loses a fact, a leftover near-repeat
only costs a glance.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any

SIMILARITY = 0.2
MIN_SHARED = 3
ADJACENT_DAYS = 1
_WORD = re.compile(r"[a-z0-9]+(?:[,.][0-9]+)*")
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")
_STOP = frozenset("""
the and for with from that this has have had are was were will its into over after before amid new
says said say not but also than their they them his her who what when where how out off per via
""".split())
_RANK = {"researched": 1, "reported": 0}


def terms(text: str) -> Counter:
    """Content-word counts of ``text`` (see the merge rule)."""
    words = (w.replace(",", "") for w in _WORD.findall((text or "").lower()))
    return Counter(w for w in words if len(w) >= 3 and w not in _STOP)


def _cosine(a: Counter, b: Counter, idf: dict[str, float]) -> float:
    wa = {w: (1 + math.log(c)) * idf[w] for w, c in a.items()}
    wb = {w: (1 + math.log(c)) * idf[w] for w, c in b.items()}
    na, nb = math.sqrt(sum(x * x for x in wa.values())), math.sqrt(sum(x * x for x in wb.values()))
    return sum(x * wb[w] for w, x in wa.items() if w in wb) / (na * nb) if na and nb else 0.0


def day_of(text: str, fallback: str) -> str:
    """The first YYYY-MM-DD in ``text`` (a development's ``when`` may be a range or empty), else ``fallback``."""
    m = _ISO.search(text or "")
    if not m:
        return fallback
    try:
        date.fromisoformat(m.group(0))
    except ValueError:
        return fallback
    return m.group(0)


def _gap(a: str, b: str) -> int:
    try:
        return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)
    except ValueError:
        return 10**6


@dataclass
class Entry:
    """One timeline line before merging. ``origin`` is the page it came from (``/geopolitics/<date>`` or
    ``/intel/briefs/<slug>``)."""

    date: str
    headline: str
    detail: str = ""
    where: str = ""
    verification: str = "reported"
    sources: list[str] = field(default_factory=list)
    origin: str = ""
    terms: Counter = field(default_factory=Counter)

    def __post_init__(self) -> None:
        if not self.terms:
            self.terms = terms(f"{self.headline} {self.detail}")

    @property
    def weight(self) -> tuple[int, int, str]:
        return (_RANK.get(self.verification, 0), len(self.headline) + len(self.detail), self.date)


def _merged(members: list[Entry]) -> Entry:
    best = max(members, key=lambda e: e.weight)
    sources: list[str] = []
    for e in [best, *sorted((m for m in members if m is not best), key=lambda m: m.date, reverse=True)]:
        sources.extend(u for u in e.sources if u not in sources)
    verification = "researched" if any(m.verification == "researched" for m in members) else best.verification
    where = best.where or next((m.where for m in members if m.where), "")
    return Entry(best.date, best.headline, best.detail, where, verification, sources, best.origin, best.terms)


def merge(entries: list[Entry]) -> list[dict[str, Any]]:
    """Merge near-duplicates (see the module docstring) and return the timeline newest first, as the
    contract's ``timeline`` rows."""
    df = Counter(w for e in entries for w in e.terms)
    idf = {w: math.log(1 + len(entries) / c) for w, c in df.items()}

    def same(m: Entry, e: Entry) -> bool:
        return (_gap(m.date, e.date) <= ADJACENT_DAYS and len(m.terms.keys() & e.terms.keys()) >= MIN_SHARED
                and _cosine(m.terms, e.terms, idf) >= SIMILARITY)

    clusters: list[list[Entry]] = []
    for e in sorted(entries, key=lambda x: (x.date, x.origin)):
        home = next((c for c in reversed(clusters) if all(m.origin != e.origin for m in c)
                     and any(same(m, e) for m in c)), None)
        if home is None:
            clusters.append([e])
        else:
            home.append(e)
    merged = sorted((_merged(c) for c in clusters), key=lambda e: (e.date, e.headline), reverse=True)
    return [{"date": e.date, "headline": e.headline, "detail": e.detail, "where": e.where,
             "verification": e.verification, "sources": e.sources, "from": e.origin} for e in merged]
