"""
The /live summary — "What's happening now" headline items, per-layer freshness and the live chokepoint counts, as one small
document (``live/summary.json``). Pure computation over what the collectors already hold (events, daily series, the live
gate counts); no model, no network. Both the timer runner and the always-on stream service rebuild it from the local store.

An item is flagged only when it is unusual FOR ITS OWN RECENT HISTORY: a count is "surging" when it beats everything in the
recent window and sits outside Tukey's fence (above the upper quartile by 1.5 interquartile ranges); never against a fixed
number. Each item names the layer it belongs to and where to centre the map.
"""

from __future__ import annotations

import statistics
from datetime import datetime
from typing import Any, Iterable

from . import flags, store
from .contracts import LiveEvent, iso
from .regions import FIRE_BOXES, GATES, REGIONS

MIN_HISTORY = 5          # fewer completed days than this and "usual" would be a guess
WINDOW = 14              # days "usual" is judged over
PER_LAYER = 2            # items one layer may take of the strip
# stat_rows() layout: (series_id, period, value, partial, name, unit, kind, region, lat, lon, source_url)
_SID, _PERIOD, _VALUE, _PARTIAL = 0, 1, 2, 3


def outlier(history: list[float], value: float) -> str | None:
    """'high' when ``value`` beats every recent value and sits above Tukey's upper fence, 'low' for the mirror; None otherwise
    (and when there is too little history to judge)."""
    if len(history) < MIN_HISTORY:
        return None
    q1, _, q3 = statistics.quantiles(history, n=4, method="inclusive")
    iqr = q3 - q1
    if value > max(history) and value > q3 + 1.5 * iqr:
        return "high"
    if value < min(history) and value < q1 - 1.5 * iqr:
        return "low"
    return None


def _series(rows: Iterable[tuple], sid: str) -> tuple[list[float], float | None]:
    """(completed days oldest first, the running day's value or None)."""
    mine = sorted((r for r in rows if r[_SID] == sid), key=lambda r: r[_PERIOD])
    done = [float(r[_VALUE]) for r in mine if not r[_PARTIAL]]
    cur = next((float(r[_VALUE]) for r in reversed(mine) if r[_PARTIAL]), None)
    return done[-WINDOW - 1:], cur


def _hhmm(start: str) -> str:
    return f"{start[11:16]} UTC" if len(start) >= 16 else ""


def _item(layer: str, text: str, score: float, lat: float | None, lon: float | None, zoom: float, key: str) -> dict[str, Any]:
    return {"id": key, "layer": layer, "text": text, "score": round(score, 1), "lat": lat, "lon": lon, "zoom": zoom}


