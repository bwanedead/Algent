"""
Run directory layout — single source of truth for where run files live.

Everything else (recorder, CLI, tests) asks this module for paths instead of
joining strings, so the layout can evolve in one place. The root resolves from
``ALGENT_RUNS_DIR`` at call time (not import time) so tests can isolate runs
under a temp directory.
"""

from __future__ import annotations

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
        # audit/human/ — the readable projection, beside the machine event stream.
        return self.audit_dir / "human" / "timeline.md"

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


def run_paths(run_id: str, root: Path | None = None) -> RunPaths:
    """Paths for one run id under the (resolved or given) runs-data root."""
    base = root if root is not None else runs_data_root()
    return RunPaths(root=base / run_id)


def index_file(root: Path | None = None) -> Path:
    """The cross-run ledger index file."""
    base = root if root is not None else runs_data_root()
    return base / "runs_index.jsonl"


def prune_runs(keep: int = 5, root: Path | None = None) -> list[str]:
    """Keep only the most recent ``keep`` run directories; remove older ones.

    Run dirs are the subdirectories of the runs-data root (the index file is left
    alone). Recency is by directory mtime. A small rolling window keeps dev clean
    without accumulating runs forever; the cross-run ledger still records history.
    Returns the removed run ids. Best-effort: never raises.
    """
    base = root if root is not None else runs_data_root()
    if not base.exists():
        return []
    try:
        run_dirs = [p for p in base.iterdir() if p.is_dir()]
    except OSError:
        return []
    if len(run_dirs) <= keep:
        return []
    run_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    removed: list[str] = []
    for stale in run_dirs[keep:]:
        shutil.rmtree(stale, ignore_errors=True)
        removed.append(stale.name)
    return removed
