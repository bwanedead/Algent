"""
Orphaned objects: published once, no longer produced by anything (``newsroom publish prune-orphans``; docs/architecture/published-content.md).

The first views build published ~36,700 place views (``views/entity/place/*``) for geoledger assets that have no events; the builder no longer makes them and no
reader asks for them, but they still sit in the bucket (storage, and a mess for anyone listing it). Nothing in the normal path deletes an object, because the writer
never lists the bucket: it keeps a LOCAL hash manifest (``object_docs.manifest_path``) of what it sent. This module compares that record with what the CURRENT build owns:

    orphans = (documents the manifest says were published under a prefix) - (documents the current build produces)

The "current build owns" side comes from an *owner*, registered per prefix (``OWNERS``); only prefixes with an owner can be pruned, so the command cannot delete a family
nobody can enumerate. Owners today: ``views/`` (the keys of the last COMPLETE views build, ``views_store/_state.json``). An owner that cannot say what is current (no
build yet, an empty store) makes the run refuse rather than treat everything as orphaned.

Never deleted: anything the current build owns, anything the product registry has no contract for (an object we cannot name is not ours to remove), anything outside the
prefix. The bucket is not listed unless ``--list`` is given (one bounded LIST pass over the prefix, for a manifest that was lost); deletes are Class A, go through the R2
guard (a refusal stops the run), and are capped per run (``flags.ORPHAN_PRUNE_MAX_PER_RUN``) so a large backlog is spread over days by the daily ``orphan-prune`` job.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from algent_backend.database import flags

from . import doc_store, object_docs, object_store

#: Consecutive refused/failed deletes after which the run stops (the guard said no, or the bucket is unwell): the rest waits for the next run.
STOP_AFTER_FAILURES = 5


def _views_owned() -> set[str] | None:
    """Document paths (``views/<key>.json``) of the last complete views build, or None when there is none to compare against."""
    from algent_backend.publishing import staging
    from algent_backend.views import publish as views_publish

    try:
        state = json.loads((views_publish.store_dir(staging.PRODUCTION) / views_publish.STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return set(state) if isinstance(state, dict) and state else None


#: prefix -> () -> the document paths the current build produces under it (None: unknown, so nothing may be pruned).
OWNERS: dict[str, Callable[[], set[str] | None]] = {"views/": _views_owned}


def log_path() -> Path:
    return object_store.held_dir() / "orphan_prune.jsonl"


def published(prefix: str, store: Any | None, *, list_bucket: bool = False) -> set[str]:
    """Document paths under ``prefix`` known to have been published: the local manifest (for ``store``'s ident, or any when there is no store), plus one
    bounded LIST pass over ``docs/<prefix>`` when ``list_bucket``."""
    state = object_docs._load(object_docs.manifest_path())  # noqa: SLF001 - same package
    ident = store.ident if store is not None else None
    out = {k.split("|", 1)[1] for k in state if "|" in k and (ident is None or k.startswith(ident + "|"))}
    out = {p for p in out if p.startswith(prefix) and p.endswith(".json")}
    if list_bucket and store is not None:
        for obj in store.list(doc_store.PREFIX + prefix):
            key = str(obj["key"])
            if key.endswith(".json.gz"):
                out.add(key[len(doc_store.PREFIX): -len(".gz")])
    return out


def _ours(path: str) -> bool:
    """An object the registry can name: it matches a declared contract (so it is a document family we publish, just not a current one)."""
    from algent_backend import contracts

    return contracts.find(path) is not None


def plan(prefix: str, store: Any | None, *, list_bucket: bool = False) -> dict[str, Any]:
    owner = OWNERS.get(prefix)
    if owner is None:
        return {"ok": False, "note": f"no owner is registered for {prefix!r} (known: {', '.join(sorted(OWNERS))}); a prefix whose current contents nobody can list is not pruned"}
    owned = owner()
    if not owned:
        return {"ok": False, "note": f"no current build to compare against under {prefix!r} (run the build first); refusing to treat everything as orphaned"}
    known = published(prefix, store, list_bucket=list_bucket)
    orphans = sorted(p for p in known - owned if _ours(p))
    return {"ok": True, "prefix": prefix, "owned": len(owned), "published": len(known), "orphans": orphans, "unrecognised": len(known - owned) - len(orphans)}


def prune(prefix: str = "views/", *, dry_run: bool = False, list_bucket: bool = False, limit: int | None = None, store: Any | None = None,
          now: datetime | None = None) -> dict[str, Any]:
    """Delete up to ``limit`` orphans under ``prefix`` (default ``flags.ORPHAN_PRUNE_MAX_PER_RUN``) and forget them in the manifest. Never raises."""
    limit = flags.ORPHAN_PRUNE_MAX_PER_RUN if limit is None else limit
    try:
        store = store if store is not None else object_store.select()
        if store is None and (list_bucket or not dry_run):
            return {"ok": False, "note": "no object store configured (R2_* names)"}
        p = plan(prefix, store, list_bucket=list_bucket)
        if not p["ok"]:
            return p
        orphans: list[str] = p.pop("orphans")
        batch = orphans[:limit]
        out = {**p, "orphans": len(orphans), "this_run": len(batch), "remaining_after": len(orphans) - len(batch), "dry_run": dry_run, "deleted": 0, "failed": 0,
               "sample": batch[:5]}
        if dry_run or not batch:
            return out
        gone, failed_in_a_row = [], 0
        for path in batch:
            if store.delete(doc_store.object_key(path)):
                gone.append(path)
                failed_in_a_row = 0
            else:
                out["failed"] += 1
                failed_in_a_row += 1
                if failed_in_a_row >= STOP_AFTER_FAILURES:
                    out["note"] = f"stopped after {STOP_AFTER_FAILURES} refused deletes in a row (the R2 guard or the bucket); the rest waits for the next run"
                    break
        out["deleted"] = len(gone)
        out["remaining_after"] = len(orphans) - len(gone)
        _forget(store.ident, gone)
        if hasattr(store, "meter"):
            store.meter().flush()
        _log({**{k: out[k] for k in ("prefix", "orphans", "deleted", "failed", "remaining_after", "sample")}, "at": (now or datetime.now(UTC)).isoformat(timespec="seconds")})
        out["ok"] = out["failed"] == 0
        return out
    except Exception as exc:  # noqa: BLE001 - housekeeping must not crash the job runner
        return {"ok": False, "note": f"{type(exc).__name__}: {str(exc)[:160]}"}


def _forget(ident: str, paths: list[str]) -> None:
    """Drop deleted documents from the hash manifest, so a later publish of the same path (should it ever return) is not skipped as unchanged."""
    if not paths:
        return
    with object_docs._LOCK:  # noqa: SLF001
        mpath = object_docs.manifest_path()
        state = object_docs._load(mpath)  # noqa: SLF001
        for p in paths:
            state.pop(f"{ident}|{p}", None)
        object_docs._save(mpath, state)  # noqa: SLF001


def _log(row: dict[str, Any]) -> None:
    try:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        pass
    print(f"[orphans] {row['prefix']}: deleted {row['deleted']} of {row['orphans']} orphans, {row['remaining_after']} remain", flush=True)
