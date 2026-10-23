"""
Publishing views: local first, then the object store, and only what changed.

1. ``stamp``   an unchanged view keeps its ``built_at`` (the state file remembers each view's content hash and first-built time), so it is byte-identical to
                what is already published and ``object_docs.publish`` skips it by hash: no request at all.
2. ``store``   each view is written to the server store ``views_store/`` first (only when it changed), so the server holds everything it publishes, can serve
                ``newsroom views show``, and can be inspected without the bucket. Keys the build no longer produces are pruned from it.
3. ``send``    the changed views go to the bucket through the one document path (``publishing/object_docs``, ``docs/views/<key>.json.gz``), behind the R2 free-tier
                guard (``object_budget``): past a limit the call is refused, the view is not recorded as sent, and the next run retries it.

Class A cost is the number of changed views per run (see docs/architecture/views.md for the estimate against the guard); no name indexes are written.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from algent_backend.publishing import doc_store, object_docs

from . import flags
from .base import View

STORE_ENV = "ALGENT_VIEWS_STORE"
STATE_FILE = "_state.json"


def store_dir(target: str | None = None) -> Path:
    """The server's views store. A staging build (``ALGENT_PUBLISH_TARGET=staging``) has a sibling store of its own (``views_store_staging``), so it
    never rewrites the production store or its change-stamps; ``target`` names one explicitly (stage-from-prod reads the production one)."""
    from algent_backend.publishing import staging

    root = Path(os.environ.get(STORE_ENV) or "views_store")
    return root.with_name(root.name + "_staging") if (target or staging.target()) == staging.STAGING else root


def _canonical(body: dict[str, Any]) -> bytes:
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _content_hash(body: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical({k: v for k, v in body.items() if k != "built_at"})).hexdigest()


def _load_state(root: Path) -> dict[str, list[str]]:
    try:
        data = json.loads((root / STATE_FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def stamp(views: list[View], state: dict[str, list[str]], now: datetime | None = None) -> dict[str, list[str]]:
    """Set each view's ``built_at``: the previous one while the content is unchanged, else now. Returns the new state ``{path: [content hash, built_at]}``."""
    stamp_now = (now or datetime.now(UTC)).isoformat(timespec="seconds")
    new: dict[str, list[str]] = {}
    for v in views:
        h = _content_hash(v.body)
        prev = state.get(v.path)
        v.body["built_at"] = prev[1] if prev and prev[0] == h else stamp_now
        new[v.path] = [h, v.body["built_at"]]
    return new


def store(views: list[View], root: Path | None = None, *, prune: bool = True) -> dict[str, int]:
    """Write changed views to the server store; returns counts. ``prune`` removes files for keys not in ``views`` (only when the build was complete)."""
    root = root or store_dir()
    wrote = unchanged = 0
    for v in views:
        f = root / f"{v.key}.json"
        data = _canonical(v.body)
        if f.is_file() and f.read_bytes() == data:
            unchanged += 1
            continue
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, f)
        wrote += 1
    pruned = 0
    if prune and root.is_dir():
        keep = {f"{v.key}.json" for v in views}
        for f in list(root.rglob("*.json")):
            rel = f.relative_to(root).as_posix()
            if rel != STATE_FILE and rel not in keep:
                f.unlink()
                pruned += 1
        for d in sorted((p for p in root.rglob("*") if p.is_dir()), reverse=True):
            if not any(d.iterdir()):
                shutil.rmtree(d, ignore_errors=True)
    return {"wrote": wrote, "unchanged": unchanged, "pruned": pruned}


def publish(views: list[View], *, root: Path | None = None, http: Any = None, dry_run: bool = False, complete: bool = True, force: bool = False,
            now: datetime | None = None) -> dict[str, Any]:
    """Stamp, store locally and send what changed. ``complete`` says the views are a whole build (the local store is pruned to them); a partial build
    (``--only``) never prunes. ``dry_run`` builds and reports the upload without storing or sending anything."""
    root = root or store_dir()
    state = _load_state(root)
    new_state = {**state, **stamp(views, state, now)}
    docs = {v.path: v.body for v in views}
    if dry_run:
        return {"dry_run": True, **object_docs.dry_run_report(docs), "views": len(views), "bytes": sum(v.size() for v in views)}
    out = {"views": len(views), "bytes": sum(v.size() for v in views), "store": store(views, root, prune=complete)}
    if complete:
        new_state = {p: s for p, s in new_state.items() if p in docs}
    (root).mkdir(parents=True, exist_ok=True)
    (root / STATE_FILE).write_text(json.dumps(new_state, sort_keys=True), encoding="utf-8")
    out["upload"] = object_docs.publish(docs, http=http, force=force, names=False)
    return out


def estimate(views: list[View]) -> dict[str, int]:
    """What a full first upload costs: one Class A per view and the gzipped bytes (the steady state is the changed fraction of this)."""
    packed = [doc_store.pack(v.path, v.body) for v in views]
    return {"class_a": len(packed), "gz_bytes": sum(len(p.gz) for p in packed), "raw_bytes": sum(p.size_bytes for p in packed), "prefix": flags.PREFIX}
