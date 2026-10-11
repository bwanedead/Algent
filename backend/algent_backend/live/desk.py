"""
Live events as desk input — the ``LIVE EVENTS`` block a section writer sees, and the theater <-> event match.

Sensing decides which countries a theater is about (``sensing.corroborated``); this module only knows the current live
events and renders the ones touching those countries, each with its public source URL so a daily can cite
"IODA shows a nationwide outage in X since 14:00 UTC". Reads the local store only; never the network.
"""

from __future__ import annotations

from collections.abc import Callable

from . import store
from .contracts import LiveEvent

MAX_LINES = 8          # reader budget: every line is prompt the writer must read
_RANK = {"major": 0, "notable": 1, "info": 2}


def current() -> list[LiveEvent]:
    """Events still going (no end) across every feed; ended outages stay out of the writers' evidence."""
    return [e for e in store.read_events() if e.end is None]


def country_names() -> set[str]:
    return {c for e in current() for c in e.countries}


def line(e: LiveEvent) -> str:
    since = f" since {e.start[:16].replace('T', ' ')} UTC" if e.start else ""
    return f"- [{e.feed}] {e.title}{since}. {e.detail} source: {e.source} {e.source_url}"


def block(countries: set[str]) -> tuple[str, set[str], int]:
    """(text, source urls, n lines) for the live events touching ``countries`` ('' when none)."""
    hit = sorted((e for e in current() if set(e.countries) & countries), key=lambda e: (_RANK[e.severity], e.id))[:MAX_LINES]
    if not hit:
        return "", set(), 0
    head = ("LIVE EVENTS — machine-detected right now from public live feeds (no model); they say something is happening, "
            "not why:")
    return "\n".join([head, *map(line, hit)]), {e.source_url for e in hit if e.source_url}, len(hit)


def for_theater(corroborate: Callable[[Callable[[str], set[str]]], set[str]], find_in: Callable[[str, set[str]], set[str]]
                ) -> tuple[str, set[str], int]:
    """Glue for sensing: ``find_in(text, names)`` -> names present; ``corroborate(find)`` -> those the theater stands behind."""
    names = country_names()
    if not names:
        return "", set(), 0
    return block(corroborate(lambda text: find_in(text, names)))
