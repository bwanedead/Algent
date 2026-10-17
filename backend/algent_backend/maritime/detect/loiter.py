"""
5. Loitering near sensitive infrastructure. A vessel slow for ``LOITER_MIN_S`` inside a sensitive zone (a chokepoint box or an undersea
cable / pipeline corridor proxy, ``sites.ZONES``), in open water and not among a crowd of other slow ships (that is an anchorage, the
zone's ordinary waiting). Fishing, towing, dredging, diving and special craft are not reported: they work slowly on station for ordinary
reasons. The dwell is tracked across passes in ``state``.
"""

from __future__ import annotations

from typing import Any

from .. import flags
from ..contracts import BehaviourEvent, event_id, iso
from ..sites import Zone, ZONES, zone_at
from .common import Context, crowd, hours_text, label_of, sat, thin, who

KIND = "loiter"


def _event(ctx: Context, st: dict[str, Any], zone: Zone, lost: bool) -> BehaviourEvent:
    p = ctx.book.get(st["mmsi"])
    dur = st["last"] - st["first"]
    pts = st["pts"]
    name = label_of(p) if p else f"MMSI {st['mmsi']}"
    tanker = bool(p and 80 <= p.ship_type <= 89)
    conf = 0.2 + 0.5 * sat(dur / flags.LOITER_FULL_S) + 0.1 * tanker + 0.1 * (zone.kind == "chokepoint")
    return BehaviourEvent(
        id=event_id(KIND, st["mmsi"], zone.slug, int(st["first"])), kind=KIND, mmsi=st["mmsi"], **(who(p) if p else {}), started_at=iso(st["first"]),
        last_seen=iso(st["last"]), ended_at=iso(st["last"]) if lost else None, state="ended" if lost else "ongoing", lat=pts[-1][1], lon=pts[-1][2],
        area=zone.label, countries=list(zone.countries), confidence=round(min(1.0, conf), 3),
        rationale=(f"Under {flags.LOITER_MAX_KN:g} kn for {hours_text(dur)} inside {zone.label}, outside port areas and not among {flags.CROWD_N}+ other "
                   f"slow ships; this is longer than the {hours_text(flags.LOITER_MIN_S)} that separates waiting from loitering"),
        summary=f"{name} loitered {hours_text(dur)} in {zone.label}",
        detail={"zone": zone.slug, "zone_kind": zone.kind, "duration_h": round(dur / 3600, 1), "samples": len(pts),
                "proxy": zone.kind == "cable"},
        evidence=thin([[p_[0], p_[1], p_[2], p_[3], zone.label] for p_ in pts]))


def detect(ctx: Context, state: dict[str, Any]) -> list[BehaviourEvent]:
    dwell: dict[str, dict[str, Any]] = state.setdefault("dwell", {})
    slow = [f for f in ctx.fresh if 0 <= f.sog <= flags.LOITER_MAX_KN and f.seen >= ctx.now - flags.FRESH_S]
    touched: set[str] = set()
    for f in slow:
        zone = zone_at(f.lat, f.lon)
        if zone is None:
            continue
        if f.ship_type in flags.LOITER_EXCLUDED_TYPES:
            ctx.screened("loiter:working_craft")
            continue
        if ctx.excl.in_port_area(f.lat, f.lon):
            ctx.screened("loiter:port_area")
            continue
        if crowd(slow, f.lat, f.lon, {f.mmsi}) >= flags.CROWD_N:
            ctx.screened("loiter:anchorage_crowd")
            continue
        key = f"{f.mmsi}:{zone.slug}"
        st = dwell.setdefault(key, {"mmsi": f.mmsi, "zone": zone.slug, "first": ctx.now, "last": ctx.now, "pts": []})
        st["last"] = ctx.now
        st["pts"].append([int(ctx.now), round(f.lat, 4), round(f.lon, 4), round(f.sog, 1)])
        del st["pts"][:-96]
        touched.add(key)
    by_slug = {z.slug: z for z in ZONES}
    out: list[BehaviourEvent] = []
    for key in list(dwell):
        st = dwell[key]
        lost = key not in touched and ctx.now - st["last"] > flags.LOITER_LOST_S
        if st["last"] - st["first"] >= flags.LOITER_MIN_S and st["zone"] in by_slug:
            out.append(_event(ctx, st, by_slug[st["zone"]], lost))
        if lost:
            del dwell[key]
    return out
