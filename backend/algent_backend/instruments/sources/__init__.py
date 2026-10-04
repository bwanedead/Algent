"""
Provider modules — one per data source, each exposing ``fetch(series, since) -> list[Observation]``.

``PROVIDERS`` is the registry the collector resolves ``Series.fetcher`` through. Adding a provider
is one module here plus one line below; adding a series on an existing provider touches only the
catalog.
"""

from __future__ import annotations

from typing import Callable

from . import agsi, ecb, eurostat, fiscaldata, portwatch, treasury, yahoo

PROVIDERS: dict[str, Callable] = {
    "portwatch": portwatch.fetch,
    "yahoo": yahoo.fetch,
    "treasury": treasury.fetch,
    "fiscaldata": fiscaldata.fetch,
    "ecb": ecb.fetch,
    "eurostat": eurostat.fetch,
    "agsi": agsi.fetch,
}
