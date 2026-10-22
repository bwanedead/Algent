"""
Publish the track record to the site: one JSON document, ``data/track-record.json``, stored as a Storage object with an index row in ``published_intel_documents`` (the table the
site already reads every desk document from, so no new migration or RLS surface). Never raises, idempotent (upsert by path), and a no-op
without ``DATABASE_URL``: the contract of ``publishing/published_db``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from algent_backend.publishing.published_db import publish_documents

from . import score

PATH = "data/track-record.json"


def publish(*, connect: Callable[[], Any] | None = None, doc: dict[str, Any] | None = None, http: Callable[..., int] | None = None) -> dict[str, Any]:
    try:
        return publish_documents({PATH: doc if doc is not None else score.track_record()}, connect=connect, http=http)
    except Exception as exc:  # noqa: BLE001 - the local store is the record; publishing is an addition
        return {"db": False, "note": f"{type(exc).__name__}: {str(exc)[:160]}"}
