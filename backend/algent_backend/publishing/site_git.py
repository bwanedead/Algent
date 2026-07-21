"""
The deployment mechanism — commit auto-published articles to the ``site-live`` branch and push.

Vercel deploys production from ``origin/site-live``, so "publish" == a commit on that branch.
**Live publish is ON by default** — every finished eligible article commits + pushes. To pause
shipping without changing code, set ``ALGENT_SITE_PUBLISH=0`` (stage only into the working tree).

To avoid disrupting the operator's working tree, live commits happen in a dedicated git WORKTREE
checked out to ``site-live`` (``.site-live/`` at the repo root, gitignored). ``publish_run`` writes
the content/assets/ledger into that worktree; this module commits + pushes it.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

DEPLOY_BRANCH = "site-live"
_WORKTREE_DIRNAME = ".site-live"
_SITE_SUBPATH = ("sites", "ohmega-monster")
_PUBLISH_ENV = "ALGENT_SITE_PUBLISH"


def publish_enabled() -> bool:
    """Live push ON by default. Only ``0`` / ``false`` / ``no`` / ``off`` pauses to stage-only."""
    return os.environ.get(_PUBLISH_ENV, "1").strip().lower() not in ("0", "false", "no", "off")


def _git(cwd: Path, *args: str) -> tuple[bool, str]:
    try:
        proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=120)
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)[:200]
    return proc.returncode == 0, (proc.stdout or proc.stderr or "").strip()


def repo_root(start: Path | None = None) -> Path:
    ok, out = _git(start or Path.cwd(), "rev-parse", "--show-toplevel")
    return Path(out) if ok and out else (start or Path.cwd())


def site_dir(root: Path) -> Path:
    return root.joinpath(*_SITE_SUBPATH)


def live_site_dir(root: Path) -> Path:
    """The site path inside the ``site-live`` worktree — where a live publish writes."""
    return (root / _WORKTREE_DIRNAME).joinpath(*_SITE_SUBPATH)


def ensure_worktree(root: Path) -> tuple[Path | None, str]:
    """Ensure a ``.site-live`` worktree on ``site-live``, pulled to latest. (path, note) — path None on failure."""
    wt = root / _WORKTREE_DIRNAME
    if wt.exists():
        ok, out = _git(wt, "pull", "--ff-only", "origin", DEPLOY_BRANCH)
        return wt, ("worktree updated" if ok else f"pull warning: {out}")
    _git(root, "fetch", "origin", DEPLOY_BRANCH)
    ok, out = _git(root, "worktree", "add", str(wt), DEPLOY_BRANCH)
    if not ok:  # branch may not exist yet — create once and push (see publish README)
        return None, (f"could not add site-live worktree ({out}); create the '{DEPLOY_BRANCH}' branch "
                      "and push it once (see the publish README); or set ALGENT_SITE_PUBLISH=0 to stage only")
    return wt, "worktree created"


def commit_and_push(worktree: Path, message: str) -> tuple[bool, str]:
    """Stage everything in the worktree, commit with ``message``, and push to ``origin/site-live``."""
    _git(worktree, "add", "-A")
    ok, out = _git(worktree, "commit", "-m", message)
    if not ok and "nothing to commit" in out:
        return True, "nothing to commit (already live)"
    if not ok:
        return False, f"commit failed: {out}"
    ok, out = _git(worktree, "push", "origin", DEPLOY_BRANCH)
    return ok, ("pushed to site-live" if ok else f"push failed: {out}")


def site_code_drift(root: Path) -> str | None:
    """Warn when the current branch's site CODE (not content) is ahead of ``site-live`` — nobody is
    watching in full-auto, so a CSS/app fix on dev would otherwise silently never ship."""
    # TWO-dot: the actual tree difference between the branches. NOT three-dot (`A...HEAD`), which
    # diffs from the MERGE BASE and so re-reports every file this branch touched since it forked —
    # even ones site-live already has by an equivalent commit. The branches legitimately carry
    # cherry-picked twins of the same work, so three-dot cried wolf on 8 files when 1 had drifted.
    ok, out = _git(root, "diff", "--name-only", DEPLOY_BRANCH, "HEAD", "--",
                   "/".join(_SITE_SUBPATH))
    if not ok:
        return None
    code = [f for f in out.splitlines()
            if "/content/articles/" not in f and "/public/analytics/" not in f
            and "publish-ledger.md" not in f]
    if code:
        shown = ", ".join(code[:4]) + (" …" if len(code) > 4 else "")
        return f"site-live is behind this branch on site code ({shown}); merge into {DEPLOY_BRANCH} to ship it"
    return None
