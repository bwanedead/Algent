"""
Shared helpers for turning the server's local stores into the site's published documents (docs/architecture/published-content.md).

The site used to read PostgREST tables (``live_events``, ``maritime_events``, ``sanctions_events`` ...). It now reads **documents** in the
object store, built from the same local stores each domain already keeps (the system of record). Each domain package owns its builder
(``live/publish.py``, ``maritime/publish.py`` ...); this module holds only what they share:

* ``stamped``    - a stable per-row ``updated_at`` ("last changed", the semantic the table had) kept in a small local file, so a document
                   whose content did not change hashes the same and is never re-uploaded;
* ``publish``    - hand documents to the object store (``object_docs``) and, only while the legacy Postgres flag is on, also run the old
                   table writer (``also_postgres``).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import object_docs, object_store, published_db


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _signature(row: dict[str, Any]) -> str:
    body = {k: v for k, v in row.items() if k != "updated_at"}
    return hashlib.sha1(json.dumps(body, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:12]


def stamped(kind: str, rows: list[dict[str, Any]], *, now: str | None = None, key: str = "id", held: Path | None = None) -> list[dict[str, Any]]:
    """Give every row an ``updated_at`` = the first time its current content was seen. Rows that disappear are forgotten. The seen-map lives
    in ``publish_held/stamps_<kind>.json`` (server state): a lost file only re-stamps everything once."""
    path = (held or object_store.held_dir()) / f"stamps_{kind}.json"
    try:
        seen = json.loads(path.read_text(encoding="utf-8"))
        seen = seen if isinstance(seen, dict) else {}
    except (OSError, ValueError):
        seen = {}
    now = now or now_iso()
    out: dict[str, list[str]] = {}
    for r in rows:
        sig = _signature(r)
        prev = seen.get(str(r[key]))
        stamp = prev[1] if isinstance(prev, list) and len(prev) == 2 and prev[0] == sig else now
        out[str(r[key])] = [sig, stamp]
        r["updated_at"] = stamp
    if out != seen:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(out, sort_keys=True), encoding="utf-8")
        except OSError:
            pass
    return rows


def publish(docs: dict[str, Any], *, http: Any = None, force: bool = False) -> dict[str, Any]:
    """Documents to the object store through the one document path (``published_db.publish_documents`` honours the Postgres flag)."""
    return published_db.publish_documents(docs, http=http, force=force) if published_db.budget.postgres_publish() \
        else object_docs.publish(docs, http=http, force=force)


def publish_built(build: Callable[[], dict[str, Any]], *, http: Any = None, force: bool = False) -> dict[str, Any]:
    """``publish(build())``, but the (possibly heavy) builder runs only when an object store is configured, so an unconfigured machine
    (a dev box, a test) costs nothing and reads no store."""
    if http is None and not object_store.configured():
        return {"db": False, "ok": False, "note": "document storage off (no object store configured: set the R2_* names, docs/credentials.md)"}
    try:
        return publish(build(), http=http, force=force)
    except Exception as exc:  # noqa: BLE001 - the local stores are the record; publishing is an addition
        return {"db": False, "ok": False, "note": f"{type(exc).__name__}: {str(exc)[:160]}"}


def also_postgres(files_result: dict[str, Any], work: Callable[[Any], dict], connect: Callable[[], Any] | None) -> dict[str, Any]:
    """The legacy table write, run only when a connection is injected or the Postgres flag + DATABASE_URL are set. Its result wins (callers
    and tests read ``db`` / row counts from it) and carries the files result under ``files``."""
    if published_db.files_only(connect):
        return files_result
    result = published_db._run(work, connect)  # noqa: SLF001 - same package family, one connection contract
    if files_result.get("ok"):
        result["files"] = files_result
    return result
