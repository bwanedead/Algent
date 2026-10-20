"""
Conflict log as desk input — the ``OHMEGA CONFLICT LOG`` block a section writer sees.

Same stance as ``maritime/desk.py``: sensing decides which countries a theater stands behind; this module only knows the store. It tallies what the
sources reported in the last days for those countries and lists the strongest events (curated and fatal first, then the most-reported). The counts
are Ohmega's own tally of what sources reported, a minimum, and machine-coded GDELT rows are marked as such. Reads the local store only.
"""

from __future__ import annotations

from collections import Counter
from datetime import date

from . import flags, store
from .contracts import TYPE_LABEL, ConflictEvent

PAGE_URL = "https://www.ohmega.monster/intel/attacks"


def _head(since: str) -> str:
    return ("OHMEGA CONFLICT LOG - Ohmega's own tally of attacks, clashes and mass-violence events that sources reported "
            f"(collected since {since or 'recently'}); cite it as \"Ohmega analysis of reported events\". It is a MINIMUM: coverage is partial, "
            "some events are never reported, and rows marked machine-coded (GDELT) are software readings of news text that can duplicate, "
            "misplace or misread an event and never carry casualty figures. Curated rows (ACLED, UCDP) are checked by researchers. "
            "A count is not a death toll:")


def _rank(e: ConflictEvent) -> tuple:
    return (e.coding == "curated", e.fatalities or 0, e.articles)


def _line(e: ConflictEvent) -> str:
    fat = f", {e.fatalities} killed per {e.source}" if e.fatalities else ""
    tag = "machine-coded" if e.coding == "machine" else e.source
    who = " vs ".join(x for x in (e.actor1, e.actor2) if x)
    return f"- {e.date} {TYPE_LABEL[e.type].lower()}, {e.place or e.country}{f' ({who})' if who else ''}{fat} [{tag}, {e.articles} report(s)]"


def block(countries: set[str], today: date | None = None, *, limit: int | None = None) -> tuple[str, set[str], int]:
    """(text, source urls, n lines) for events in ``countries`` (ISO2) over the last DESK_DAYS ('' when none)."""
    evs = [e for e in store.events(flags.DESK_DAYS, today) if e.country in countries and e.type != "report"]
    return _render(evs, limit or flags.DESK_LINES)


def block_all(today: date | None = None) -> tuple[str, set[str], int]:
    """The strongest events anywhere (the world sweep's material)."""
    return _render([e for e in store.events(flags.DESK_DAYS, today) if e.type != "report"], flags.SWEEP_LINES)


def _render(evs: list[ConflictEvent], limit: int) -> tuple[str, set[str], int]:
    if not evs:
        return "", set(), 0
    tally = Counter((e.country or "??", e.type) for e in evs)
    by_country = {c: ", ".join(f"{n} {TYPE_LABEL[t].lower()}" for (cc, t), n in tally.most_common() if cc == c) for c in {c for c, _ in tally}}
    top = sorted(evs, key=_rank, reverse=True)[:limit]
    lines = [f"- {c}: {txt} (last {flags.DESK_DAYS} days)" for c, txt in sorted(by_country.items(), key=lambda kv: -sum(v for (c, _), v in tally.items() if c == kv[0]))[:6]]
    urls = {PAGE_URL} | {u for e in top if e.coding == "curated" for u in e.urls}
    return "\n".join([_head(store.collecting_since()), *lines, *map(_line, top)]), urls, len(top)
