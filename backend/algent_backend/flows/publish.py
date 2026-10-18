"""
Publish the ``flows`` document to the public Storage bucket as ``live/flows.json`` — the same path every other live product takes
(``live/snapshots.publish``: a no-op without ``SUPABASE_URL`` + ``SUPABASE_SERVICE_ROLE_KEY``, an unchanged document skipped by hash,
never raises). The site polls it like ``summary``.

``run`` is what the ``ohmega-flows`` timer calls: refresh the trade picture when it is due, read the tracker's aggregates the stream
service wrote, build, publish. A machine that holds no tracker aggregates (a laptop) does not publish unless asked to: it would
replace the server's document with one that has no ships in it.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from algent_backend.live import snapshots

from . import document, store
from .tracker import LaneTracker
from .trade import refresh as trade_refresh


def build_now(now: float | None = None, *, trade: dict[str, Any] | None = None) -> tuple[dict[str, Any], LaneTracker]:
    """The document from what is on disk now (and the tracker it was built from)."""
    now = time.time() if now is None else now
    tracker = LaneTracker.load()
    return document.build(tracker.days, tracker.samples, trade if trade is not None else trade_refresh.load(), now), tracker


def run(*, now: float | None = None, force_trade: bool = False, publish: bool = True, allow_empty: bool = False,
        http: Callable[..., int] | None = None, get: Callable[..., str] | None = None) -> dict[str, Any]:
    stamp = time.time() if now is None else now
    trade = trade_refresh.refresh(datetime.fromtimestamp(stamp, tz=timezone.utc), force=force_trade, get=get)
    doc, tracker = build_now(stamp, trade=trade or None)
    ais = doc["ais"]
    out: dict[str, Any] = {"as_of": doc["as_of"], "ais_days": ais["days"], "places": len(ais["places"]), "lanes": len(ais["lanes"]),
                           "grain_flows": sum(len(c["flows"]) for c in (doc.get("grain") or {}).get("commodities", {}).values()),
                           "money_flows": len((doc.get("money") or {}).get("flows", []))}
    store.write_json("flows_doc.json", doc)
    if not publish:
        return out
    if not tracker.days and not allow_empty:
        out["publish"] = {"skipped": "no lane aggregates on this machine (the stream service holds them)"}
        return out
    out["publish"] = snapshots.publish({"flows": doc}, http=http)
    return out
