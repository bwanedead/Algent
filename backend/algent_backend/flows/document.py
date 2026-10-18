"""
The published ``flows`` document — everything the site's flow layer draws, in one small JSON object (tens of KB, no tracks).

    ais     OUR OWN observed ship lanes: places (chokepoints, port regions) with visit rates and anomalies, lanes with per-class rates over
            the last 7 and 30 days and their drawn path, how long we have been watching, and a coverage caveat. Live-ish: rebuilt every run.
    grain   wheat, corn and soybeans between countries: annual values as the exporter reported them (UN Comtrade). A different source
            and cadence from ``ais``; the site draws it differently so the two are never confused.
    money   merchandise exports in US dollars between the largest economies, same source and caveats as grain.
    places  the countries any trade flow mentions, with a point for the arc ends.

Pure: ``build`` takes the tracker's aggregates and the trade cache and returns the document.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone
from typing import Any

from . import flags, rates
from .classes import CLASSES
from .network import PLACES, lane_line
from .trade.countries import BY_ISO
from .tracker import day_of

AIS_NOTE = ("Ships heard by volunteer AIS receivers near coasts, ports and straits; open ocean and ships with their transponder off are not heard. "
            "A ship seen in two places is counted on every lane between them. Compare a lane with itself over time, not with the world's total.")
TRADE_NOTE = "Annual values as the exporting country reported them to the UN (newest year it has filed). A year's trade, not a shipment."


def _r(x: float) -> float:
    return round(x, 2)


def _ais(days: dict[str, dict[str, Any]], samples: dict[str, list[float]], now: float) -> dict[str, Any]:
    w7, w30 = flags.WINDOWS
    lanes7, lanes30 = rates.lane_rates(days, now, w7), rates.lane_rates(days, now, w30)
    vis7, vis30 = rates.visit_rates(days, now, w7), rates.visit_rates(days, now, w30)
    anomaly = rates.anomalies(days, now)
    watched = sorted(d for d, v in days.items() if v["secs"] >= flags.WATCHED_SHARE * 86400)
    lanes = []
    for key in sorted(set(lanes7) | set(lanes30)):
        a, b = key.split(">")
        s7, s30 = lanes7.get(key), lanes30.get(key)
        hours = samples.get(key) or []
        lanes.append({"a": a, "b": b, "line": [[round(p[0], 2), round(p[1], 2)] for p in lane_line(a, b)],
                      "r7": _r(sum(s7["by"].values())) if s7 else 0.0, "r30": _r(sum(s30["by"].values())) if s30 else 0.0,
                      "by": (s7 or s30 or {"by": {}})["by"], "n": (s30 or s7 or {"n": 0})["n"],
                      "inf": _r(s30["inf"] / s30["n"]) if s30 and s30["n"] else 0.0,
                      **({"h": round(statistics.median(hours), 1)} if hours else {})})
    places = []
    for p in PLACES:
        v7, v30 = vis7.get(p.id), vis30.get(p.id)
        if not v7 and not v30 and p.kind != "chokepoint":
            continue
        row: dict[str, Any] = {"id": p.id, "label": p.label, "kind": p.kind, "lat": p.lat, "lon": p.lon,
                               "r7": _r(sum(v7["by"].values())) if v7 else 0.0, "r30": _r(sum(v30["by"].values())) if v30 else 0.0,
                               "by": (v7 or v30 or {"by": {}})["by"]}
        if (a := anomaly.get(p.id)):
            row.update(usual=a["usual"], last=a["last"], z=a["z"], dir=a["dir"], day=a["day"])
        places.append(row)
    return {"since": min(days) if days else None, "days": len(watched), "windows": [w7, w30], "note": AIS_NOTE,
            "learning": len(watched) < flags.ANOMALY_MIN_DAYS + 1, "places": places, "lanes": lanes}


def _trade_block(block: dict[str, Any]) -> dict[str, Any]:
    return {"label": block["label"], "flows": block["flows"], "missing": block.get("missing", [])}


def build(days: dict[str, dict[str, Any]], samples: dict[str, list[float]], trade: dict[str, Any] | None, now: float) -> dict[str, Any]:
    ais = _ais(days, samples, now)
    doc: dict[str, Any] = {"v": 1, "as_of": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(timespec="seconds"), "today": day_of(now),
                           "classes": [{"id": c, "label": label} for c, label in CLASSES], "ais": ais}
    used: set[str] = set()
    if trade:
        grain = {k: _trade_block(v) for k, v in (trade.get("grain") or {}).items() if v.get("flows")}
        money = _trade_block(trade["money"]) if (trade.get("money") or {}).get("flows") else None
        meta = {"fetched_at": trade.get("fetched_at"), "source": trade.get("source"), "source_url": trade.get("source_url"), "note": TRADE_NOTE}
        doc["grain"] = {**meta, "commodities": grain}
        if money:
            doc["money"] = {**meta, **money}
        for b in [*grain.values(), *([money] if money else [])]:
            used |= {f["from"] for f in b["flows"]} | {f["to"] for f in b["flows"]}
    doc["places"] = {iso: {"name": BY_ISO[iso].name, "lat": BY_ISO[iso].lat, "lon": BY_ISO[iso].lon} for iso in sorted(used) if iso in BY_ISO}
    return doc
