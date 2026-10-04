"""
Escape guard for the analytics worker — attribution is about the WORKER, never the repo.

The worker is a coding-agent subprocess that may write anywhere its OS user can. The old guard
diffed the whole repo (``git status`` + every file in the pipeline's own stores) before vs after and
blamed the worker for every difference. But the repo is not quiet while a chart renders: a developer
edits ``sites/``, and the article pipeline itself writes ``draft_store/`` and ``profile_store/`` on
other threads. Every such write failed the chart ("worker wrote outside analytics_workspace/"), so
articles shipped with no visuals.

A before/after diff cannot tell WHO wrote a path, so this guard only judges surfaces where the
writer IS identifiable by construction, and treats the rest as observed-not-blamed:

1. LANE — ``analytics_workspace/`` outside scratch folders (lib/, scripts/, AGENTS.md ...). Nobody
   else writes there mid-run; any change is the worker's. Content-compared, and *reverted*
   from the pre-run bytes (new strays deleted, edited/removed files restored).
2. LANDING SIGNATURE — files carrying the worker's own output names (``chart.svg``, ``data.csv``,
   ``caption.md`` ...) newly appearing at the repo root, ``backend/`` or the workspace root: the
   classic ``..`` mistake. Only the worker names files that way, so they are its writes; deleted.
3. SECRETS — ``.env*`` created or touched. No other writer touches them mid-run.
4. STORES (profile/treatment/draft/lead) — written legitimately by our own pipeline concurrently, so
   "changed" proves nothing. What does betray a non-pipeline writer is damage: a pre-existing store
   file deleted, or a changed/new ``.json`` that no longer parses. Reported, never auto-deleted
   (a store file could be the pipeline's own in-flight write).

Everything else that changed in git during the window is returned as ``observed_churn`` — logged,
never blamed. Confinement at the source (codex's workspace-write sandbox rooted at the scratch
folder) is the preventive layer; this guard is the detective layer for the surfaces it can attribute.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

#: Stores the pipeline writes concurrently; damage (not change) is what indicts the worker.
GUARDED_STORE_DIRS = ("profile_store", "treatment_store", "draft_store", "lead_store")

_RESTORE_FILE_CAP = 1_000_000       # keep pre-run bytes only for small files (the helper stack)
_RESTORE_TOTAL_CAP = 20_000_000
# Workspace subtrees that are machine-local environment, not worker-reachable doctrine/stack.
_SKIP_DIRNAMES = {".venv", "__pycache__", "node_modules", ".git"}
_SKIP_REL_PREFIXES = ("data/natural_earth", "data/_smoke")
_SKIP_SUFFIXES = {".pyc"}
_PARSE_RETRY_S = 0.3                # a store write is not atomic; re-check an unparsable file once

Stamp = tuple[int, int]             # (mtime_ns, size)


@dataclass
class LaneBaseline:
    """Pre-run state of the surfaces the guard can attribute. Built by :func:`snapshot`."""

    stack: dict[str, tuple[Stamp, bytes | None]] = field(default_factory=dict)
    landing: dict[Path, set[str]] = field(default_factory=dict)
    env: dict[str, Stamp] = field(default_factory=dict)
    stores: dict[str, Stamp] = field(default_factory=dict)
    git_dirty: set[str] | None = None


@dataclass
class GuardVerdict:
    """What :func:`check` found. ``escaped`` is the worker's (fail the chart); the rest is not."""

    escaped: list[str] = field(default_factory=list)       # attributable to the worker
    reverted: list[str] = field(default_factory=list)      # worker writes undone (subset of escaped)
    observed_churn: list[str] = field(default_factory=list)  # changed in git, NOT attributable


def _stamp(p: Path) -> Stamp | None:
    try:
        st = p.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def _walk_stack(workspace: Path, is_scratch: Callable[[str], bool]) -> Iterable[Path]:
    """Files of the worker-reachable stack — scratch folders and machine-local env pruned."""
    for dirpath, dirnames, filenames in os.walk(workspace):
        rel_dir = Path(dirpath).relative_to(workspace)
        at_root = rel_dir == Path(".")
        keep = []
        for d in dirnames:
            rel = (rel_dir / d).as_posix()
            if d in _SKIP_DIRNAMES or rel.startswith(_SKIP_REL_PREFIXES):
                continue
            if at_root and is_scratch(d):
                continue        # own + sibling requests' scratch: the worker's legitimate lane
            keep.append(d)
        dirnames[:] = keep
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() not in _SKIP_SUFFIXES:
                yield p


