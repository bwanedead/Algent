"""
GNSS interference as desk input — the ``OHMEGA GNSS INTERFERENCE`` block a section writer sees.

Same stance as ``maritime/desk.py``: sensing decides which countries a theater stands behind; this module only knows the store. It lists the latest day's
zones over those countries (or, for the world sweep, the strongest anywhere), our own estimates first, noting where GPSJam agrees. Our own derivation, so cited as
"Ohmega analysis". A zone says aircraft there reported poor navigation accuracy; it does not say who is jamming. Reads the local store only.
"""

from __future__ import annotations

from datetime import date

from . import flags, store
from .contracts import Zone

PAGE_URL = "https://www.ohmega.monster/intel/gnss"


def _head(since: str) -> str:
    return ("OHMEGA GNSS INTERFERENCE - computed by Ohmega (no model) from the navigation accuracy aircraft broadcast (ADS-B), "
            f"collected since {since or 'recently'}; cite it as \"Ohmega analysis\". Each line is a one-degree cell where an unusual share of aircraft "
            "reported poor position accuracy: that is a sign of GPS jamming or spoofing, not proof of who is doing it. It is a MINIMUM: only aircraft that "
            "broadcast ADS-B and are heard by volunteer receivers are seen, and only where Ohmega samples. 'new' and 'intensifying' compare a cell with its own history:")


def _line(z: Zone) -> str:
    tail = " (GPSJam shows it too)" if z.cross_check == "agrees" else " (not seen in GPSJam's file)" if z.cross_check == "not_in_gpsjam" else ""
    flag = f", {z.flag}" if z.flag else ""
    return (f"- {z.date}: {z.severity} interference around {z.lat:.1f}, {z.lon:.1f}{f' ({z.country})' if z.country else ' (sea or border area)'}: "
            f"{z.degraded_share:.0%} of {z.aircraft} aircraft observations degraded{flag}{tail}")


def latest(today: date | None = None) -> list[Zone]:
    days = [d for d in store.zone_days() if d <= (today or date.today()).isoformat()]
    if not days:
        return []
    return [Zone.model_validate(z) for z in store.load_zones(days[-1]).get("zones", [])]


def _render(zs: list[Zone], limit: int) -> tuple[str, set[str], int]:
    if not zs:
        return "", set(), 0
    top = sorted(zs, key=lambda z: (z.flag == "", -z.degraded_share))[:limit]
    return "\n".join([_head(store.since().get("ohmega_adsb", "")), *map(_line, top)]), {PAGE_URL}, len(top)


def block(countries: set[str], today: date | None = None) -> tuple[str, set[str], int]:
    return _render([z for z in latest(today) if z.country in countries], flags.DESK_LINES)


def block_all(today: date | None = None) -> tuple[str, set[str], int]:
    return _render(latest(today), flags.DESK_LINES)
