"""
Published assets in Supabase Storage — the public bucket ``published-assets`` (migration 006).

Article hero/figure/chart images upload here on publish, so an article's images no longer ship by git commit
(docs/architecture/published-content.md). The object key is the site path without its leading slash:
``/analytics/<slug>/<name>`` -> ``analytics/<slug>/<name>``; the site resolves it to
``<SUPABASE_URL>/storage/v1/object/public/published-assets/<key>``.

Contract (same as ``published_db``): never raises into a run; idempotent (an object whose content hash matches the
last upload is skipped); a no-op without ``SUPABASE_URL`` + ``SUPABASE_SERVICE_ROLE_KEY`` or with
``ALGENT_DB_PUBLISH=0``. Environment only (``.env`` is not loaded), so a dev test run cannot reach the live project.
The service-role key is SERVER-ONLY: it is never on the site (docs/credentials.md).
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

BUCKET = "published-assets"
_OFF = ("0", "false", "no", "off")
_MIME = {".svg": "image/svg+xml", ".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg",
         ".jpeg": "image/jpeg", ".gif": "image/gif", ".json": "application/json"}

#: ``http(method, url, headers, body) -> status`` — injectable so tests need no network.
Http = Callable[[str, str, dict[str, str], bytes], int]


def _base() -> str:
    return os.environ.get("SUPABASE_URL", "").strip().rstrip("/")


def enabled() -> bool:
    return bool(_base() and os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()) \
        and os.environ.get("ALGENT_DB_PUBLISH", "1").strip().lower() not in _OFF


def object_key(site_path: str) -> str:
    """``/analytics/<slug>/x.svg`` -> ``analytics/<slug>/x.svg`` (the bucket key)."""
    return site_path.lstrip("/")


def public_url(site_path: str, base: str | None = None) -> str:
    """The URL the site serves an asset from once it is in the bucket."""
    return f"{(base if base is not None else _base())}/storage/v1/object/public/{BUCKET}/{object_key(site_path)}"


def content_type(key: str) -> str:
    return _MIME.get(Path(key).suffix.lower()) or mimetypes.guess_type(key)[0] or "application/octet-stream"


def _http(method: str, url: str, headers: dict[str, str], body: bytes) -> int:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:   # noqa: S310 — https URL from our own env
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def _manifest_path() -> Path:
    """Where the per-object content hashes live: server-local state, gitignored, never in the site checkout."""
    from .site_git import repo_root

    return repo_root() / "backend" / "publish_held" / "asset_hashes.json"


def _load(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def upload(files: dict[str, bytes], *, http: Http | None = None, manifest: Path | None = None) -> dict[str, Any]:
    """Upload ``{site path: bytes}``. Returns ``{"assets": n_uploaded, "skipped": n, "failed": [paths], "ok": bool}``
    (``ok`` False only when a configured upload failed). Never raises."""
    if not files:
        return {"assets": 0, "skipped": 0, "failed": [], "ok": True}
    if http is None and not enabled():
        return {"assets": 0, "skipped": 0, "failed": [], "ok": True,
                "note": "asset upload off (no SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY)"}
    try:
        mpath = manifest or _manifest_path()
        seen = _load(mpath)
        key_env = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        send = http or _http
        uploaded, skipped, failed = 0, 0, []
        for site_path, data in sorted(files.items()):
            key = object_key(site_path)
            digest = hashlib.sha256(data).hexdigest()
            if seen.get(key) == digest:
                skipped += 1
                continue
            headers = {"Authorization": f"Bearer {key_env}", "apikey": key_env, "x-upsert": "true",
                       "Content-Type": content_type(key), "Cache-Control": "max-age=3600"}
            status = send("POST", f"{_base()}/storage/v1/object/{BUCKET}/{key}", headers, data)
            if 200 <= status < 300:
                seen[key] = digest
                uploaded += 1
            else:
                failed.append(f"{site_path} ({status})")
        try:
            mpath.parent.mkdir(parents=True, exist_ok=True)
            mpath.write_text(json.dumps(seen, indent=1, sort_keys=True), encoding="utf-8")
        except OSError:
            pass   # the manifest is an optimisation: losing it only costs re-uploads
        return {"assets": uploaded, "skipped": skipped, "failed": failed, "ok": not failed}
    except Exception as exc:  # noqa: BLE001 — the article is the product; assets must never sink a run
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
