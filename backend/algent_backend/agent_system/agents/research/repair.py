"""
Corpus repair — put back the complete profile a failed attempt once replaced.

Before the store refused to let an incomplete result replace a complete profile, a run cut short could
save an empty profile as the CURRENT version over the day's finished research. The finished research
is still in ``_history``; this finds every such profile and restores the newest complete version.
Read-only until ``apply`` is called; the restoration itself is the store's (logged, history kept).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .store import JsonProfileStore, profile_shape


@dataclass(frozen=True)
class Repair:
    profile_id: str
    version: Path             # the history version that would be (or was) restored
    current: dict             # shape of what is current now
    restored: dict            # shape of what it becomes


def plan(store: JsonProfileStore) -> list[Repair]:
    """Every id whose current version is not complete while a complete same-id version sits in history."""
    repairs = []
    for current in store.iter_profiles():
        if current.is_complete:
            continue
        best = store.newest_complete(current.id)
        if best is not None:
            repairs.append(Repair(current.id, best[0], profile_shape(current), profile_shape(best[1])))
    return repairs


def apply(store: JsonProfileStore, repairs: list[Repair]) -> None:
    for r in repairs:
        store.restore(r.profile_id, r.version, replaced=store.get(r.profile_id))
