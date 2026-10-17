"""What every detector reads (the context of one pass) and the small helpers they share. Pure; no I/O."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from algent_backend.live.classify import VESSEL_CLASSES, flag_of, vessel_class
from algent_backend.live.memory.areas import areas_at

from .. import flags
from ..contracts import BehaviourEvent, Point, iso
from ..geomath import km_between
from ..profile import Profile, ProfileBook
from ..sites import Exclusion


@dataclass
class Fresh:
    """A vessel on the live board right now."""

    mmsi: int
    lat: float
    lon: float
    sog: float
    seen: float
    ship_type: int
    name: str


@dataclass
class Context:
    now: float
    book: ProfileBook
    heard: Mapping[int, float]                       # 1-degree cell -> when AIS was last heard there (the coverage grid)
    fresh: list[Fresh]
    excl: Exclusion
    blind_until: float = 0.0                         # the stream was down until here: silences that began before it say nothing
    sanctions: Any = None                            # sanctioned.SanctionIndex | None
    notes: dict[str, int] = field(default_factory=dict)   # what the pass screened out, by reason (for the account)

    def screened(self, reason: str) -> None:
        self.notes[reason] = self.notes.get(reason, 0) + 1


def klass_of(ship_type: int) -> str:
    return VESSEL_CLASSES[vessel_class(ship_type)]


def who(p: Profile) -> dict[str, str]:
    return {"name": p.name, "imo": p.imo, "flag": flag_of(p.mmsi), "ship_class": klass_of(p.ship_type)}


def where(lat: float, lon: float) -> tuple[str, list[str]]:
    """(the named area it lies in, the desk's country names for it)."""
    hit = areas_at(lat, lon)
    return (hit[0].label if hit else ""), sorted({c for a in hit for c in a.countries})


def sat(x: float) -> float:
    return max(0.0, min(1.0, x))


def thin(points: list[Point], n: int = flags.EVIDENCE_POINTS) -> list[Point]:
    """At most ``n`` points, evenly spread, first and last kept."""
    if len(points) <= n:
        return points
    step = (len(points) - 1) / (n - 1)
    return [points[round(i * step)] for i in range(n)]


def profile_points(p: Profile, since: float = 0.0, limit: int = 8) -> list[Point]:
    pts = [[ts, round(la, 4), round(lo, 4), sog, ""] for ts, la, lo, sog in p.points() if ts >= since]
    return pts[-limit:]


def crowd(slow: list[Fresh], lat: float, lon: float, skip: set[int]) -> int:
    """How many OTHER slow vessels lie within CROWD_KM: an anchorage or a waiting area, not a pair."""
    near = 0
    for f in slow:
        if f.mmsi not in skip and abs(f.lat - lat) <= flags.CROWD_KM / 100 and km_between(lat, lon, f.lat, f.lon) <= flags.CROWD_KM:
            near += 1
    return near


def hours_text(seconds: float) -> str:
    h = seconds / 3600
    return f"{h:.1f} h" if h < 48 else f"{h / 24:.1f} d"


def label_of(p: Profile) -> str:
    return p.name or f"MMSI {p.mmsi}"


def closed(e: BehaviourEvent, at: float, state: str = "ended") -> BehaviourEvent:
    return e.model_copy(update={"ended_at": iso(at), "state": state})
