"""
Run directory layout — single source of truth for where run files live.

Everything else (recorder, CLI, tests) asks this module for paths instead of
joining strings, so the layout can evolve in one place. The root resolves from
``ALGENT_RUNS_DIR`` at call time (not import time) so tests can isolate runs
under a temp directory.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

# backend/ (the directory containing algent_backend/) — runs_data sits beside
# the package, not inside it, like other data trees.
_BACKEND_DIR = Path(__file__).resolve().parents[4]

RUNS_DIR_ENV = "ALGENT_RUNS_DIR"


def runs_data_root() -> Path:
    """Resolve the runs-data root (env override first)."""
    override = os.environ.get(RUNS_DIR_ENV)
    if override:
        return Path(override)
    return _BACKEND_DIR / "runs_data"


@dataclass(frozen=True)
class RunPaths:
    """All filesystem locations owned by one run."""

    root: Path

    @property
    def request_file(self) -> Path:
        return self.root / "request.json"

    @property
    def state_file(self) -> Path:
        return self.root / "state.json"

    @property
    def audit_dir(self) -> Path:
        return self.root / "audit"

    @property
    def events_file(self) -> Path:
        return self.audit_dir / "events.jsonl"

    @property
    def timeline_file(self) -> Path:
        # Flat in audit/, beside the per-turn JSONs and the machine event stream,
        # so the curated human log and the turn detail are visible side-by-side.
        return self.audit_dir / "timeline.md"

    def turn_file(self, turn: int) -> Path:
        # audit/turn_0001.json … — one JSON per model turn, flat beside timeline.md.
        return self.audit_dir / f"turn_{turn:04d}.json"

    @property
    def error_file(self) -> Path:
        # Full traceback for a failed run — written so a failure is diagnosable
        # from disk without re-running.
        return self.audit_dir / "error.log"

    @property
    def result_file(self) -> Path:
        return self.root / "result.json"

    @property
    def done_file(self) -> Path:
        return self.root / "done.json"

    @property
    def artifacts_dir(self) -> Path:
        return self.root / "artifacts"

    @property
    def child_stdout_file(self) -> Path:
        return self.root / "child_stdout.log"

    @property
    def child_stderr_file(self) -> Path:
        return self.root / "child_stderr.log"


def _agent_dir(agent_id: str, root: Path | None = None) -> Path:
    base = root if root is not None else runs_data_root()
    return base / agent_id


def allocate_run_root(agent_id: str, run_id: str, root: Path | None = None) -> Path:
    """Create and return a new run directory: ``<agent>/<NNNN>__<run_id>``.

    The zero-padded counter comes from a per-agent ``_meta.json`` and is
    monotonic — it never reuses a number even after retention prunes older runs —
    so the highest-numbered directory is always the most recent in a file tree.
    """
    adir = _agent_dir(agent_id, root)
    adir.mkdir(parents=True, exist_ok=True)
    meta = adir / "_meta.json"
    count = 0
    if meta.exists():
        try:
            count = int(json.loads(meta.read_text(encoding="utf-8")).get("count", 0))
        except (OSError, ValueError):
            count = 0
    count += 1
    meta.write_text(json.dumps({"count": count}, indent=2), encoding="utf-8")
    return adir / f"{count:04d}__{run_id}"


def find_run_root(run_id: str, root: Path | None = None) -> Path | None:
    """Locate an existing run directory by run id (search across agent folders)."""
    base = root if root is not None else runs_data_root()
    if not base.exists():
        return None
    matches = sorted(base.glob(f"*/*__{run_id}"))
    return matches[0] if matches else None


def resolve_run_ref(
    ref: str,
    *,
    prefer_agent: str | None = None,
    root: Path | None = None,
) -> Path | None:
    """Locate a run directory from a flexible operator reference.

    Accepts:
      - full run UUID (via ``find_run_root``)
      - absolute/relative path to a run directory
      - counter prefix ``0013`` / ``13`` (latest match; prefer ``prefer_agent`` if set)
      - ``agent_id/0013`` form
    """
    text = (ref or "").strip()
    if not text:
        return None
    base = root if root is not None else runs_data_root()

    # Path to an existing run dir (has artifacts/ or request.json).
    as_path = Path(text)
    if as_path.is_dir() and (
        (as_path / "artifacts").is_dir() or (as_path / "request.json").is_file()
    ):
        return as_path.resolve()

    # Full UUID (with or without agent folder knowledge).
    by_id = find_run_root(text, root=base)
    if by_id is not None:
        return by_id

    # agent_id/NNNN or agent_id/NNNN__uuid
    if "/" in text or "\\" in text:
        parts = text.replace("\\", "/").split("/")
        if len(parts) == 2:
            agent, suffix = parts[0], parts[1]
            adir = base / agent
            if adir.is_dir():
                hit = _match_counter(adir, suffix)
                if hit is not None:
                    return hit

    # Bare counter: 0013 or 13 — prefer a named agent, else any.
    if prefer_agent:
        hit = _match_counter(base / prefer_agent, text)
        if hit is not None:
            return hit
    if base.exists():
        for adir in sorted(base.iterdir()):
            if not adir.is_dir() or adir.name.startswith(("_", ".")):
                continue
            hit = _match_counter(adir, text)
            if hit is not None:
                return hit
    return None


def _match_counter(agent_dir: Path, token: str) -> Path | None:
    """Match ``NNNN`` or ``NNNN__...`` under one agent directory (highest seq wins)."""
    if not agent_dir.is_dir():
        return None
    token = token.strip()
    # Exact dir name or UUID tail already handled elsewhere; here: counter prefix.
    if token.isdigit():
        pad = f"{int(token):04d}"
    elif len(token) >= 4 and token[:4].isdigit() and (len(token) == 4 or token[4] == "_"):
        pad = token[:4]
    else:
        # Full dir name under this agent?
        direct = agent_dir / token
        return direct if direct.is_dir() else None
    matches = [p for p in agent_dir.iterdir() if p.is_dir() and p.name.startswith(f"{pad}__")]
    if not matches:
        return None
    matches.sort(key=_run_seq, reverse=True)
    return matches[0]


def resolve_or_allocate_run_root(run_id: str, agent_id: str, root: Path | None = None) -> Path:
    """Return the existing run directory for ``run_id``, or allocate a new one.

    ``start`` allocates the directory up front; the executing process then finds
    that same directory. A direct ``RunService`` call (no ``start``) allocates.
    """
    existing = find_run_root(run_id, root)
    return existing if existing is not None else allocate_run_root(agent_id, run_id, root)


def index_file(root: Path | None = None) -> Path:
    """The cross-run ledger index file."""
    base = root if root is not None else runs_data_root()
    return base / "runs_index.jsonl"


def _run_seq(run_dir: Path) -> int:
    try:
        return int(run_dir.name.split("__", 1)[0])
    except ValueError:
        return -1


def prune_runs(keep: int = 5, root: Path | None = None) -> list[str]:
    """Keep only the ``keep`` most recent run dirs *per agent*; remove older ones.

    Recency is the monotonic counter prefix. The window keeps dev clean without
    accumulating runs forever; the cross-run ledger still records history.
    Returns removed directory names. Best-effort: never raises.
    """
    base = root if root is not None else runs_data_root()
    if not base.exists():
        return []
    removed: list[str] = []
    try:
        agent_dirs = [p for p in base.iterdir() if p.is_dir()]
    except OSError:
        return []
    for adir in agent_dirs:
        run_dirs = [p for p in adir.iterdir() if p.is_dir() and "__" in p.name]
        if len(run_dirs) <= keep:
            continue
        run_dirs.sort(key=_run_seq, reverse=True)
        for stale in run_dirs[keep:]:
            shutil.rmtree(stale, ignore_errors=True)
            removed.append(stale.name)
    return removed
