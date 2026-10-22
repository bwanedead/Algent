"""
Published assets — the one uploader behind every public object (docs/architecture/database-budget.md, storage architecture).

Article hero/figure/chart images, live snapshots/tiles/points, satellite chips and the gzipped JSON documents (``doc_store``) all go
through ``upload``. The object key is the site path without its leading slash (``/analytics/<slug>/<name>`` -> ``analytics/<slug>/<name>``)
and the site reads it from ``NEXT_PUBLIC_DATA_BASE`` + the key. WHERE the bytes go is ``object_store``'s business (Cloudflare R2 by default,
Supabase Storage by a flag); this module owns the policy: content hash skip, parallelism, headers, never raising.

Contract: never raises into a run; idempotent (an object whose content hash matches the last upload is skipped, so nothing churns); a no-op
when no object store is configured or with ``ALGENT_DB_PUBLISH=0``. Environment only (``.env`` is not loaded), so a dev test run cannot reach
the live bucket. The access keys are SERVER-ONLY: never on the site (docs/credentials.md).
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any, Callable

from . import object_store

#: Supabase Storage's bucket (kept for the switch-back path); R2's bucket is ``R2_BUCKET``.
BUCKET = object_store.SUPABASE_BUCKET
_MIME = {".svg": "image/svg+xml", ".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg",
         ".jpeg": "image/jpeg", ".gif": "image/gif", ".json": "application/json", ".gz": "application/gzip"}

#: ``http(method, url, headers, body) -> status`` - injectable so tests need no network.
Http = Callable[[str, str, dict[str, str], bytes], int]


def enabled() -> bool:
    return object_store.select() is not None


def object_key(site_path: str) -> str:
    """``/analytics/<slug>/x.svg`` -> ``analytics/<slug>/x.svg`` (the bucket key)."""
    return site_path.lstrip("/")


def public_url(site_path: str, base: str | None = None) -> str:
    """The URL the site serves an asset from once it is in the bucket (``base`` overrides the configured public prefix)."""
    if base is not None:
        return f"{base.rstrip('/')}/{object_key(site_path)}"
    store = object_store.select(allow_unconfigured=True)
    return store.public_url(object_key(site_path)) if store else object_key(site_path)


def content_type(key: str) -> str:
    return _MIME.get(Path(key).suffix.lower()) or mimetypes.guess_type(key)[0] or "application/octet-stream"


def _manifest_path() -> Path:
    """Where the per-object content hashes live: server-local state, gitignored, never in the site checkout."""

    return object_store.held_dir() / "asset_hashes.json"


def _load(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _store_for(http: Http | None) -> object_store.ObjectStore | None:
    """The configured store; with an injected ``http`` (tests) a store over that transport, configured or not."""
    if http is None:
        return object_store.select()
    return object_store.select(call=lambda m, u, h, b: (http(m, u, h, b), {}, b""), allow_unconfigured=True)


def upload(files: dict[str, bytes], *, http: Http | None = None, manifest: Path | None = None,
           cache_control: str = "max-age=3600", workers: int = 1, force: bool = False) -> dict[str, Any]:
    """Upload ``{site path: bytes}`` (``cache_control`` is the objects' CDN/browser cache header; the live snapshots
    pass a short one; ``workers`` > 1 sends that many requests at once, for the live tiles; ``force`` ignores and leaves untouched the local hash
    manifest, for callers that decide "changed" themselves, as the document store does from its own hash manifest). Returns ``{"assets": n_uploaded,
    "skipped": n, "failed": [paths], "ok": bool}`` (``ok`` False only when a configured upload failed). Never raises."""
    if not files:
        return {"assets": 0, "skipped": 0, "failed": [], "ok": True}
    store = _store_for(http)
    if store is None:
        return {"assets": 0, "skipped": 0, "failed": [], "ok": True,
                "note": "asset upload off (no object store configured: set the R2_* names, docs/credentials.md)"}
    try:
        mpath = manifest or _manifest_path()
        seen = {} if force else _load(mpath)

        def one(site_path: str) -> tuple[str, str]:
            data = files[site_path]
            key = object_key(site_path)
            digest = hashlib.sha256(data).hexdigest()
            mkey = f"{store.ident}|{key}"          # per backend: switching stores re-sends everything once
            if seen.get(mkey) == digest:
                return "skipped", site_path
            status = store.put(key, data, content_type=content_type(key), cache_control=cache_control)
            if 200 <= status < 300:
                seen[mkey] = digest
                return "uploaded", site_path
            return "failed", f"{site_path} ({status})"

        paths = sorted(files)
        if workers > 1:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(one, paths))
        else:
            results = [one(p) for p in paths]
        if hasattr(store, "meter"):
            store.meter().flush()            # the usage counter reaches disk at the end of every batch (object_budget.py)
        uploaded = sum(r == "uploaded" for r, _ in results)
        skipped = sum(r == "skipped" for r, _ in results)
        failed = [what for r, what in results if r == "failed"]
        if not force:
            try:
                mpath.parent.mkdir(parents=True, exist_ok=True)
                mpath.write_text(json.dumps(seen, indent=1, sort_keys=True), encoding="utf-8")
            except OSError:
                pass   # the manifest is an optimisation: losing it only costs re-uploads
        return {"assets": uploaded, "skipped": skipped, "failed": failed, "ok": not failed}
    except Exception as exc:  # noqa: BLE001 - the article is the product; assets must never sink a run
        return {"assets": 0, "skipped": 0, "failed": [f"{type(exc).__name__}: {str(exc)[:120]}"], "ok": False}


def backfill(site_dir: Path, *, http: Http | None = None, manifest: Path | None = None) -> dict[str, Any]:
    """One-off: upload every file under the site's ``public/analytics`` (the published article images)."""
    root = Path(site_dir) / "public"
    files = {"/" + p.relative_to(root).as_posix(): p.read_bytes()
             for p in sorted((root / "analytics").rglob("*")) if p.is_file()}
    return upload(files, http=http, manifest=manifest)


if __name__ == "__main__":   # python -m algent_backend.publishing.asset_store <site dir>
    import sys

    print(json.dumps(backfill(sys.argv[1]), indent=2))
