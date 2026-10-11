"""
Live snapshots — compact JSON documents for the site's map, written to the PUBLIC Storage bucket ``published-assets`` under
``live/`` (the same bucket and uploader as the article images, ``publishing/asset_store``). One file per layer (``vessels``,
``aircraft``, ``fires``, ``summary``, ``energy``, ``tracks/...``), rewritten every minute or so with a short cache header; the
site polls them. Nothing per-object goes to Postgres.

Same contract as the other publishers: never raises, a no-op without ``SUPABASE_URL`` + ``SUPABASE_SERVICE_ROLE_KEY``, an
unchanged file is skipped (content hash). Small documents also keep a local copy (``live_store/docs/<name>.json``) so the
other process (timers vs the always-on stream service) can read them.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from algent_backend.publishing import asset_store

from . import flags, store


def encode(doc: Any) -> bytes:
    return json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def publish(docs: dict[str, Any], *, local: tuple[str, ...] = (), http: Callable[..., int] | None = None) -> dict[str, Any]:
    """Upload ``{name: document}`` as ``live/<name>.json``; the names in ``local`` also keep a local copy. Returns the uploader's tally."""
    for name in local:
        if name in docs:
            store.write_doc(name, docs[name])
    files = {f"/live/{name}.json": encode(doc) for name, doc in docs.items()}
    return asset_store.upload(files, http=http, manifest=store.root() / "asset_hashes.json", cache_control=flags.SNAPSHOT_CACHE)
