"""
3. Identity changes. Read from the profile book's recorded changes and from the IMO index: a rename, a name that goes A -> B -> A
(two transmitters on one identity), an IMO number that changed on one MMSI, an IMO with an invalid check digit, and one IMO number
heard under MMSIs of different flag states (flag hopping). Each is evidence of a changed or contested identity, not proof of intent.
"""

from __future__ import annotations

from .. import flags
from ..contracts import BehaviourEvent, event_id, iso
from ..profile import Profile, imo_valid, same_name
from .common import Context, label_of, where, who
from algent_backend.live.classify import flag_of

KIND = "identity"
_WORD = {"rename": "was renamed", "alternating": "alternates between two names", "imo_change": "changed IMO number",
         "imo_invalid": "broadcasts an IMO number with an invalid check digit", "flag_hop": "appears under more than one flag state"}


def _ev(p: Profile, sub: str, ts: float, key: object, rationale: str, summary: str, detail: dict, evidence: list, extra: float = 0.0,
        mmsi2: int | None = None, flag2: str = "") -> BehaviourEvent:
    area, countries = where(p.lat, p.lon) if p.last else ("", [])
    tanker = 0.1 if 80 <= p.ship_type <= 89 else 0.0
    return BehaviourEvent(
        id=event_id(KIND, sub, p.mmsi, key), kind=KIND, mmsi=p.mmsi, mmsi2=mmsi2, **who(p), flag2=flag2, started_at=iso(ts), ended_at=iso(ts),
        last_seen=iso(p.last or ts), state="ended", lat=round(p.lat, 4) if p.last else None, lon=round(p.lon, 4) if p.last else None,
        area=area, countries=countries, confidence=round(min(1.0, flags.IDENTITY_BASE[sub] + tanker + extra), 3), rationale=rationale,
        summary=summary, detail={"change": sub, **detail}, evidence=evidence)


def _changes(p: Profile) -> list[BehaviourEvent]:
    out: list[BehaviourEvent] = []
    names = [c for c in p.changes if c[1] == "name"]
    seen = [names[0][2]] if names else []
    for i, (ts, _k, old, new) in enumerate(names):
        back = any(same_name(new, earlier) for earlier in seen)
        seen.append(new)
        sub = "alternating" if back else "rename"
        extra = min(0.2, 0.1 * i)
        out.append(_ev(p, sub, ts, ts, f"Broadcast name changed from '{old}' to '{new}' on one MMSI"
                       + (" and returned to a name used earlier (two sources sharing the identity)" if back else ""),
                       f"{old} {'now alternates with' if back else 'was renamed'} {new}", {"old": old, "new": new, "n_renames": i + 1},
                       [[int(ts), round(p.lat, 4), round(p.lon, 4), -1, f"{old} -> {new}"]], extra))
    for ts, _k, old, new in (c for c in p.changes if c[1] == "imo"):
        out.append(_ev(p, "imo_change", ts, ts, f"IMO number broadcast on this MMSI changed from {old} to {new}",
                       f"{label_of(p)} {_WORD['imo_change']} ({old} to {new})", {"old": old, "new": new},
                       [[int(ts), round(p.lat, 4), round(p.lon, 4), -1, f"IMO {old} -> {new}"]]))
    return out


def detect(ctx: Context, current: dict[str, BehaviourEvent]) -> list[BehaviourEvent]:
    out: list[BehaviourEvent] = []
    for p in ctx.book.profiles.values():
        out += _changes(p)
        if p.imo and not imo_valid(p.imo):
            ts = p.last or p.first
            out.append(_ev(p, "imo_invalid", p.first, p.imo, f"IMO {p.imo} fails the IMO check digit (a real number always passes)",
                           f"{label_of(p)} {_WORD['imo_invalid']} ({p.imo})", {"imo": p.imo},
                           [[int(ts), round(p.lat, 4), round(p.lon, 4), -1, f"IMO {p.imo}"]]))
    for imo, mmsis in ctx.book.by_imo.items():
        ps = [ctx.book.get(m) for m in mmsis]
        ps = sorted((p for p in ps if p is not None and p.last > 0), key=lambda p: -p.last)
        flags_ = {flag_of(p.mmsi) for p in ps} - {""}
        if len(ps) > 1 and len(flags_) > 1:
            a, b = ps[0], ps[1]
            out.append(_ev(a, "flag_hop", a.first, imo, f"IMO {imo} was heard under {len(ps)} MMSIs with flag states {', '.join(sorted(flags_))}",
                           f"IMO {imo} appears under {' and '.join(sorted(flags_))} flags ({label_of(a)}, {label_of(b)})",
                           {"imo": imo, "mmsis": [p.mmsi for p in ps], "flags": sorted(flags_)},
                           [[int(p.last), round(p.lat, 4), round(p.lon, 4), round(p.sog, 1), f"MMSI {p.mmsi} {flag_of(p.mmsi)}"] for p in ps][:12],
                           mmsi2=b.mmsi, flag2=flag_of(b.mmsi)))
    return out
