"""
Daily housekeeping (``newsroom products housekeeping --apply``, timer ``ohmega-housekeeping``): the two growth paths the product registry found that
nothing was bounding.

- the page-fetch cache (``ALGENT_FETCH_CACHE_DIR`` / ``backend/.cache/fetch``): entries are only ever *read* within a 6 h TTL, but nothing deleted
  the expired ones, so every URL ever fetched stayed on disk;
- the per-job run logs ``~/runlogs/<job>-<date>.log`` that the scheduled paid jobs write: one file per job per day, forever.

Free, no model, idempotent. Dry run unless ``apply``.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

#: A run log is only read to diagnose a recent run; the journal and ``~/ops-log.md`` carry the outcome. A month is plenty.
RUNLOG_KEEP_DAYS = 30


def prune_runlogs(*, apply: bool, home: Path | None = None, now: float | None = None) -> dict[str, int]:
    horizon = (now if now is not None else time.time()) - RUNLOG_KEEP_DAYS * 86400
    d, found, freed = (home or Path.home()) / "runlogs", 0, 0
    for p in d.glob("*.log") if d.is_dir() else ():
        try:
            st = p.stat()
            if st.st_mtime >= horizon:
                continue
            found, freed = found + 1, freed + st.st_size
            if apply:
                p.unlink()
        except OSError:
            continue
    return {"expired": found, "bytes": freed, "deleted": found if apply else 0}


def run(*, apply: bool, home: Path | None = None, now: float | None = None) -> dict[str, Any]:
    from algent_backend.agent_system.tools.sourcing.depth import fetch_content

    return {"apply": apply, "fetch_cache": fetch_content.prune_cache(apply=apply, now=now), "runlogs": prune_runlogs(apply=apply, home=home, now=now)}
