"""
A satellite pass (what the ``ohmega-satellite`` timer runs): rank the watch list, take the sites that are due, look at each, build the document, upload
the chips and then the document (chips first, so a page never names an image that is not there yet). Free: no model, no key.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from algent_backend.geoledger.store import Ledger
from algent_backend.live import snapshots
from algent_backend.publishing import asset_store

from . import document, flags, observe, store, watchlist
from .sources import Imagery, PlanetaryComputer

CHIP_CACHE = "max-age=31536000, immutable"       # chip file names carry the scene date and a hash: they never change


def publish(doc: dict[str, Any], *, http: Callable[..., int] | None = None) -> dict[str, Any]:
    files = {}
    for key in document.chip_keys(doc):
        data = store.read_bytes("chips/" + key.split("/", 1)[1])
        if data:
            files["/" + key] = data
    up = asset_store.upload(files, http=http, manifest=store.root() / "asset_hashes.json", cache_control=CHIP_CACHE)
    if not up["ok"]:
        return {"chips": up, "document": {"skipped": "chip upload failed; the document names them, so it waits"}}
    return {"chips": up, "document": snapshots.publish({"satellite": doc}, http=http)}


def run(*, src: Imagery | None = None, ledger: Ledger | None = None, now: datetime | None = None, limit: int | None = None,
        only: list[str] | None = None, do_publish: bool = True, http: Callable[..., int] | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    src = src or PlanetaryComputer()
    sites = watchlist.build(ledger or Ledger(), now)
    store.write_json("watch.json", [s.to_json() for s in sites])
    last = {s.id: (store.read_json(f"sites/{s.id}/state.json", {}) or {}).get("checked_at") for s in sites}
    if only:
        due = [s for s in sites if s.id in only]
    else:
        due = watchlist.select_due(sites, {k: v for k, v in last.items() if v}, now.timestamp(), limit)
    pass_id = now.strftime("%Y%m%dT%H%M%SZ")
    t0 = time.time()
    seen = [observe.observe(s, src, now, pass_id) for s in due]
    doc = document.build(sites, now, budget={"id": pass_id, "sites_taken": len(due), "cap": flags.MAX_SITES_PER_PASS, "seconds": round(time.time() - t0, 1)})
    store.write_json("doc.json", doc)
    out: dict[str, Any] = {"as_of": doc["as_of"], "watched": len(sites), "taken": [s.id for s in due], "counts": doc["counts"],
                           "states": {r["site_id"]: r["optical"]["state"] for r in seen}}
    if do_publish:
        out["publish"] = publish(doc, http=http)
    return out
