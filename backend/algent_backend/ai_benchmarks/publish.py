"""
Publish the AI benchmark document to the site: one JSON document, ``data/ai-benchmarks.json``, stored as a Storage object with an index row in ``published_intel_documents`` (the
table the site already reads every desk document from, so no migration or new RLS surface). Never raises, idempotent (upsert by path), and a
no-op without ``DATABASE_URL``: the contract of ``publishing/published_db`` (same as ``markets/publish``).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

from algent_backend.publishing.published_db import publish_documents

from . import derive, freshness, store
from .sources import INFO

PATH = "data/ai-benchmarks.json"
SCHEMA = "ohmega.ai-benchmarks/1"


def document(*, today: date | None = None) -> dict[str, Any]:
    today = today or datetime.now(UTC).date()
    results = store.current()
    catalog = store.benchmarks()
    views = [v for b in catalog.values() if (v := derive.view(b, results, as_of=today))]
    views.sort(key=lambda v: (-v["n_models"], v["name"]))
    health = freshness.source_health()
    return {
        "schema": SCHEMA, "as_of": datetime.now(UTC).isoformat(timespec="seconds"),
        "sources": [{**h, "page": INFO.get(h["source"], ("", "", ""))[1], "licence": INFO.get(h["source"], ("", "", ""))[2]} for h in health],
        "labs": derive.lab_summary(results), "benchmarks": views,
        "note": "Scores are as published by each source. 'measured' scores were run or collected independently of the lab; 'claimed' scores are the lab's own "
                "blog or model card, extracted automatically and unverified. Frontier = best measured score so far; models are placed by release date.",
    }


def publish(*, connect: Callable[[], Any] | None = None, doc: dict[str, Any] | None = None, http: Callable[..., int] | None = None) -> dict[str, Any]:
    try:
        return publish_documents({PATH: doc if doc is not None else document()}, connect=connect, http=http)
    except Exception as exc:  # noqa: BLE001 - the local store is the record; publishing is an addition
        return {"db": False, "note": f"{type(exc).__name__}: {str(exc)[:160]}"}
