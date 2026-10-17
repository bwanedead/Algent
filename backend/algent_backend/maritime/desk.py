"""
Maritime behaviour as desk input — the ``OHMEGA MARITIME`` block a section writer sees, and the sweep's version.

Same stance as ``live/memory/desk.py``: sensing decides which countries a theater stands behind (``sensing.corroborated``); this module only
knows the current events and renders the ones whose AREA (a chokepoint, region or cable zone) touches those countries. They are Ohmega's
own derivation (provenance ``ohmega_derived``): a daily may cite them as "Ohmega analysis of AIS", never as something a source reported.
Reads the local store only; never the network.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from algent_backend.live.memory.areas import AREAS

from . import flags, store
from .contracts import LABEL, BehaviourEvent
from .sites import ZONES

PAGE_URL = "https://www.ohmega.monster/intel/maritime"
_HEAD = ("OHMEGA MARITIME - computed by Ohmega (no model) from the ship positions it hears (AIS); cite it as \"Ohmega analysis\". Each line is a "
         "pattern seen, not a finding of intent: a silence, an encounter, a rename or a long dwell all have innocent explanations. Gaps are only "
         "reported where other ships kept being heard (a ship that left receiver coverage is not going dark), ports and anchorage crowds are "
         "screened out, a match to a sanctions list rests on the IMO number or on name plus flag state as the line says, and a zone marked "
         "proxy is an approximate corridor:")


def _recent(e: BehaviourEvent, now: datetime) -> bool:
    """Still going, or last seen within the days a daily may still cite."""
    return e.ended_at is None or (e.last_seen or e.ended_at) >= (now - timedelta(days=flags.DESK_RECENT_DAYS)).isoformat(timespec="seconds")


def _line(e: BehaviourEvent) -> str:
    state = "ongoing" if e.ended_at is None else f"ended {e.ended_at[:16].replace('T', ' ')} UTC"
    return (f"- {LABEL[e.kind]}: {e.summary} (since {e.started_at[:16].replace('T', ' ')} UTC, {state}; confidence {e.confidence:.0%}). "
            f"Why flagged: {e.rationale}")


def _block(hit: list[BehaviourEvent], limit: int) -> tuple[str, set[str], int]:
    hit = sorted(hit, key=lambda e: (-e.confidence, e.started_at))[:limit]
    return ("\n".join([_HEAD, *map(_line, hit)]), {PAGE_URL}, len(hit)) if hit else ("", set(), 0)


def _current(now: datetime | None) -> list[BehaviourEvent]:
    now = now or datetime.now(timezone.utc)
    return [e for e in store.read_current().values() if _recent(e, now)]


def touching(countries: set[str], now: datetime | None = None) -> list[BehaviourEvent]:
    return [e for e in _current(now) if set(e.countries) & countries]


def block(countries: set[str], now: datetime | None = None) -> tuple[str, set[str], int]:
    """(text, source urls, n lines) for the events in areas touching ``countries`` ('' when none)."""
    return _block(touching(countries, now), flags.DESK_LINES)


def block_all(now: datetime | None = None) -> tuple[str, set[str], int]:
    """The strongest events anywhere, in or out of a named area (the world sweep's material)."""
    return _block(_current(now), flags.SWEEP_LINES)


def country_names() -> set[str]:
    return {c for z in ZONES for c in z.countries} | {c for a in AREAS if a.kind != "fire" for c in a.countries}


def for_theater(corroborate: Callable[[Callable[[str], set[str]]], set[str]], find_in: Callable[[str, set[str]], set[str]]
                ) -> tuple[str, set[str], int]:
    """Glue for sensing: (text, urls, n lines) for the countries the theater stands behind that we watch."""
    names = country_names() | {c for e in store.read_current().values() for c in e.countries}
    stood = corroborate(lambda text: find_in(text, names))
    return block(stood)
