"""
Live spend heartbeat — the on-disk signal the out-of-process watchdog (``ops/watchdog.py``) reads.

The cost ledger lives in process memory, so nothing outside a run can see what it has spent. Every
charge lands here too: one small JSON file per process per UTC day, ``<runs_data>/live_spend/<day>__<pid>.json``,
holding the process's cumulative settled spend (across every article it runs). Writes are throttled and
best-effort — telemetry must never break a model call.

Also owns the *spend halt* marker (``<runs_data>/spend_halt.json``). The watchdog writes it when the day's spend
passes the ceiling; ``try_reserve`` then refuses every billable op until the UTC day rolls over (or an operator
clears it), so even a freshly launched run cannot spend.
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

_WRITE_EVERY_S = 3.0
_HALT_CACHE_S = 5.0

_total = 0.0
_started = time.time()
_last_write = 0.0
_halt_checked_at = 0.0
_halt_cached = False


def _root() -> Path:
    from algent_backend.agent_system.runs.control_plane.layout import runs_data_root

    return runs_data_root()


def today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def live_dir() -> Path:
    return _root() / "live_spend"


def halt_path() -> Path:
    return _root() / "spend_halt.json"


def note(usd: float) -> None:
    """Add a settled charge to this process's heartbeat. Never raises."""
    global _total
    _total += max(0.0, float(usd))
    if time.time() - _last_write >= _WRITE_EVERY_S:
        flush()


def flush() -> None:
    global _last_write
    _last_write = time.time()
    try:
        d = live_dir()
        d.mkdir(parents=True, exist_ok=True)
        pid = os.getpid()
        path = d / f"{today()}__{pid}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"pid": pid, "started": _started, "usd": round(_total, 6), "ts": _last_write}),
                       encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def halted() -> bool:
    """True while today's spend halt marker stands. Cached a few seconds: this is on the model-call path."""
    global _halt_checked_at, _halt_cached
    now = time.time()
    if now - _halt_checked_at < _HALT_CACHE_S:
        return _halt_cached
    _halt_checked_at = now
    try:
        _halt_cached = json.loads(halt_path().read_text(encoding="utf-8")).get("day") == today()
    except (OSError, ValueError):
        _halt_cached = False
    return _halt_cached
