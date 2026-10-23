"""
Off-site backup of the newsroom's durable data — research profiles and the Pulse ledger.

The stores are append-only JSON on this machine (``backend/profile_store``, ``backend/pulse_store``)
and were never backed up: one dead disk would have taken every profile, claim and Pulse history.
This mirrors them into a separate PRIVATE repo (``bwanedead/algent-data``) checked out at
``<repo>/.algent-data/`` — ignored by the code repo, the same pattern as ``.site-live``. The
operator never handles it; runs call ``backup()`` when they finish.

Rules:
- MIRROR ADDS AND UPDATES, NEVER DELETES. The stores are append-only, so a file missing locally is
  an accident, and an accident must not propagate into the only other copy.
- Never raises. A backup that fails leaves the run's result untouched and says why.
- Off in tests (``ALGENT_DATA_BACKUP=0``, set by conftest) — a test must never push data.
Files over ``flags.MIRROR_MAX_FILE_BYTES`` are not mirrored: the R2 snapshot (``snapshot.py``) is the primary copy and covers them. What is
irreplaceable is decided once, in the product registry (``ops/products``); ``_sources()`` reads it and so does the snapshot.
Restore on a new machine: clone the repo and copy its folders back (``restore()``), or ``newsroom backup restore`` from the latest snapshot.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

REPO_URL = "https://github.com/bwanedead/algent-data.git"
BRANCH = "main"
DIRNAME = ".algent-data"
_ENV = "ALGENT_DATA_BACKUP"


def enabled() -> bool:
    return os.environ.get(_ENV, "1").strip().lower() not in ("0", "false", "no", "off")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]          # …/Algent


def _sources() -> dict[str, Path]:
    """What is backed up, by the folder name it gets in the data repo: every backed-up store of an irreplaceable product in the product registry
    (``ops/products/registry.py``) - the single list, read by the mirror, the R2 snapshot, the restore and the coverage test."""
    from algent_backend.ops.products import views

    return views.backup_sources()


def _git(cwd: Path, *args: str) -> tuple[bool, str]:
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return done.returncode == 0, (done.stdout + done.stderr).strip()


def _checkout() -> tuple[Path | None, str]:
    """The data repo's working copy, cloned on first use and fast-forwarded after."""
    wt = _repo_root() / DIRNAME
    if (wt / ".git").is_dir():
        ok, out = _git(wt, "pull", "--ff-only", "origin", BRANCH)
        # An empty remote has no branch to pull yet — that is the first backup, not an error.
        return wt, "updated" if ok or "couldn't find remote ref" in out else f"pull warning: {out[:120]}"
    ok, out = _git(_repo_root(), "clone", REPO_URL, DIRNAME)
    if not ok:
        return None, f"clone failed: {out[:160]}"
    _git(wt, "checkout", "-B", BRANCH)
    return wt, "cloned"


def _same_bytes(a: Path, b: Path) -> bool:
    """True when two files hold the same bytes. Deliberately not ``filecmp.cmp``: that caches its verdict by (size, mtime) signature, so a same-size
    rewrite inside one filesystem timestamp tick (and ``copy2`` gives the mirror the source's mtime) is answered from the cache as "unchanged" - a
    missed backup, and the cause of ``test_mirror_adds_and_updates_but_never_deletes`` failing now and then."""
    if a.stat().st_size != b.stat().st_size:
        return False
    with a.open("rb") as fa, b.open("rb") as fb:
        while True:
            ca, cb = fa.read(1 << 20), fb.read(1 << 20)
            if ca != cb:
                return False
            if not ca:
                return True


def mirror(sources: dict[str, Path], dest: Path, skipped: list[str] | None = None) -> int:
    """Copy new and changed files from each source into ``dest/<name>/``. Returns files copied. A file over ``flags.MIRROR_MAX_FILE_BYTES`` is
    not mirrored (it is in the R2 snapshot, ``snapshot.py``); its path is appended to ``skipped`` when given."""
    from algent_backend.data_backup import flags

    copied = 0
    for name, src in sources.items():
        if not src.is_dir():
            continue
        for path in src.rglob("*"):
            if not path.is_file() or path.suffix == ".tmp":
                continue
            target = dest / name / path.relative_to(src)
            if path.stat().st_size > flags.MIRROR_MAX_FILE_BYTES:
                if skipped is not None:
                    skipped.append(f"{name}/{path.relative_to(src).as_posix()}")
                continue
            if target.exists() and _same_bytes(path, target):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            copied += 1
    return copied


def backup(note: str = "") -> dict:
    """Mirror the stores and push. Never raises."""
    if not enabled():
        return {"backed_up": False, "note": "disabled"}
    try:
        wt, how = _checkout()
        if wt is None:
            return {"backed_up": False, "note": how}
        too_big: list[str] = []
        copied = mirror(_sources(), wt, too_big)
        extra = {"too_big_for_git": too_big} if too_big else {}
        if not copied:
            return {"backed_up": True, "copied": 0, "note": "already current", **extra}
        _git(wt, "add", "-A")
        ok, out = _git(wt, "commit", "-m", f"backup: {copied} file(s){' — ' + note if note else ''}")
        if not ok and "nothing to commit" not in out:
            return {"backed_up": False, "note": f"commit failed: {out[:160]}"}
        ok, out = _git(wt, "push", "-u", "origin", BRANCH)
        return {"backed_up": ok, "copied": copied, "note": "pushed" if ok else f"push failed: {out[:160]}", **extra}
    except Exception as exc:  # noqa: BLE001 — a failed backup must never fail the run
        return {"backed_up": False, "note": f"{type(exc).__name__}: {str(exc)[:160]}"}


def restore() -> dict:
    """New machine: copy the backed-up stores into place. Only fills in; never overwrites newer."""
    wt, how = _checkout()
    if wt is None:
        return {"restored": False, "note": how}
    restored = 0
    for name, dest in _sources().items():
        src = wt / name
        if not src.is_dir():
            continue
        for path in src.rglob("*"):
            target = dest / path.relative_to(src)
            if path.is_file() and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                restored += 1
    return {"restored": True, "files": restored}
