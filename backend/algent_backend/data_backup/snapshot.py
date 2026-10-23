"""
Nightly off-box snapshot: one compressed tar of every irreplaceable store, in the private R2 backup bucket.

    backups/daily/<YYYY-MM-DD>.tar.gz            the stores (``sync._sources()`` is the single list of what is irreplaceable), one folder each
    backups/daily/<YYYY-MM-DD>.manifest.json.gz  per store: file count, bytes and the sha256 of every file, plus the archive's own sha256

Why this and not git: the old backup was a git repo of rewritten JSON (history grows forever, files approach the 100 MB wall, never restored from).
A snapshot is one object, restored by one download, and verified against its manifest. The git mirror stays only as a second, human-diffable
path for small files (``sync.py``, ``flags.MIRROR_MAX_FILE_BYTES``).

The restore drill (``restore_drill``) downloads the latest snapshot into a temp dir and checks counts and hashes against the manifest; its
result goes to ``~/ops-log.md`` and ``backup_state.json`` (what ``newsroom envelope`` and the doctor read). Retention thins the daily prefix
to 14 daily + 8 weekly + 12 monthly (``plan_retention``); deletes are Class A operations and go through the same R2 budget meter.

Never raises into a job: every entry point returns a dict with ``ok`` and a ``note``.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import re
import shutil
import tarfile
import tempfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from algent_backend.data_backup import flags, sync
from algent_backend.ops import opslog

SCHEMA = "ohmega.backup/1"
_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.tar\.gz$")


def _key(day: str, suffix: str = "tar.gz") -> str:
    return f"{flags.PREFIX}{day}.{suffix}"


# ── state (what the envelope reads) ──────────────────────────────────────────────────────────────
def state_path() -> Path:
    from algent_backend.publishing.object_store import held_dir

    return held_dir() / "backup_state.json"


def read_state() -> dict[str, Any]:
    try:
        doc = json.loads(state_path().read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


def _remember(**part: Any) -> None:
    doc = read_state()
    doc.update(part)
    path = state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, indent=1), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


# ── build ────────────────────────────────────────────────────────────────────────────────────────
def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_archive(sources: dict[str, Path], out: Path, *, day: str, now: datetime) -> dict[str, Any]:
    """Write the tar.gz and return its manifest. Each file is read once, hashed and added from the same bytes, so a store being written to
    during the pass cannot make the hash disagree with what is in the archive."""
    stores: dict[str, Any] = {}
    with tarfile.open(out, "w:gz", compresslevel=6) as tar:
        for name in sorted(sources):
            root = sources[name]
            if not root.is_dir():
                continue
            files: dict[str, list] = {}
            for path in sorted(p for p in root.rglob("*") if p.is_file() and p.suffix != ".tmp"):
                try:
                    data, mtime = path.read_bytes(), path.stat().st_mtime
                except OSError:
                    continue                                   # vanished between listing and reading
                rel = path.relative_to(root).as_posix()
                info = tarfile.TarInfo(f"{name}/{rel}")
                info.size, info.mtime, info.mode = len(data), mtime, 0o644
                tar.addfile(info, io.BytesIO(data))
                files[rel] = [len(data), _sha(data)]
            if files:
                stores[name] = {"files": len(files), "bytes": sum(v[0] for v in files.values()), "sha": files}
    h = hashlib.sha256()
    with out.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return {"schema": SCHEMA, "date": day, "created": now.isoformat(timespec="seconds"),
            "archive": {"bytes": out.stat().st_size, "sha256": h.hexdigest()}, "stores": stores}


def _brief(manifest: dict[str, Any]) -> dict[str, Any]:
    stores = manifest.get("stores", {})
    return {"stores": len(stores), "files": sum(s["files"] for s in stores.values()), "raw_bytes": sum(s["bytes"] for s in stores.values()),
            "archive_bytes": manifest.get("archive", {}).get("bytes", 0), "by_store": {n: {"files": s["files"], "bytes": s["bytes"]} for n, s in stores.items()}}


# ── retention ────────────────────────────────────────────────────────────────────────────────────
def plan_retention(days: list[str], *, daily: int = flags.KEEP_DAILY, weekly: int = flags.KEEP_WEEKLY, monthly: int = flags.KEEP_MONTHLY) -> set[str]:
    """Which snapshot dates to keep: the newest ``daily``, the newest of each of the last ``weekly`` ISO weeks and ``monthly`` months."""
    ordered = sorted(set(days), reverse=True)
    keep = set(ordered[:daily])
    for period, n in ((lambda d: date.fromisoformat(d).isocalendar()[:2], weekly), (lambda d: d[:7], monthly)):
        seen: dict[Any, str] = {}
        for d in ordered:                                      # newest first: the first seen in a period is its newest
            seen.setdefault(period(d), d)
        keep |= set(list(seen.values())[:n])                   # insertion order is newest period first
    return keep


def listing(store: Any) -> list[str]:
    """Snapshot dates in the backup bucket, oldest first."""
    days = []
    for obj in store.list(flags.PREFIX):
        m = _DATE.match(obj["key"][len(flags.PREFIX):])
        if m:
            days.append(m.group(1))
    return sorted(days)


def prune(store: Any, *, apply: bool) -> dict[str, Any]:
    days = listing(store)
    keep = plan_retention(days)
    drop = [d for d in days if d not in keep]
    deleted = 0
    if apply:
        for d in drop:
            ok = store.delete(_key(d))
            store.delete(_key(d, "manifest.json.gz"))
            deleted += bool(ok)
    return {"snapshots": len(days), "keep": len(keep), "drop": drop, "deleted": deleted}


# ── snapshot ─────────────────────────────────────────────────────────────────────────────────────
def snapshot(store: Any, *, now: datetime | None = None, dry_run: bool = False, sources: dict[str, Path] | None = None) -> dict[str, Any]:
    """Build today's snapshot and (unless ``dry_run``) upload it, then thin the old ones. Never raises."""
    now = now or datetime.now(UTC)
    day = now.date().isoformat()
    tmp = Path(tempfile.mkdtemp(prefix="ohmega-snap-"))
    try:
        out = tmp / f"{day}.tar.gz"
        manifest = build_archive(sources if sources is not None else sync._sources(), out, day=day, now=now)
        res: dict[str, Any] = {"ok": True, "date": day, **_brief(manifest)}
        if dry_run:
            return {**res, "note": "dry run: nothing uploaded"}
        if store is None:
            return {**res, "ok": False, "note": "no backup bucket: set R2_BACKUP_BUCKET (a PRIVATE bucket) next to the R2 keys"}
        body = out.read_bytes()
        status = store.put(_key(day), body, content_type="application/gzip", cache_control="no-store")
        if status not in (200, 201):
            return {**res, "ok": False, "note": f"upload refused or failed (HTTP {status})"}
        store.put(_key(day, "manifest.json.gz"), gzip.compress(json.dumps(manifest, separators=(",", ":")).encode("utf-8"), mtime=0),
                  content_type="application/gzip", cache_control="no-store")
        pruned = prune(store, apply=True)
        res.update(note=f"uploaded {len(body)} bytes", pruned=len(pruned["drop"]))
        _remember(last_snapshot={"at": now.isoformat(timespec="seconds"), "date": day, "ok": True, **_brief(manifest)})
        opslog.append("backup", f"snapshot {day} ok: {res['files']} files, {res['raw_bytes'] / 1e6:.0f} MB -> {len(body) / 1e6:.1f} MB; "
                                f"{pruned['keep']} kept, {len(pruned['drop'])} thinned", now=now)
        return res
    except Exception as exc:  # noqa: BLE001 - a backup failure is reported, never raised into the timer
        _remember(last_snapshot_failure={"at": now.isoformat(timespec="seconds"), "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
        opslog.append("backup", f"snapshot {day} FAILED: {type(exc).__name__}: {str(exc)[:120]}", now=now)
        return {"ok": False, "date": day, "note": f"{type(exc).__name__}: {str(exc)[:160]}"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ── restore and the drill ────────────────────────────────────────────────────────────────────────
def _safe(name: str) -> bool:
    p = Path(name)
    return not p.is_absolute() and ".." not in p.parts and bool(p.parts)


def _extract(archive: bytes, dest: Path) -> list[str]:
    """Unpack by hand: only regular files, only inside ``dest``. Returns problems."""
    problems: list[str] = []
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for m in tar:
            if not m.isfile() or not _safe(m.name):
                problems.append(f"skipped unsafe member {m.name!r}")
                continue
            target = dest / m.name
            target.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(m) as src, target.open("wb") as dst:       # type: ignore[union-attr]
                shutil.copyfileobj(src, dst)
    return problems


def verify(manifest: dict[str, Any], root: Path, archive: bytes | None = None) -> dict[str, Any]:
    """Counts and hashes of what is under ``root`` against the manifest."""
    problems: list[str] = []
    if archive is not None and _sha(archive) != manifest.get("archive", {}).get("sha256"):
        problems.append("archive sha256 differs from the manifest")
    files = bad = 0
    for name, st in manifest.get("stores", {}).items():
        have = sum(1 for p in (root / name).rglob("*") if p.is_file()) if (root / name).is_dir() else 0
        if have != st["files"]:
            problems.append(f"{name}: {have} files, manifest says {st['files']}")
        for rel, (size, sha) in st["sha"].items():
            files += 1
            f = root / name / rel
            if not f.is_file() or f.stat().st_size != size or _sha(f.read_bytes()) != sha:
                bad += 1
                if bad <= 5:
                    problems.append(f"{name}/{rel}: missing or different")
    if bad > 5:
        problems.append(f"... {bad} files differ in all")
    return {"ok": not problems, "files_checked": files, "problems": problems}


def _fetch(store: Any, day: str) -> tuple[bytes | None, dict[str, Any] | None]:
    archive, raw = store.get(_key(day)), store.get(_key(day, "manifest.json.gz"))
    manifest = json.loads(gzip.decompress(raw)) if raw else None
    return archive, manifest


def restore(store: Any, dest: Path, *, day: str | None = None) -> dict[str, Any]:
    """Download a snapshot (default: the latest), unpack it into ``dest`` (a new folder per store) and verify it. Never overwrites a store in place."""
    try:
        days = listing(store)
        if not days:
            return {"ok": False, "note": "no snapshots in the backup bucket"}
        day = day or days[-1]
        archive, manifest = _fetch(store, day)
        if archive is None or manifest is None:
            return {"ok": False, "date": day, "note": "archive or manifest missing"}
        dest.mkdir(parents=True, exist_ok=True)
        problems = _extract(archive, dest)
        res = verify(manifest, dest, archive)
        res["problems"] = problems + res["problems"]
        return {**res, "ok": res["ok"] and not problems, "date": day, "bytes": len(archive), "dest": str(dest)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "note": f"{type(exc).__name__}: {str(exc)[:160]}"}


def restore_drill(store: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """Restore the latest snapshot to a temp dir, verify, delete it, and record ok / fail (ops-log + state file)."""
    now = now or datetime.now(UTC)
    if store is None:
        res = {"ok": False, "note": "no backup bucket (R2_BACKUP_BUCKET unset)"}
    else:
        tmp = Path(tempfile.mkdtemp(prefix="ohmega-drill-"))
        try:
            res = restore(store, tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        res.pop("dest", None)
    _remember(last_drill={"at": now.isoformat(timespec="seconds"), "ok": bool(res.get("ok")), "snapshot": res.get("date"),
                          "files": res.get("files_checked"), "problems": res.get("problems", [])[:5], "note": res.get("note", "")})
    opslog.append("backup", f"restore-drill {'ok' if res.get('ok') else 'FAIL'}: snapshot {res.get('date')}, {res.get('files_checked', 0)} files verified"
                            + (f"; {'; '.join(res.get('problems', [])[:2]) or res.get('note', '')}" if not res.get("ok") else ""), now=now)
    return res


def age_hours(now: datetime | None = None) -> float | None:
    """Hours since the last good snapshot, or None when there has never been one."""
    at = (read_state().get("last_snapshot") or {}).get("at")
    if not at:
        return None
    return ((now or datetime.now(UTC)) - datetime.fromisoformat(at)).total_seconds() / 3600


def drill_age_days(now: datetime | None = None) -> float | None:
    at = (read_state().get("last_drill") or {}).get("at")
    return None if not at else ((now or datetime.now(UTC)) - datetime.fromisoformat(at)) / timedelta(days=1)
