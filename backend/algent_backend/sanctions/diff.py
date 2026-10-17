"""
Snapshot diff — the only place a change in a list becomes an event.

Pure: two snapshots in, events out. The rules (docs/architecture/sanctions-calendar.md):
* no previous snapshot -> a baseline: only entries the list itself dates inside ``BASELINE_RECENT_DAYS`` become events;
* a ref that appeared -> ``designated``, a ref that vanished -> ``delisted``;
* a snapshot that shrank below ``MIN_KEEP_FRACTION`` of the previous one is refused (truncated download / format change).
"""

from __future__ import annotations

from datetime import date, timedelta

from . import flags
from .contracts import SOURCES, Entry, SanctionsEvent, event_id


def _event(source: str, action: str, e: Entry, day: date, when: str, *, baseline: bool = False) -> SanctionsEvent:
    return SanctionsEvent(id=event_id(source, action, e.ref, when), source=source, action=action, date=when,          # type: ignore[arg-type]
                          observed_on=day.isoformat(), ref=e.ref, name=e.name, type=e.type, programmes=e.programmes,
                          countries=e.countries, imo=e.imo, flag=e.flag, owner=e.owner,
                          source_url=e.url or SOURCES[source]["page"], baseline=baseline)


def _recent(stated: str, day: date, days: int) -> bool:
    try:
        return day - timedelta(days=days) <= date.fromisoformat(stated) <= day
    except ValueError:
        return False


def diff(source: str, old: dict[str, Entry] | None, new: dict[str, Entry], day: date) -> list[SanctionsEvent]:
    if old is None:
        return [_event(source, "designated", e, day, e.designated_on, baseline=True)
                for e in new.values() if _recent(e.designated_on, day, flags.BASELINE_RECENT_DAYS)]
    if old and len(new) < flags.MIN_KEEP_FRACTION * len(old):
        raise ValueError(f"{source}: snapshot shrank from {len(old)} to {len(new)} entries; refusing it")
    out = []
    for ref in sorted(new.keys() - old.keys()):
        e = new[ref]
        out.append(_event(source, "designated", e, day, e.designated_on if _recent(e.designated_on, day, flags.LIST_DATE_MAX_AGE_DAYS) else day.isoformat()))
    for ref in sorted(old.keys() - new.keys()):
        out.append(_event(source, "delisted", old[ref], day, day.isoformat()))
    return out
