"""
2. Ship-to-ship (STS) transfer candidates. Two vessels, at least one a tanker, both slow, within hundreds of metres of each other for a
sustained time, in open water (outside port areas and not among a waiting crowd). The encounter is tracked across passes in ``state``;
it becomes an event once it has lasted ``STS_MIN_S``, and closes when the pair has not been seen together for ``STS_LOST_S``.
A candidate is not a finding: it is two ships alongside, which is also what a lay-up pair, a bunkering and a rescue look like.
"""

from __future__ import annotations

from typing import Any

from .. import flags
from ..contracts import BehaviourEvent, event_id, iso
from ..geomath import km_between
from .common import Context, Fresh, crowd, hours_text, sat, thin, where, who, label_of

KIND = "sts"
_B = 0.01                                       # bucket size in degrees (~1.1 km) for finding close pairs


def _is_tanker(t: int) -> bool:
    return 80 <= t <= 89


def _pairs(slow: list[Fresh]) -> list[tuple[Fresh, Fresh, float]]:
    buckets: dict[tuple[int, int], list[Fresh]] = {}
    for f in slow:
        buckets.setdefault((round(f.lat / _B), round(f.lon / _B)), []).append(f)
    out: list[tuple[Fresh, Fresh, float]] = []
    for (r, c), members in buckets.items():
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                for a in members:
                    for b in buckets.get((r + dr, c + dc), ()):
                        if a.mmsi < b.mmsi and (_is_tanker(a.ship_type) or _is_tanker(b.ship_type)):
                            d = km_between(a.lat, a.lon, b.lat, b.lon) * 1000
                            if d <= flags.STS_MAX_M:
                                out.append((a, b, d))
    return out


def _event(ctx: Context, st: dict[str, Any], closed_at: float | None) -> BehaviourEvent:
    pa, pb = ctx.book.get(st["a"]), ctx.book.get(st["b"])
    pts = st["pts"]
    dist = sorted(p[3] for p in pts)
    med = dist[len(dist) // 2]
    dur = st["last"] - st["first"]
    mlat, mlon = pts[-1][1], pts[-1][2]
    area, countries = where(mlat, mlon)
    both_tankers = bool(pa and pb and _is_tanker(pa.ship_type) and _is_tanker(pb.ship_type))
    conf = 0.15 + 0.45 * sat(dur / flags.STS_FULL_S) + 0.25 * sat(1 - med / flags.STS_MAX_M) + 0.15 * both_tankers
    if dur > flags.STS_LAYUP_H * 3600:
        conf *= 0.5
    na, nb = (label_of(pa) if pa else f"MMSI {st['a']}"), (label_of(pb) if pb else f"MMSI {st['b']}")
    here = f" in {area}" if area else " in open water"
    fa, fb = (who(pa) if pa else {}), (who(pb) if pb else {})
    ev = BehaviourEvent(
        id=event_id(KIND, st["a"], st["b"], int(st["first"])), kind=KIND, mmsi=st["a"], mmsi2=st["b"],
        name=fa.get("name", ""), name2=fb.get("name", ""), imo=fa.get("imo", ""), flag=fa.get("flag", ""), flag2=fb.get("flag", ""),
        ship_class=fa.get("ship_class", ""), started_at=iso(st["first"]), last_seen=iso(st["last"]),
        ended_at=iso(closed_at) if closed_at is not None else None, state="ended" if closed_at is not None else "ongoing",
        lat=mlat, lon=mlon, area=area, countries=countries, confidence=round(min(1.0, conf), 3),
        rationale=(f"Within a median {med:.0f} m of each other at under {flags.STS_MAX_KN} kn for {hours_text(dur)}"
                   f"{' (both tankers)' if both_tankers else ''}, outside port areas ({flags.PORT_KM:.0f} km of ports, {flags.COAST_KM:.0f} km of land) "
                   f"and not among a crowd of {flags.CROWD_N}+ waiting ships"),
        summary=f"{na} and {nb} lay alongside{here} for {hours_text(dur)} at near-zero speed: a possible ship-to-ship transfer",
        detail={"median_m": round(med), "duration_h": round(dur / 3600, 1), "samples": len(pts), "mmsi_pair": [st["a"], st["b"]]},
        evidence=thin([[p[0], p[1], p[2], p[4], f"{p[3]:.0f} m apart"] for p in pts]))
    return ev


def detect(ctx: Context, state: dict[str, Any]) -> list[BehaviourEvent]:
    enc: dict[str, dict[str, Any]] = state.setdefault("enc", {})
    slow = [f for f in ctx.fresh if 0 <= f.sog <= flags.STS_MAX_KN and f.seen >= ctx.now - flags.FRESH_S
            and f.ship_type in flags.STS_PARTNER_TYPES]
    wide = [f for f in ctx.fresh if 0 <= f.sog <= flags.STS_MAX_KN and f.seen >= ctx.now - flags.FRESH_S]     # the crowd counts every slow ship
    touched: set[str] = set()
    for a, b, d in _pairs(slow):
        mlat, mlon = (a.lat + b.lat) / 2, (a.lon + b.lon) / 2
        if ctx.excl.in_port_area(mlat, mlon):
            ctx.screened("sts:port_area")
            continue
        if crowd(wide, mlat, mlon, {a.mmsi, b.mmsi}) >= flags.CROWD_N:
            ctx.screened("sts:anchorage_crowd")
            continue
        key = f"{a.mmsi}-{b.mmsi}"
        st = enc.setdefault(key, {"a": a.mmsi, "b": b.mmsi, "first": ctx.now, "last": ctx.now, "pts": []})
        st["last"] = ctx.now
        st["pts"].append([int(ctx.now), round(mlat, 4), round(mlon, 4), round(d), round(max(a.sog, b.sog), 1)])
        del st["pts"][:-96]
        touched.add(key)
    out: list[BehaviourEvent] = []
    for key in list(enc):
        st = enc[key]
        lost = key not in touched and ctx.now - st["last"] > flags.STS_LOST_S
        if st["last"] - st["first"] >= flags.STS_MIN_S:
            out.append(_event(ctx, st, st["last"] if lost else None))
        if lost:
            del enc[key]
    return out
