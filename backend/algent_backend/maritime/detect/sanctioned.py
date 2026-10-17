"""
4. Sanctioned vessel seen. A vessel on our board that matches a sanctions designation (the current vessel entries of the OFAC, UK and
EU snapshots): by IMO number (high confidence) or by exact name PLUS flag state (medium: names recur and flags change). A name alone is
never reported. A former name the vessel broadcast earlier counts as its name. One event per vessel, listing and UTC day.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from algent_backend.live.classify import flag_of
from algent_backend.sanctions import store as sstore
from algent_backend.sanctions.contracts import SOURCES, Entry
from algent_backend.sanctions.vessels import asset_key

from .. import flags
from ..contracts import BehaviourEvent, event_id, iso
from ..profile import Profile, fold_name
from .common import Context, label_of, profile_points, where, who

KIND = "sanctioned"
_REFRESH_S = 3600


@dataclass
class SanctionIndex:
    by_imo: dict[str, list[tuple[str, Entry]]] = field(default_factory=dict)
    by_name: dict[tuple[str, str], list[tuple[str, Entry]]] = field(default_factory=dict)
    built: float = 0.0

    @classmethod
    def build(cls, snapshots: dict[str, dict[str, Entry]], now: float | None = None) -> "SanctionIndex":
        idx = cls(built=now if now is not None else time.time())
        for src, entries in snapshots.items():
            for e in entries.values():
                if e.type != "vessel":
                    continue
                if e.imo:
                    idx.by_imo.setdefault(e.imo, []).append((src, e))
                name = fold_name(e.name)
                if e.flag and len(name) >= flags.SANCTION_NAME_MIN_CHARS:
                    idx.by_name.setdefault((name, e.flag), []).append((src, e))
        return idx

    @classmethod
    def from_store(cls, now: float | None = None) -> "SanctionIndex":
        snaps = {s: (sstore.load_snapshot(s) or {}) for s in flags.SANCTION_SOURCES}
        return cls.build(snaps, now)

    def __len__(self) -> int:
        return len(self.by_imo) + len(self.by_name)


def refreshed(idx: SanctionIndex | None, now: float) -> SanctionIndex | None:
    """The index, rebuilt from the sanctions snapshots at most hourly (they change a few times a week). Never raises."""
    if idx is not None and now - idx.built < _REFRESH_S:
        return idx
    try:
        return SanctionIndex.from_store(now)
    except Exception:  # noqa: BLE001
        return idx


def _matches(idx: SanctionIndex, p: Profile) -> list[tuple[str, str, Entry, str]]:
    """(basis, source, entry, matched name) for the profile, strongest basis first."""
    found: list[tuple[str, str, Entry, str]] = []
    if p.imo:
        found += [("imo", s, e, e.name) for s, e in idx.by_imo.get(p.imo, [])]
    if found:
        return found
    flag = flag_of(p.mmsi)
    names = [p.name, *(c[2] for c in p.changes if c[1] == "name")]
    for n in dict.fromkeys(fold_name(x) for x in names if x):
        found += [("name_flag", s, e, n) for s, e in idx.by_name.get((n, flag), [])] if flag else []
    return found


def detect(ctx: Context, current: dict[str, BehaviourEvent]) -> list[BehaviourEvent]:
    idx = ctx.sanctions
    if not idx:
        return []
    out: list[BehaviourEvent] = []
    for p in ctx.book.profiles.values():
        if p.last <= 0:
            continue
        for basis, src, e, matched in _matches(idx, p):
            day = int(p.last // 86400)
            eid = event_id(KIND, p.mmsi, src, e.ref, day)
            old = current.get(eid)
            area, countries = where(p.lat, p.lon)
            listed = SOURCES[src]["label"]
            seen_now = ctx.now - p.last <= 2 * flags.DETECT_SECONDS + 900
            out.append(BehaviourEvent(
                id=eid, kind=KIND, mmsi=p.mmsi, **{**who(p), "imo": p.imo or e.imo}, started_at=old.started_at if old else iso(p.last),
                last_seen=iso(p.last), ended_at=None if seen_now else iso(p.last), state="ongoing" if seen_now else "ended",
                lat=round(p.lat, 4), lon=round(p.lon, 4), area=area, countries=countries,
                confidence=flags.SANCTION_CONF[basis],
                rationale=(f"Broadcast IMO {p.imo} is the IMO of a vessel designated by {listed}" if basis == "imo" else
                           f"Broadcast name '{matched}' and the {flag_of(p.mmsi)} flag state match a vessel designated by {listed}; no IMO number to confirm"),
                summary=f"{label_of(p)} ({listed} designated vessel{', ' + ', '.join(e.programmes[:2]) if e.programmes else ''}) was seen"
                        f"{' in ' + area if area else ''}",
                detail={"basis": basis, "source": src, "list": listed, "ref": e.ref, "listed_name": e.name, "listed_flag": e.flag, "owner": e.owner,
                        "programmes": e.programmes, "designated_on": e.designated_on, "url": e.url or SOURCES[src]["page"],
                        "asset_id": asset_key(e.imo, e.name, e.flag)},
                evidence=profile_points(p, limit=12)))
    return out
