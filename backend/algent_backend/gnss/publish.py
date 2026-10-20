"""
Publish GNSS zones to the site database (migration 014: ``gnss_zones``, anon read-only).

Same contract as the other publishers: never raises, idempotent, a no-op without ``DATABASE_URL``. An open day's zones change as the day fills, so a day
is upserted (``on conflict (id) do update``) whenever its document was regenerated; GPSJam cells are sent only from ``GPSJAM_PUBLISH_SHARE`` upward (their top band). Days older
than ``PUBLISH_DAYS`` are not resent.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from algent_backend.publishing.published_db import _run

from . import flags, store
from .contracts import COVERAGE, Zone

_COLS = ("id", "on_date", "source", "cell", "lat", "lon", "size_deg", "country", "severity", "degraded_share", "aircraft", "flag", "cross_check",
         "basis", "coverage_note", "baseline_since")
_ROW = (f"insert into gnss_zones ({', '.join(_COLS)}) values ({', '.join(['%s'] * len(_COLS))}) on conflict (id) do update set "
        "severity = excluded.severity, degraded_share = excluded.degraded_share, aircraft = excluded.aircraft, flag = excluded.flag, "
        "cross_check = excluded.cross_check, country = excluded.country")


def row(z: Zone) -> tuple:
    return (z.id, z.date, z.source, z.cell, z.lat, z.lon, z.size_deg, z.country, z.severity, z.degraded_share, z.aircraft, z.flag, z.cross_check,
            z.basis, z.coverage_note, z.baseline_since or None)


def zones_for(day: str) -> list[Zone]:
    doc = store.load_zones(day)
    ours = [Zone.model_validate(z) for z in doc.get("zones", [])]
    theirs = [Zone.model_validate(z) for z in doc.get("gpsjam", []) if z["degraded_share"] >= flags.GPSJAM_PUBLISH_SHARE]
    return ours + theirs


def publish(*, today: date | None = None, connect: Callable[[], Any] | None = None) -> dict[str, Any]:
    today = today or date.today()
    floor = (today - timedelta(days=flags.PUBLISH_DAYS)).isoformat()
    marks = store.published_days()
    send: list[Zone] = []
    new_marks = dict(marks)
    for day in store.zone_days():
        if day < floor:
            continue
        doc = store.load_zones(day)
        stamp = str(doc.get("generated_at", ""))
        if marks.get(day) == stamp:
            continue                                        # this version of the day is already on the site
        send += zones_for(day)
        new_marks[day] = stamp
    if not send:
        return {"db": True, "zones": 0, "note": "nothing new"}

    def work(conn: Any) -> dict:
        with conn.cursor() as cur:
            cur.executemany(_ROW, [row(z) for z in send])
        return {"zones": len(send)}

    result = _run(work, connect)
    if result.get("db"):
        store.save_published(new_marks)
    return result


def snapshot_doc(today: date | None = None) -> dict[str, Any] | None:
    """The globe overlay's document (``live/gnss.json``): the newest day's zones, compact. None before any zone file exists.
    Our own zones carry ``src`` "o", GPSJam's "g" (only its top band, like the database); ``p`` is provenance for the legend."""
    days = [d for d in store.zone_days() if d <= (today or date.today()).isoformat()]
    if not days:
        return None
    doc = store.load_zones(days[-1])
    ours, theirs = doc.get("zones", []), [z for z in doc.get("gpsjam", []) if z["degraded_share"] >= flags.GPSJAM_PUBLISH_SHARE]
    row = lambda z, src: {"lat": z["lat"], "lon": z["lon"], "r": z["size_deg"], "s": z["severity"], "share": z["degraded_share"], "f": z["flag"], "src": src}  # noqa: E731
    return {"v": 1, "as_of": doc.get("generated_at", ""), "date": days[-1], "zones": [row(z, "o") for z in ours] + [row(z, "g") for z in theirs],
            "p": {"ours": {"basis": "our_estimate", "coverage_note": COVERAGE["ohmega_adsb"], "baseline_since": doc.get("baseline_since", ""),
                           "baseline_days": doc.get("baseline_days", 0)},
                  "gpsjam": {"basis": "third_party", "coverage_note": COVERAGE["gpsjam"]}}}


def publish_snapshot(*, today: date | None = None, http: Callable[..., int] | None = None) -> dict[str, Any]:
    """Upload the overlay document to the public live bucket (no-op without Supabase credentials; unchanged documents are skipped by hash)."""
    from algent_backend.live import snapshots

    doc = snapshot_doc(today)
    return snapshots.publish({"gnss": doc}, http=http) if doc else {"skipped": "no zones yet"}
