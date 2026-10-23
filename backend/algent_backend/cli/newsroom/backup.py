"""
``newsroom backup`` - the off-box snapshot of the irreplaceable stores (data_backup/snapshot.py). Needs ``R2_BACKUP_BUCKET`` (a PRIVATE bucket).

    newsroom backup snapshot [--dry-run]       build today's tar.gz of every backed-up store, upload it, thin old ones (14 daily / 8 weekly / 12 monthly)
    newsroom backup status                     last snapshot, last restore drill, what is in the bucket (one LIST)
    newsroom backup prune [--apply]            show / apply the retention on its own
    newsroom backup restore-drill              restore the latest snapshot to a temp dir, verify counts + hashes, log ok / FAIL (monthly timer)
    newsroom backup restore --to DIR [--date]  unpack a snapshot into a NEW directory and verify it (never overwrites a store)

Prints one JSON document; exit 1 when the thing failed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def add_parser(sub: Any) -> None:
    p = sub.add_parser("backup", help="R2 snapshots of the irreplaceable stores: snapshot, status, prune, restore-drill, restore")
    verbs = p.add_subparsers(dest="backup_cmd", required=True)
    s = verbs.add_parser("snapshot", help="build and upload today's snapshot")
    s.add_argument("--dry-run", action="store_true", help="build it in a temp dir and report sizes; upload nothing (needs no bucket)")
    s.set_defaults(handler=run_snapshot)
    verbs.add_parser("status", help="last snapshot / drill and the bucket's listing").set_defaults(handler=run_status)
    pr = verbs.add_parser("prune", help="the 14/8/12 retention (dry run unless --apply)")
    pr.add_argument("--apply", action="store_true")
    pr.set_defaults(handler=run_prune)
    verbs.add_parser("restore-drill", help="restore the latest snapshot to a temp dir and verify it").set_defaults(handler=run_drill)
    r = verbs.add_parser("restore", help="unpack a snapshot into a new directory and verify it")
    r.add_argument("--to", required=True, help="a directory to unpack into (created; stores land as <dir>/<store_name>/)")
    r.add_argument("--date", default=None, help="YYYY-MM-DD (default: the latest)")
    r.set_defaults(handler=run_restore)


def _store() -> Any:
    from algent_backend.publishing import object_store

    return object_store.select_backup()


def _emit(doc: dict[str, Any]) -> int:
    print(json.dumps(doc, indent=2, ensure_ascii=False))
    return 0 if doc.get("ok", True) else 1


def run_snapshot(args: Any) -> int:
    from algent_backend.data_backup import snapshot

    return _emit(snapshot.snapshot(_store(), dry_run=args.dry_run))


def run_status(_args: Any) -> int:
    from algent_backend.data_backup import flags, snapshot

    store = _store()
    doc: dict[str, Any] = {"ok": True, "bucket_configured": store is not None, "state": snapshot.read_state(),
                           "snapshot_age_h": snapshot.age_hours(), "drill_age_days": snapshot.drill_age_days(),
                           "retention": {"daily": flags.KEEP_DAILY, "weekly": flags.KEEP_WEEKLY, "monthly": flags.KEEP_MONTHLY}}
    if store is not None:
        try:
            doc["snapshots"] = snapshot.listing(store)
        except Exception as exc:  # noqa: BLE001
            doc["list_error"] = f"{type(exc).__name__}: {str(exc)[:120]}"
    return _emit(doc)


def run_prune(args: Any) -> int:
    from algent_backend.data_backup import snapshot

    store = _store()
    return _emit({"ok": False, "note": "no backup bucket (R2_BACKUP_BUCKET unset)"} if store is None else {"ok": True, **snapshot.prune(store, apply=args.apply)})


def run_drill(_args: Any) -> int:
    from algent_backend.data_backup import snapshot

    return _emit(snapshot.restore_drill(_store()))


def run_restore(args: Any) -> int:
    from algent_backend.data_backup import snapshot

    store = _store()
    if store is None:
        return _emit({"ok": False, "note": "no backup bucket (R2_BACKUP_BUCKET unset)"})
    dest = Path(args.to)
    if dest.exists() and any(dest.iterdir()):
        return _emit({"ok": False, "note": f"{dest} is not empty; restore into a new directory and copy from there"})
    return _emit(snapshot.restore(store, dest, day=args.date))