def _git_dirty(root: Path) -> set[str] | None:
    """Repo-relative dirty paths, or None when git is unavailable (advisory data only)."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True, text=True, timeout=15, encoding="utf-8", errors="replace",
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return {ln[3:].strip().split(" -> ")[-1].strip('"') for ln in proc.stdout.splitlines() if len(ln) > 3}


def _landing_dirs(repo_root: Path, workspace: Path) -> list[Path]:
    return [repo_root, repo_root / "backend", workspace]


def _listing(d: Path, names: frozenset[str]) -> set[str]:
    try:
        return {c.name for c in d.iterdir() if c.is_file() and c.name in names}
    except OSError:
        return set()


def _env_files(repo_root: Path) -> Iterable[Path]:
    for base in (repo_root, repo_root / "backend"):
        for p in (*base.glob(".env"), *base.glob(".env.*")):
            if p.is_file():
                yield p


def _store_files(repo_root: Path) -> Iterable[Path]:
    for name in GUARDED_STORE_DIRS:
        d = repo_root / "backend" / name
        if d.is_dir():
            yield from (p for p in d.rglob("*") if p.is_file())


def snapshot(
    workspace: Path, *, signature_names: frozenset[str], is_scratch: Callable[[str], bool],
) -> LaneBaseline:
    """Capture the attributable surfaces. Reads file bytes only inside the workspace stack; ``.env``
    and store files are fingerprinted by metadata — their contents are never read here."""
    repo_root = workspace.parent
    base = LaneBaseline(git_dirty=_git_dirty(repo_root))
    budget = _RESTORE_TOTAL_CAP
    for p in _walk_stack(workspace, is_scratch):
        stamp = _stamp(p)
        if stamp is None:
            continue
        data: bytes | None = None
        if stamp[1] <= _RESTORE_FILE_CAP and stamp[1] <= budget:
            try:
                data = p.read_bytes()
                budget -= len(data)
            except OSError:
                data = None
        base.stack[p.relative_to(workspace).as_posix()] = (stamp, data)
    for d in _landing_dirs(repo_root, workspace):
        base.landing[d] = _listing(d, signature_names)
    for p in _env_files(repo_root):
        if (s := _stamp(p)) is not None:
            base.env[str(p)] = s
    for p in _store_files(repo_root):
        if (s := _stamp(p)) is not None:
            base.stores[str(p)] = s
    return base


def _check_stack(workspace: Path, before: LaneBaseline, is_scratch, verdict: GuardVerdict) -> None:
    seen: set[str] = set()
    for p in _walk_stack(workspace, is_scratch):
        rel = p.relative_to(workspace).as_posix()
        seen.add(rel)
        prior = before.stack.get(rel)
        if prior is None:                                   # stray new file in the stack
            p.unlink(missing_ok=True)
            verdict.escaped.append(f"analytics_workspace/{rel}")
            verdict.reverted.append(f"analytics_workspace/{rel}")
            continue
        (p_mtime, p_size), data = prior
        now = _stamp(p)
        if now is None or now == (p_mtime, p_size):
            continue
        try:
            current = p.read_bytes()
        except OSError:
            continue
        if data is not None and current == data:
            continue                                        # touched, bytes identical: not damage
        verdict.escaped.append(f"analytics_workspace/{rel}")
        if data is not None:
            p.write_bytes(data)
            verdict.reverted.append(f"analytics_workspace/{rel}")
    for rel, (_, data) in before.stack.items():
        if rel in seen:
            continue
        verdict.escaped.append(f"analytics_workspace/{rel} (deleted)")
        if data is not None:
            target = workspace / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            verdict.reverted.append(f"analytics_workspace/{rel}")


def _check_landing(before: LaneBaseline, names: frozenset[str], repo_root: Path, verdict: GuardVerdict) -> None:
    for d, prior in before.landing.items():
        for name in sorted(_listing(d, names) - prior):
            (d / name).unlink(missing_ok=True)
            rel = (d / name).relative_to(repo_root).as_posix()
            verdict.escaped.append(rel)
            verdict.reverted.append(rel)


def _check_env(before: LaneBaseline, repo_root: Path, verdict: GuardVerdict) -> None:
    for p in _env_files(repo_root):
        s = _stamp(p)
        if s is not None and before.env.get(str(p)) != s:
            verdict.escaped.append(p.relative_to(repo_root).as_posix())


def _parses(p: Path) -> bool:
    try:
        json.loads(p.read_text(encoding="utf-8"))
        return True
    except (OSError, ValueError):
        return False


def _check_stores(before: LaneBaseline, repo_root: Path, verdict: GuardVerdict) -> None:
    now: dict[str, Path] = {str(p): p for p in _store_files(repo_root)}
    for path_s in before.stores:
        if path_s not in now:                               # append-only stores: deletion is damage
            verdict.escaped.append(Path(path_s).relative_to(repo_root).as_posix() + " (deleted)")
    for path_s, p in now.items():
        if p.suffix.lower() != ".json" or before.stores.get(path_s) == _stamp(p):
            continue
        if _parses(p):
            continue
        time.sleep(_PARSE_RETRY_S)                          # may be the pipeline mid-write
        if not _parses(p):
            verdict.escaped.append(p.relative_to(repo_root).as_posix() + " (unparsable)")


def check(
    workspace: Path, before: LaneBaseline, *, signature_names: frozenset[str],
    is_scratch: Callable[[str], bool],
) -> GuardVerdict:
    """Judge the post-run state. Reverts the worker's own writes where it can; blames nothing else."""
    repo_root = workspace.parent
    verdict = GuardVerdict()
    _check_stack(workspace, before, is_scratch, verdict)
    _check_landing(before, signature_names, repo_root, verdict)
    _check_env(before, repo_root, verdict)
    _check_stores(before, repo_root, verdict)
    after = _git_dirty(repo_root)
    if before.git_dirty is not None and after is not None:
        attributed = {Path(e.split(" (")[0]).as_posix() for e in verdict.escaped}
        verdict.observed_churn = sorted(
            p for p in after - before.git_dirty
            if not p.startswith("analytics_workspace/") and p not in attributed
        )
    verdict.escaped = sorted(dict.fromkeys(verdict.escaped))
    return verdict
