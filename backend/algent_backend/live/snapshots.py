"""
Live snapshots — compact JSON documents (the big ones gzipped, ``*.json.gz``) for the site's map, written to the PUBLIC Storage bucket ``published-assets`` under
``live/`` (the same bucket and uploader as the article images, ``publishing/asset_store``). One file per layer (``vessels``,
``aircraft``, ``fires``, ``summary``, ``energy``, ``tracks/...``), rewritten every minute or so with a short cache header; the
site polls them. Nothing per-object goes to Postgres.

Same contract as the other publishers: never raises, a no-op without ``SUPABASE_URL`` + ``SUPABASE_SERVICE_ROLE_KEY``, an
unchanged file is skipped (content hash). Small documents also keep a local copy (``live_store/docs/<name>.json``) so the
other process (timers vs the always-on stream service) can read them.

The vessel and aircraft layers go out as ``points`` (``live/points.py``: the world-zoom glow) + ``tiles/...`` (``live/tiles.py``: zoomed-in detail); ``publish`` sends a cycle's tiles
BEFORE the rest, so a client never reads a ``tiles/index`` that names tiles not yet uploaded.
"""

from __future__ import annotations

import gzip
import json
from typing import Any, Callable

from algent_backend import contracts
from algent_backend.publishing import asset_store

from . import flags, store


def encode(doc: Any) -> bytes:
    return json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


#: Documents big enough to be worth compressing; they are uploaded as ``<name>.json.gz`` (see ``flags.GZIP_LEVEL``). The site inflates them.
GZIPPED = ("vessels", "aircraft", "coverage", "tracks/", "density", "tiles/", "points")


def encode_gz(doc: Any) -> bytes:
    """Deterministic gzip of the compact JSON (mtime 0), so an unchanged document hashes the same and is not re-uploaded."""
    return gzip.compress(encode(doc), compresslevel=flags.GZIP_LEVEL, mtime=0)


def publish(docs: dict[str, Any], *, local: tuple[str, ...] = (), http: Callable[..., int] | None = None) -> dict[str, Any]:
    """Upload ``{name: document}`` as ``live/<name>.json``; the names in ``local`` also keep a local copy. Returns the uploader's tally."""
    for name in local:
        if name in docs:
            store.write_doc(name, docs[name])
    def stamped(n: str) -> Any:
        """The document with the schema stamp its contract declares (contracts/): the browser's snapshot reader checks the major."""
        stamp = contracts.stamp_for(f"live/{n}.json", docs[n])
        return {"schema": stamp, **docs[n]} if stamp else docs[n]

    def encoded(names: list[str]) -> dict[str, bytes]:
        return {(f"/live/{n}.json.gz" if n.startswith(GZIPPED) else f"/live/{n}.json"): encode_gz(stamped(n)) if n.startswith(GZIPPED) else encode(stamped(n))
                for n in names}

    tile_names = [n for n in docs if n.startswith("tiles/") and n != "tiles/index"]
    rest = [n for n in docs if n not in tile_names]
    kw: dict[str, Any] = {"http": http, "manifest": store.root() / "asset_hashes.json", "cache_control": flags.SNAPSHOT_CACHE}
    first = asset_store.upload(encoded(tile_names), workers=flags.UPLOAD_WORKERS, **kw)
    second = asset_store.upload(encoded(rest), **kw)
    out = {k: first[k] + second[k] for k in ("assets", "skipped")}
    out["failed"] = first["failed"] + second["failed"]
    out["ok"] = first["ok"] and second["ok"]
    if note := second.get("note") or first.get("note"):
        out["note"] = note
    return out
