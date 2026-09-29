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
Restore on a new machine: clone the repo and copy its folders back (``restore()``).
"""

from __future__ import annotations

import filecmp
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
    """What is backed up, by the folder name it gets in the data repo."""
    from algent_backend.agent_system.agents.pulse import PulseStore
    from algent_backend.agent_system.agents.research.store import JsonProfileStore

    backend = _repo_root() / "backend"

    def resolve(p: Path) -> Path:
        return p if p.is_absolute() else backend / p

    return {"profile_store": resolve(JsonProfileStore().root),
            "pulse_store": resolve(PulseStore().root)}


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


def mirror(sources: dict[str, Path], dest: Path) -> int:
    """Copy new and changed files from each source into ``dest/<name>/``. Returns files copied."""
    copied = 0
    for name, src in sources.items():
        if not src.is_dir():
            continue
        for path in src.rglob("*"):
            if not path.is_file() or path.suffix == ".tmp":
                continue
            target = dest / name / path.relative_to(src)
            if target.exists() and filecmp.cmp(path, target, shallow=False):
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
        copied = mirror(_sources(), wt)
        if not copied:
            return {"backed_up": True, "copied": 0, "note": "already current"}
        _git(wt, "add", "-A")
        ok, out = _git(wt, "commit", "-m", f"backup: {copied} file(s){' — ' + note if note else ''}")
        if not ok and "nothing to commit" not in out:
            return {"backed_up": False, "note": f"commit failed: {out[:160]}"}
        ok, out = _git(wt, "push", "-u", "origin", BRANCH)
        return {"backed_up": ok, "copied": copied, "note": "pushed" if ok else f"push failed: {out[:160]}"}
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
