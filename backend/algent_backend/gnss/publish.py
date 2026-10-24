"""
Publish the GNSS picture as documents (the site reads documents, never tables: docs/architecture/published-content.md).

    gnss/latest.json    the newest day: our zones and GPSJam's top band with their provenance, plus a short per-day history (the page's trend)
    live/gnss.json      the globe overlay: the same newest day, compact (one dot per zone), with the legend's provenance

Both are built from the local store, so they are rebuildable at will, and an unchanged document costs no request (``publishing/object_docs``, ``live/snapshots``).
Never raises: the local record is the record, publishing is an addition.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from algent_backend.publishing import site_data

from . import flags, store
from .contracts import COVERAGE, Zone


def row(z: dict[str, Any]) -> dict[str, Any]:
    """A stored zone as the site reads it (``on_date``; per-source constants live at document level)."""
    return {"id": z["id"], "on_date": z["date"], "source": z["source"], "cell": z["cell"], "lat": z["lat"], "lon": z["lon"], "size_deg": z["size_deg"],
            "country": z.get("country", ""), "severity": z["severity"], "degraded_share": z["degraded_share"], "aircraft": z["aircraft"],
            "flag": z.get("flag", ""), "cross_check": z.get("cross_check", "")}


def newest_day(today: date | None = None) -> str:
    days = [d for d in store.zone_days() if d <= (today or date.today()).isoformat()]
    return days[-1] if days else ""


def history(today: date) -> list[dict[str, Any]]:
    """One line per recent day, ours only: how many zones, how many high, how many flagged. Oldest first."""
    floor = (today - timedelta(days=flags.HISTORY_PUBLISH_DAYS)).isoformat()
    out = []
    for d in store.zone_days():
        if floor <= d <= today.isoformat():
            ours = store.load_zones(d).get("zones", [])
            out.append({"day": d, "zones": len(ours), "high": sum(1 for z in ours if z["severity"] == "high"), "flagged": sum(1 for z in ours if z.get("flag"))})
    return out


def latest_doc(today: date | None = None) -> dict[str, Any] | None:
    today = today or date.today()
    day = newest_day(today)
    if not day:
        return None
    doc = store.load_zones(day)
    return {"day": day, "generated_at": doc.get("generated_at", ""), "samples": doc.get("samples", 0), "baseline_days": doc.get("baseline_days", 0),
            "baseline_since": doc.get("baseline_since", ""), "coverage": COVERAGE, "ours": [row(z) for z in doc.get("zones", [])],
            "gpsjam": [row(z) for z in doc.get("gpsjam", [])], "history": history(today)}


def snapshot_doc(today: date | None = None) -> dict[str, Any] | None:
    """The globe overlay's document (``live/gnss.json``): the newest day's zones, compact. None before any zone file exists.
    Our own zones carry ``src`` "o", GPSJam's "g" (its top band only, which is all that is stored); ``p`` is provenance for the legend."""
    day = newest_day(today)
    if not day:
        return None
    doc = store.load_zones(day)
    ours, theirs = doc.get("zones", []), doc.get("gpsjam", [])
    dot = lambda z, src: {"lat": z["lat"], "lon": z["lon"], "r": z["size_deg"], "s": z["severity"], "share": z["degraded_share"], "f": z.get("flag", ""), "src": src}  # noqa: E731
    return {"v": 1, "as_of": doc.get("generated_at", ""), "date": day, "zones": [dot(z, "o") for z in ours] + [dot(z, "g") for z in theirs],
            "p": {"ours": {"basis": "our_estimate", "coverage_note": COVERAGE["ohmega_adsb"], "baseline_since": doc.get("baseline_since", ""),
                           "baseline_days": doc.get("baseline_days", 0)},
                  "gpsjam": {"basis": "third_party", "coverage_note": COVERAGE["gpsjam"]}}}


def documents(today: date | None = None) -> dict[str, Any]:
    latest = latest_doc(today)
    return {"gnss/latest.json": latest} if latest else {}


def publish_snapshot(*, today: date | None = None, http: Any = None) -> dict[str, Any]:
    """The overlay to the public live bucket; the pass is local-first (the zone file it is built from is already on disk)."""
    from algent_backend.live import snapshots

    doc = snapshot_doc(today)
    return snapshots.publish({"gnss": doc}, http=http) if doc else {"skipped": "no zones yet"}


def publish(*, today: date | None = None, http: Any = None) -> dict[str, Any]:
    files = site_data.publish_built(lambda: documents(today), http=http) if newest_day(today) else {"skipped": "no zones yet"}
    return {"files": files, "snapshot": publish_snapshot(today=today, http=http)}