def compute(events: list[LiveEvent], rows: list[tuple], gates_now: dict[str, Any] | None, now: datetime) -> list[dict[str, Any]]:
    from algent_backend.instruments.live_series import ais_ids, fire_id, mil_ids

    items: list[dict[str, Any]] = []
    for e in events:
        if e.kind == "outage" and e.end is None:
            major = e.severity == "major"
            since = f" since {_hhmm(e.start)}" if e.start else ""
            name = e.countries[0] if e.countries else "a country"
            text = f"Internet down nationwide in {name}{since}" if major else f"Internet disrupted in {name}{since}"
            items.append(_item("outage", text, 100 if major else 45, e.lat, e.lon, 4, e.id))
        elif e.kind == "quake" and e.end is None:
            mag = float(e.data.get("magnitude") or 0)
            score = 30 + (mag - 4.5) * 20 + (15 if e.severity == "major" else 0)
            items.append(_item("quake", e.title + (f" at {_hhmm(e.start)}" if e.start else ""), score, e.lat, e.lon, 5.5, e.id))
        elif e.kind == "fire" and e.data.get("notable"):
            items.append(_item("fire", f"{e.title}: {float(e.data.get('frp_mw') or 0):.0f} MW", 55, e.lat, e.lon, 6, e.id))
    for b in FIRE_BOXES:
        done, cur = _series(rows, fire_id(b.slug))
        if cur is not None and outlier(done, cur) == "high":
            lat, lon = (b.box[0] + b.box[2]) / 2, (b.box[1] + b.box[3]) / 2
            items.append(_item("fire", f"Fires surging near {b.label}: {cur:.0f} heat readings in 24 h, usual about {statistics.median(done):.0f}",
                               70, lat, lon, 6, f"surge:{b.slug}"))
    for r in REGIONS:
        done, cur = _series(rows, mil_ids(r.slug)[0])
        if cur is not None and outlier(done, cur) == "high":
            lat, lon = (r.box[0] + r.box[2]) / 2, (r.box[1] + r.box[3]) / 2
            items.append(_item("aircraft", f"{cur:.0f} military aircraft over the {r.label} at once, above anything in the last two weeks",
                               50, lat, lon, 5, f"mil:{r.slug}"))
    live = (gates_now or {}).get("gates", {})
    for g in GATES:
        now_g = live.get(g.slug)
        done, _ = _series(rows, ais_ids(g.slug)[0])
        if not done:
            continue
        latest, before = done[-1], done[:-1]
        flag = outlier(before, latest)
        lat, lon = (g.a[0] + g.b[0]) / 2, (g.a[1] + g.b[1]) / 2
        usual = statistics.median(before) if len(before) >= MIN_HISTORY else None
        if flag and usual:
            pct = round(abs(latest - usual) / usual * 100)
            head = f"{g.label}: " + (f"{now_g['in_strait']} ships in the strait now, " if now_g else "") + \
                   f"transits {pct}% {'below' if flag == 'low' else 'above'} usual"
            items.append(_item("ships", head, 80, lat, lon, 7, f"gate:{g.slug}"))
        elif now_g and now_g["in_strait"]:
            items.append(_item("ships", f"{g.label}: {now_g['in_strait']} ships in the strait now ({now_g['moving']} moving)", 30, lat, lon, 7, f"gate:{g.slug}"))
    items.sort(key=lambda i: -i["score"])
    out: list[dict[str, Any]] = []
    taken: dict[str, int] = {}
    for it in items:
        if taken.get(it["layer"], 0) >= PER_LAYER:
            continue
        taken[it["layer"]] = taken.get(it["layer"], 0) + 1
        out.append(it)
        if len(out) >= flags.HEADLINES_MAX:
            break
    return out


_FEED_LAYER = {"ioda": "outage", "usgs": "quake", "firms": "fire", "adsb": "aircraft_regions"}


def freshness(status: dict[str, dict[str, Any]], extra: dict[str, str]) -> dict[str, str]:
    """layer -> ISO instant of the last good update. Layers fed by snapshots pass theirs in ``extra``."""
    out = {layer: status.get(feed, {}).get("last_ok", "") for feed, layer in _FEED_LAYER.items()}
    return {k: v for k, v in {**out, **extra}.items() if v}


def build(now: datetime, rows: list[tuple] | None = None, extra_fresh: dict[str, str] | None = None) -> dict[str, Any]:
    """The summary document from the local store (events, series rows, gate counts). ``rows`` defaults to the published stat rows."""
    from . import publish

    rows = publish.stat_rows(now.date()) if rows is None else rows
    gates_now = store.read_doc("gates_now") or {}
    fires = store.read_doc("fires_meta") or {}
    gates_meta = {g.slug: {"label": g.label, "lat": round((g.a[0] + g.b[0]) / 2, 3), "lon": round((g.a[1] + g.b[1]) / 2, 3), "box": list(g.box)} for g in GATES}
    gates = {}
    from algent_backend.instruments.live_series import ais_ids

    for slug, meta in gates_meta.items():
        _, today = _series(rows, ais_ids(slug)[0])
        _, today_t = _series(rows, ais_ids(slug)[1])
        gates[slug] = {**meta, **(gates_now.get("gates", {}).get(slug) or {}),
                       "transits_today": today, "tanker_transits_today": today_t}
    fresh = {**({"ships": gates_now["as_of"]} if gates_now.get("as_of") else {}), **(extra_fresh or {})}
    return {"v": 1, "as_of": iso(now), "headlines": compute(store.read_events(), rows, gates_now, now), "gates": gates,
            "fresh": freshness(store.read_status(), fresh),
            "fires": {k: fires[k] for k in ("as_of", "detections", "occupied") if k in fires}}
