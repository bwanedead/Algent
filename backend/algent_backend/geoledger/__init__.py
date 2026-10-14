"""
Geospatial asset ledger: the persistent, geolocated entity layer under the desk's prose (docs/architecture/geoledger.md).

    contracts   Asset (a place or named thing) and StatusEvent (somebody's dated word about its state), append-only
    store       the JSONL ledger on disk + in-memory view
    match       transliteration-tolerant name matching with hard guards
    seed_wri / seed_osm   open data (WRI Global Power Plant Database, OpenStreetMap via Overpass)
    materials / extract / ingest   enumerated entity-level events out of stored text, grounded and matched
    backfill    read the stored corpus once
    publish     the Supabase tables the site reads (migration 009)

Public surface: ``Ledger``, ``Asset``, ``StatusEvent``, ``ingest.add_event``, ``ingest.attach``.
"""

from .contracts import Asset, StatusEvent
from .store import Ledger

__all__ = ["Asset", "Ledger", "StatusEvent"]
