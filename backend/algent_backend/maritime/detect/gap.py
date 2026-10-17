"""
1. AIS gap ("went dark"). A vessel underway when last heard, then silent for ``GAP_MIN_S``, in water that stayed HEARD: other vessels
kept being heard in the 3 x 3 degree block around it at a comparable rate, and the block is being heard now. A vessel that left receiver
coverage, a place that went quiet as a whole, a ship that arrived in port and a stream outage are all screened out (coverage honesty:
silence only means something where listening continued). When the vessel is heard again the event closes with how far it reappeared.
"""

from __future__ import annotations

from .. import flags
from ..contracts import BehaviourEvent, event_id, iso
from ..geomath import block, km_between
from ..profile import MOVING_KN, Profile
from .common import Context, closed, hours_text, label_of, profile_points, sat, where, who

KIND = "ais_gap"


def _activity(ctx: Context, p: Profile, cells: list[int]) -> tuple[float, float]:
    """(underway samples per hour from OTHER vessels before the silence, and during it) in the block."""
    last_h, now_h = int(p.last // 3600), int(ctx.now // 3600)
    before = ctx.book.hourly_activity(cells, last_h - flags.GAP_BASE_H, last_h)
    own = sum(1 for ts, _la, _lo, sog in p.points() if sog >= MOVING_KN and last_h - flags.GAP_BASE_H <= ts // 3600 <= last_h)
    before = max(0.0, before - own / (flags.GAP_BASE_H + 1))
    return before, ctx.book.hourly_activity(cells, last_h + 1, now_h)


def _confidence(p: Profile, silence: float, before: float, during: float) -> float:
    tanker = 1.0 if 80 <= p.ship_type <= 89 else 0.0
    return round(0.15 + 0.45 * sat(silence / flags.GAP_FULL_S) + 0.25 * sat(during / max(before, 1e-9)) + 0.15 * tanker, 3)


def _open(ctx: Context, p: Profile) -> BehaviourEvent | None:
    silence = ctx.now - p.last
    if silence < flags.GAP_MIN_S or p.sog < flags.GAP_LAST_MIN_KN:
        return None
    if p.last <= ctx.blind_until:
        ctx.screened("gap:stream_was_down")
        return None
    if ctx.excl.in_port_area(p.lat, p.lon):
        ctx.screened("gap:port_area")
        return None
    cells = block(p.lat, p.lon, flags.GAP_NEIGHBOUR_DEG)
    before, during = _activity(ctx, p, cells)
    if before < flags.GAP_MIN_BEFORE:
        ctx.screened("gap:thin_water")
        return None
    if during < flags.GAP_ALIVE_SHARE * before or not any(ctx.heard.get(c, 0.0) >= ctx.now - flags.GAP_NOW_HEARD_S for c in cells):
        ctx.screened("gap:receiver_gap")
        return None
    area, countries = where(p.lat, p.lon)
    here = f" in {area}" if area else ""
    ev = BehaviourEvent(
        id=event_id(KIND, p.mmsi, int(p.last)), kind=KIND, mmsi=p.mmsi, **who(p), started_at=iso(p.last), last_seen=iso(p.last),
        lat=round(p.lat, 4), lon=round(p.lon, 4), area=area, countries=countries,
        confidence=_confidence(p, silence, before, during),
        rationale=(f"Silent {hours_text(silence)} after a report at {p.sog:.1f} kn, in water where {before:.1f} underway vessels an hour were heard "
                   f"before and {during:.1f} an hour during the silence (receivers were alive), more than {hours_text(flags.GAP_MIN_S)} of silence"),
        summary=f"{label_of(p)} stopped transmitting{here} and has not been heard for {hours_text(silence)}, while other ships nearby kept being heard",
        detail={"last_ts": int(p.last), "last_sog": round(p.sog, 1), "before_per_h": round(before, 2), "during_per_h": round(during, 2),
                "cells": len(cells), "silence_h": round(silence / 3600, 1)},
        evidence=profile_points(p, limit=6) + [[int(p.last), round(p.lat, 4), round(p.lon, 4), round(p.sog, 1), "last heard"]])
    return ev


def _reappeared(p: Profile, ev: BehaviourEvent) -> BehaviourEvent:
    km = km_between(float(ev.lat or 0), float(ev.lon or 0), p.lat, p.lon)
    dark = p.last - float(ev.detail["last_ts"])
    moved = km >= flags.GAP_MOVED_KM
    word = f"reappeared {km:.0f} km away" if moved else f"reappeared {km:.0f} km from where it went quiet"
    detail = {**ev.detail, "reappeared": {"ts": int(p.last), "lat": round(p.lat, 4), "lon": round(p.lon, 4), "km": round(km, 1), "moved_while_dark": moved},
              "dark_h": round(dark / 3600, 1)}
    out = closed(ev, p.last).model_copy(update={
        "detail": detail, "last_seen": iso(p.last), "confidence": round(min(1.0, ev.confidence + (0.1 if moved else 0.0)), 3),
        "summary": f"{ev.name or 'MMSI ' + str(ev.mmsi)} was silent {hours_text(dark)} and {word}",
        "evidence": [*ev.evidence, [int(p.last), round(p.lat, 4), round(p.lon, 4), round(p.sog, 1), "heard again"]]})
    return out


def detect(ctx: Context, current: dict[str, BehaviourEvent]) -> list[BehaviourEvent]:
    out: list[BehaviourEvent] = []
    live = {e.mmsi: e for e in current.values() if e.kind == KIND and e.ended_at is None}
    for p in ctx.book.profiles.values():
        if p.last <= 0:
            continue
        ev = live.get(p.mmsi)
        if ev is not None:
            if p.last > float(ev.detail["last_ts"]):
                out.append(_reappeared(p, ev))
            elif ctx.now - p.last > flags.GAP_UNRESOLVED_S:
                out.append(closed(ev, ctx.now, "unresolved").model_copy(update={"summary": ev.summary + "; never heard again within the window"}))
            continue
        opened = _open(ctx, p)
        if opened is not None:
            out.append(opened)
    for mmsi, ev in live.items():                       # a profile that expired entirely while its gap was open
        if mmsi not in ctx.book.profiles:
            out.append(closed(ev, ctx.now, "unresolved"))
    return out
