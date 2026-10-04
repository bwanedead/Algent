"""
Run-scoped read cache — a page is fetched once per article, however many stages ask for it.

Measured on a live rail: the gauntlet made 59 page reads that covered only 27 distinct pages.
The IUCN species page was fetched 6 times and one Current Biology attachment 5 times; 24 reads
went through the paid crawler and only 13 of those were distinct. Every repeat returned the same
page. None of it bought anything, and page reads are the scarcest resource this newsroom has.

Two causes, both structural:

- Each enrichment lane opens its own snapshot scope, which RESETS the snapshot store, so the
  counter-perspective lane had no memory of what the primary-source lane read a minute earlier.
- The read path RECORDED snapshots for grounding but never CHECKED them before fetching.

This cache sits above both: installed once for the whole rail run, consulted before every fetch.

RULES
- Only a GOOD read is cached. A thin, blocked or failed read is exactly the case where a retry —
  often with the paid crawler — is the right move, so it must not be answered from cache.
- A cached good read satisfies a later request for the same page at ANY richness. A paid "rich"
  read of a page we already hold in full is pure waste of the scarcest credit.
- A hit re-records the snapshot. Grounding is judged per stage from the snapshot store, and a
  stage that got a page from cache has still read it — it must not be downgraded for that.
- Persisted to the run directory, so `newsroom resume` reuses what the failed attempt read.

With no scope installed (standalone agents, tests) every call is a no-op and behaviour is exactly
what it was before.
"""

from __future__ import annotations

import contextvars
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


class _Cache:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.entries: dict[str, dict[str, Any]] = {}
        self.hits = 0
        self.misses = 0
        if path is not None and path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a torn line from a killed run must not lose the rest
                if isinstance(row, dict) and row.get("key") and isinstance(row.get("result"), dict):
                    self.entries[row["key"]] = row["result"]


_active: contextvars.ContextVar[_Cache | None] = contextvars.ContextVar(
    "read_cache", default=None,
)


def key(url: str) -> str:
    """Same page, same key: drop the fragment and a trailing slash, lowercase scheme and host."""
    try:
        parts = urlsplit((url or "").strip())
    except ValueError:
        return (url or "").strip()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def get(url: str) -> dict[str, Any] | None:
    """A previously read good result for this page, or None."""
    cache = _active.get()
    if cache is None or not url:
        return None
    hit = cache.entries.get(key(url))
    if hit is None:
        cache.misses += 1
        return None
    cache.hits += 1
    return dict(hit)


def put(url: str, result: dict[str, Any]) -> None:
    """Remember a GOOD read. Anything less stays retryable."""
    cache = _active.get()
    if cache is None or not url or not isinstance(result, dict):
        return
    if result.get("quality") != "good" or not result.get("content"):
        return
    k = key(url)
    if k in cache.entries:
        return
    cache.entries[k] = dict(result)
    if cache.path is not None:
        try:
            cache.path.parent.mkdir(parents=True, exist_ok=True)
            with cache.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"key": k, "result": result}, ensure_ascii=False) + "\n")
        except OSError:
            pass  # losing persistence costs a re-read on resume, never the run


def stats() -> dict[str, int]:
    cache = _active.get()
    if cache is None:
        return {"pages": 0, "hits": 0, "misses": 0}
    return {"pages": len(cache.entries), "hits": cache.hits, "misses": cache.misses}


@contextmanager
def scoped(path: Path | None = None) -> Iterator[None]:
    """Install one cache for a whole run. Nested scopes reuse the outer one.

    Reusing rather than replacing is the point: the enrichment lanes each open their own scopes
    for snapshots and budget, and a cache that reset with them would reproduce the exact bug it
    exists to fix.
    """
    if _active.get() is not None:
        yield
        return
    token = _active.set(_Cache(path))
    try:
        yield
    finally:
        _active.reset(token)


def search_key(kind: str, query: str) -> str:
    """Identical search, identical key: case and whitespace do not make a new question."""
    return f"search:{(kind or 'keyword').lower()}:{' '.join((query or '').lower().split())}"


def get_search(kind: str, query: str) -> dict[str, Any] | None:
    """A search this run already ran with results. Searches spend Tavily credit too."""
    cache = _active.get()
    if cache is None or not (query or "").strip():
        return None
    hit = cache.entries.get(search_key(kind, query))
    if hit is None:
        return None
    cache.hits += 1
    return dict(hit)


def put_search(kind: str, query: str, result: dict[str, Any]) -> None:
    """Remember a search that returned results. An error or an empty answer stays retryable."""
    cache = _active.get()
    if cache is None or not (query or "").strip() or not isinstance(result, dict):
        return
    if result.get("error") or not result.get("results"):
        return
    k = search_key(kind, query)
    if k in cache.entries:
        return
    cache.entries[k] = dict(result)
    if cache.path is not None:
        try:
            with cache.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"key": k, "result": result}, ensure_ascii=False) + chr(10))
        except OSError:
            pass
