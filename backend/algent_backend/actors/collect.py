"""
Collector — run the sources and append what is new to the store.

One source at a time, each isolated: a source down, blocked (HTTP 403) or returning something
unparseable is recorded in the report and never stops the others. Inside a source, a single failing
indicator is reported on its own row. Everything is free and keyless; nothing here calls a model.
"""

from __future__ import annotations

from typing import Any

from algent_backend.polite_http import SourceError, SourceUnavailable

from . import catalog, store
from .sources import LEADER_SOURCE, OBSERVATION_SOURCES, wikidata

SOURCE_KEYS = [*OBSERVATION_SOURCES, LEADER_SOURCE]


def _observations(key: str) -> list[dict[str, Any]]:
    todo = catalog.for_source(key)
    try:
        fetched = OBSERVATION_SOURCES[key](todo, None)
    except SourceUnavailable as exc:
        return [{"source": key, "id": i.id, "status": "blocked", "error": str(exc)} for i in todo]
    except (SourceError, OSError) as exc:
        return [{"source": key, "id": i.id, "status": "error", "error": str(exc)} for i in todo]
    rows = []
    for ind in todo:
        got = fetched.get(ind.id, [])
        if isinstance(got, str):
            rows.append({"source": key, "id": ind.id, "status": "error", "error": got})
        else:
            rows.append({"source": key, "id": ind.id, "status": "ok", "fetched": len(got),
                         **store.append(ind.id, got).model_dump()})
    return rows


def _leaders() -> list[dict[str, Any]]:
    try:
        rows = wikidata.fetch_leaders()
    except SourceUnavailable as exc:
        return [{"source": LEADER_SOURCE, "id": "leaders", "status": "blocked", "error": str(exc)}]
    except (SourceError, OSError) as exc:
        return [{"source": LEADER_SOURCE, "id": "leaders", "status": "error", "error": str(exc)}]
    return [{"source": LEADER_SOURCE, "id": "leaders", "status": "ok", "fetched": len(rows),
             **store.append_leaders(rows).model_dump()}]


def collect(sources: list[str] | None = None) -> dict[str, Any]:
    """Fetch the named sources (default all) into the store; returns one report document."""
    keys = sources or SOURCE_KEYS
    unknown = [k for k in keys if k not in SOURCE_KEYS]
    if unknown:
        raise ValueError(f"unknown source {unknown[0]!r}; choose from {', '.join(SOURCE_KEYS)}")
    rows: list[dict[str, Any]] = []
    for key in keys:
        try:
            rows += _leaders() if key == LEADER_SOURCE else _observations(key)
        except Exception as exc:   # a parser/shape surprise in one source must not take the others down
            rows.append({"source": key, "id": "*", "status": "error", "error": f"{type(exc).__name__}: {exc}"})
    tally = {st: sum(r["status"] == st for r in rows) for st in ("ok", "blocked", "error")}
    return {"sources": keys, "store": str(store.store_dir()), **tally, "rows": rows}
