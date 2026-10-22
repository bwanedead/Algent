"""
Documents in Storage — where the desk's JSON documents live (docs/architecture/database-budget.md).

A published document (a daily report, a dossier, an actor page, the track record, an agent feed ...) is a gzipped canonical-JSON object in
the public ``published-assets`` bucket at ``docs/<path>.gz``; Postgres keeps only an index row (``published_intel_documents``: path, kind,
storage_key, size, sha256, visible, updated_at). Storage is outside the database-size quota; the index row is ~200 bytes, so rewriting a
document costs the database nothing but a hash comparison.

This module is the pure half: naming, canonical encoding, hashing, size caps. ``published_db.publish_documents`` does the I/O (reads the
known hashes, uploads what changed through ``asset_store``, then writes the index rows) and the CLI's ``db diet`` uses the same ``pack``.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from functools import cached_property
from typing import Any

from algent_backend.database import flags

#: Bucket prefix of every document object.
PREFIX = "docs/"
#: Documents change when a desk publishes (minutes apart at most): a short CDN window keeps a fresh publish visible, the site's own
#: ISR (``REVALIDATE_SECONDS``) is the real cache.
CACHE_CONTROL = "public, max-age=60"
_NUL = "\\u0000"


@dataclass(frozen=True)
class Packed:
    """One document ready to store: its index fields and the gzipped bytes."""

    path: str
    kind: str
    key: str                  # bucket key: docs/<path>.gz
    sha256: str               # of the canonical JSON (not of the gzip: a zlib upgrade must not look like a change)
    size_bytes: int           # canonical JSON length
    raw: bytes = b""

    @cached_property
    def gz(self) -> bytes:
        """The gzipped object, compressed on first use: a publish hashes hundreds of documents and uploads only the few that changed."""
        return gzip.compress(self.raw, compresslevel=6, mtime=0)

    @property
    def site_path(self) -> str:
        """The leading-slash form ``asset_store.upload`` takes."""
        return "/" + self.key


def object_key(path: str) -> str:
    return f"{PREFIX}{path}.gz"


def kind_of(path: str) -> str:
    return path.split("/", 1)[0].removesuffix(".json")


def canonical(body: Any) -> bytes:
    """Compact JSON with sorted keys and NUL dropped (Postgres jsonb never kept key order either, so nothing depended on it)."""
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).replace(_NUL, "").encode("utf-8")


def pack(path: str, body: Any) -> Packed:
    raw = canonical(body)
    return Packed(path=path, kind=kind_of(path), key=object_key(path), sha256=hashlib.sha256(raw).hexdigest(), size_bytes=len(raw),
                  raw=raw)


def over_cap(packed: Packed) -> str | None:
    """Why this document must not be written, or None. The cap is the bucket's own object limit (a larger upload would be rejected)."""
    if len(packed.gz) > flags.STORAGE_OBJECT_BYTES:
        return f"{packed.path}: {len(packed.gz)} bytes gzipped is over the {flags.STORAGE_OBJECT_BYTES} byte object limit"
    return None


def row_over_cap(label: str, text: str) -> str | None:
    """Why a single Postgres row of ``text`` must not be written (``ROW_CAP_BYTES``), or None."""
    n = len(text.encode("utf-8"))
    if n > flags.ROW_CAP_BYTES:
        return f"{label}: {n} bytes is over the {flags.ROW_CAP_BYTES} byte row cap (database-budget.md)"
    return None
