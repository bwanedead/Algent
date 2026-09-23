"""
The stall watchdog — a run that has stopped making progress ends itself.

A run once sat eight hours inside one model call after the laptop slept: the connection died
without the process noticing, the call's network timeout never fired, and the single-flight lock
held every other run off until a human found it. Per-call timeouts cannot catch that class of
hang — streamed calls and subprocesses sit outside them — so the guard lives at the level that
can see everything: the rail's own event stream, plus file activity in the chart workers'
scratch folders (they draw for many minutes without emitting an event).

No progress on either for ``STALL_S`` and the process records why and exits. The run is left
resumable (every finished stage is on disk), the lock is released by the process dying, and
the spend envelope keeps the run's reservation — a run that died mid-flight is charged its
worst case, never less.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

#: Above every legitimate silence in a run: the chart worker's absolute backstop is 30 minutes
#: (``analytics_worker._TIMEOUT_SOURCED_S``) and it writes files while it works; a model call's
#: network timeout is 15. Forty-five minutes of neither events nor file activity is a hang.
STALL_S = 45 * 60
_CHECK_S = 60
_WORKSPACE = Path(__file__).resolve().parents[5] / "analytics_workspace"


class Watchdog(threading.Thread):
    def __init__(self, *, stall_s: float = STALL_S, check_s: float = _CHECK_S,
                 record: Path | None = None, on_stall=None) -> None:
        super().__init__(name="rail-watchdog", daemon=True)
        self.stall_s, self.check_s, self.record = stall_s, check_s, record
        self.on_stall = on_stall or (lambda: os._exit(3))
        self._last = time.time()
        self._stop = threading.Event()

    def touch(self) -> None:
        self._last = time.time()

    def stop(self) -> None:
        self._stop.set()

    def idle_s(self) -> float:
        return time.time() - max(self._last, _scratch_activity())

    def run(self) -> None:
        while not self._stop.wait(self.check_s):
            idle = self.idle_s()
            if idle < self.stall_s:
                continue
            note = (f"stalled: no events and no chart-worker activity for {int(idle // 60)} min "
                    f"— exiting so the lock frees; resume with `newsroom resume`")
            print(f"[watchdog] {note}", file=sys.stderr, flush=True)
            if self.record is not None:
                try:
                    self.record.parent.mkdir(parents=True, exist_ok=True)
                    self.record.write_text(note + "\n", encoding="utf-8")
                except OSError:
                    pass
            self.on_stall()
            return


def _scratch_activity() -> float:
    """Newest write inside any chart worker's scratch folder (0 when none exist)."""
    newest = 0.0
    if not _WORKSPACE.is_dir():
        return newest
    for folder in _WORKSPACE.iterdir():
        if not (folder.is_dir() and folder.name.startswith(("anx_", "req_"))):
            continue
        for root, _dirs, files in os.walk(folder):
            for name in files:
                try:
                    newest = max(newest, os.path.getmtime(os.path.join(root, name)))
                except OSError:
                    pass
    return newest
