"""
The run ledger, ``runs_data/jobs.jsonl``: one JSON line per job run (``kind: "run"``) and per memory-guard breach (``kind: "breach"``), bounded by age
(``LEDGER_KEEP_DAYS``) and by row count, compacted in place when the file grows past ``COMPACT_AT_BYTES``. It is what the guard, ``newsroom products
runs``, ``newsroom products capacity`` and the envelope's queue rows read: measurement first, registry estimates only where it has nothing yet.

Never raises on write: a ledger that cannot be written must not fail the job it describes.
"""

from __future__ import annotations

import json
import math
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from . import flags


def default_path() -> Path:
    from algent_backend.agent_system.foundation import live_spend

    return live_spend.halt_path().parent / "jobs.jsonl"


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile, None for no data."""
    if not values:
        return None
    s = sorted(values)
    return s[max(0, math.ceil(q / 100 * len(s)) - 1)]


class Ledger:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path or default_path()

    def append(self, row: dict[str, Any], *, now: datetime | None = None) -> None:
        row = {"ts": (now or datetime.now(UTC)).isoformat(timespec="seconds"), **row}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, separators=(",", ":")) + "\n")
            if self.path.stat().st_size > flags.COMPACT_AT_BYTES:
                self.compact(now=now)
        except OSError:
            pass

    def rows(self, *, since: datetime | None = None, kind: str | None = None) -> list[dict[str, Any]]:
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out = []
        for line in lines:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if kind and r.get("kind", "run") != kind:
                continue
            if since and (_ts(r) or datetime.min.replace(tzinfo=UTC)) < since:
                continue
            out.append(r)
        return out

    def compact(self, *, now: datetime | None = None) -> int:
        """Drop rows older than the retention window, then all but the newest ``LEDGER_MAX_ROWS``. Returns rows dropped."""
        horizon = (now or datetime.now(UTC)) - timedelta(days=flags.LEDGER_KEEP_DAYS)
        rows = self.rows(since=horizon)
        kept = rows[-flags.LEDGER_MAX_ROWS:]
        try:
            before = len(self.path.read_text(encoding="utf-8").splitlines())
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in kept), encoding="utf-8")
            os.replace(tmp, self.path)
            return before - len(kept)
        except OSError:
            return 0


def _ts(row: dict[str, Any]) -> datetime | None:
    try:
        t = datetime.fromisoformat(row["ts"])
        return t if t.tzinfo else t.replace(tzinfo=UTC)
    except (KeyError, ValueError):
        return None


def end_time(row: dict[str, Any]) -> datetime | None:
    """A run row is written when the run ends, so ``ts`` is its end."""
    return _ts(row)


def stats(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per job: runs, ok, failed, skipped (busy / memory), coalesced, p50/p95 duration (min), p50/p95/max lock wait (min), p95 peak RSS (MB), deadline misses."""
    by: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        if r.get("kind", "run") == "run":
            by.setdefault(r["job"], []).append(r)
    out: dict[str, dict[str, Any]] = {}
    for job, rs in sorted(by.items()):
        ran = [r for r in rs if r.get("outcome") in ("ok", "failed", "preempted")]
        dur = [r["duration_s"] / 60 for r in ran if r.get("duration_s") is not None]
        wait = [r.get("wait_s", 0.0) / 60 for r in rs if r.get("outcome") != "coalesced"]
        rss = [r["peak_rss_mb"] for r in ran if r.get("peak_rss_mb")]
        out[job] = {
            "runs": len(ran), "ok": sum(r["outcome"] == "ok" for r in ran), "failed": sum(r["outcome"] == "failed" for r in ran),
            "skipped": sum(r.get("outcome") == "skipped" for r in rs), "coalesced": sum(r.get("outcome") == "coalesced" for r in rs),
            "p50_min": _r(percentile(dur, 50)), "p95_min": _r(percentile(dur, 95)),
            "wait_p50_min": _r(percentile(wait, 50)), "wait_p95_min": _r(percentile(wait, 95)), "wait_max_min": _r(max(wait) if wait else None),
            "rss_p95_mb": _r(percentile(rss, 95), 0), "rss_samples": len(rss),
            "deadline_missed": sum(bool(r.get("deadline_missed")) for r in ran),
        }
    return out


def _r(x: float | None, nd: int = 1) -> float | None:
    return None if x is None else round(x, nd)
