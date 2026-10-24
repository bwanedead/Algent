"""
Join events to the geoledger — an event within a few km of a tracked asset (power plant, depot, port, ...) carries that asset.

This is a plain spatial join, not a claim that the asset was hit: the event line says "near", the asset page says what the ledger knows.
It never writes a status event to the ledger (a machine-coded GDELT dot is not evidence an asset was struck); a curated source's
confirmed hit is the geoledger's own extraction to make. Loads the ledger once per call and degrades to "no assets" if it is absent.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

from . import flags
from .contracts import AssetRef, ConflictEvent


@lru_cache(maxsize=1)
def _default_bands() -> dict[int, list[Any]]:
    from algent_backend.geoledger.store import Ledger

    return _buckets(Ledger())                               # one load per process: a catch-up run attaches several files


def _buckets(ledger: Any) -> dict[int, list[Any]]:
    """Live assets by whole degree of latitude, so a lookup scans three bands, not the whole ledger."""
    out: dict[int, list[Any]] = {}
    for a in ledger.live():
        if a.lat is not None and a.lon is not None:
            out.setdefault(math.floor(a.lat), []).append(a)
    return out


def attach(events: list[ConflictEvent], ledger: Any | None = None) -> int:
    """Fill ``assets`` on every located event; returns how many events matched at least one asset."""
    located = [e for e in events if e.lat is not None and e.lon is not None]
    if not located:
        return 0
    try:
        from algent_backend.geoledger.match import km_between

        bands = _buckets(ledger) if ledger is not None else _default_bands()
    except Exception:  # noqa: BLE001 - the join is an enrichment, never a gate
        return 0
    hit = 0
    for e in located:
        row = math.floor(e.lat)
        cands = [a for r in (row - 1, row, row + 1) for a in bands.get(r, ())]
        near = sorted(((km_between((e.lat, e.lon), (a.lat, a.lon)), a) for a in cands if abs(a.lat - e.lat) <= flags.ASSET_KM / 100.0), key=lambda t: t[0])
        e.assets = [AssetRef(id=a.id, name=a.name, type=a.type, km=round(km, 1)) for km, a in near if km <= flags.ASSET_KM][: flags.ASSET_MAX]
        hit += bool(e.assets)
    return hit
