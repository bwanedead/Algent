"""
Public data series (the instruments store): chokepoint transits, prices, indices, gas storage, and our own live-feed daily counts. One observation
per period, latest revision winning. Basis follows the stats registry: our own counts (``live_*``) are ``our_count``, everything fetched from a
publisher is ``official``. Each chokepoint's series attach to a place entity at its narrowest point.
"""

from __future__ import annotations

from collections.abc import Iterator

from algent_backend.instruments import catalog, store

from .. import flags
from ..norm import slug
from ..sink import Sink
from .base import Source, Unit, digest_of, mark


def _emit(series, rows: list, place: dict | None, sink: Sink) -> None:                   # noqa: ANN001 - instruments Series
    ent = ""
    if place:
        ent = f"place:chokepoint:{slug(place['label'])}"
        sink.declare(ent, "place", place["label"], lat=place["lat"], lon=place["lon"], rank=flags.RANK_DECLARED, attrs={"kind": "chokepoint"})
    basis = "our_count" if series.id.startswith("live_") else "official"
    for o in rows:
        sink.observation(series.id, o.period, o.value, entity=ent, unit=series.unit, basis=basis, label=series.name, source_url=o.source_url or series.source_url,
                         note=f"{series.source}{' (revised)' if o.revised else ''}; {series.frequency}")


def _units() -> Iterator[Unit]:
    sites = {s["series_id"]: s for s in catalog.chokepoint_sites()}
    for sid in store.stored_ids():
        try:
            series = catalog.get_series(sid)
        except KeyError:
            continue
        rows = store.history(sid)
        site = sites.get(sid) or sites.get(sid.replace("_tanker_transits", "_transits"))
        last = rows[-1].period[:10] if rows else ""
        yield Unit(f"series:{sid}", digest_of([(o.period, o.value) for o in rows]), lambda sink, series=series, rows=rows, site=site: _emit(series, rows, site, sink),
                   date=last, path=f"instruments_store/series/{sid}.jsonl")


def _watermark() -> str:
    folder = store.store_dir() / "series"
    return mark(folder.glob("*.jsonl")) if folder.is_dir() else "none"


SOURCE = Source("instruments", "instruments", _units, _watermark)
