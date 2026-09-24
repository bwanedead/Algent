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
#: After the laptop wakes, a run whose connection survived shows activity within one model call's
#: network timeout (15 min). One that went quiet across the sleep is holding a dead socket.
WAKE_GRACE_S = 20 * 60
#: A tick this late means the machine was asleep, not that the run was stuck.
_SLEEP_GAP_FACTOR = 5
_WORKSPACE = Path(__file__).resolve().parents[5] / "analytics_workspace"


class Watchdog(threading.Thread):
    def __init__(self, *, stall_s: float = STALL_S, check_s: float = _CHECK_S,
                 wake_grace_s: float = WAKE_GRACE_S,
                 record: Path | None = None, on_stall=None) -> None:
        super().__init__(name="rail-watchdog", daemon=True)
        self.stall_s, self.check_s, self.record = stall_s, check_s, record
        self.wake_grace_s = wake_grace_s
        self.on_stall = on_stall or (lambda: os._exit(3))
        self._last = time.time()
        self._woke = 0.0
        self._stop = threading.Event()

    def touch(self) -> None:
        self._last = time.time()

    def stop(self) -> None:
        self._stop.set()

    def idle_s(self) -> float:
        return time.time() - max(self._last, _scratch_activity())

    def _limit(self) -> float:
        # Just woken and nothing has happened since: judge it on the short window.
        return self.wake_grace_s if self._woke and self._last <= self._woke else self.stall_s

    def run(self) -> None:
        tick = time.time()
        while not self._stop.wait(self.check_s):
            now = time.time()
            if now - tick > self.check_s * _SLEEP_GAP_FACTOR:
                # The laptop slept. Hours of "no progress" were a closed lid, not a hang: restart
                # the clock from the wake, and give the run a short window to show it is alive.
                self._last = self._woke = now
                print(f"[watchdog] machine slept ~{int((now - tick) // 60)} min — run continues",
                      file=sys.stderr, flush=True)
            tick = now
            idle = self.idle_s()
            if idle < self._limit():
                continue
            note = (f"stalled: no events and no chart-worker activity for {int(idle // 60)} min "
                    + ("after the machine woke — a call died across the sleep; "
                       if self._woke and self._last <= self._woke else "")
                    + "exiting so the lock frees")
            print(f"[watchdog] {note}", file=sys.stderr, flush=True)
            if self.record is not None:
                try:
                    self.record.parent.mkdir(parents=True, exist_ok=True)
                    self.record.write_text(note + "\n", encoding="utf-8")
                except OSError:
                    pass
            self.on_stall()
            return


_BACKEND = Path(__file__).resolve().parents[4]
#: Long enough for this process to die and release the single-flight lock before resume takes it.
_RELAUNCH_DELAY_S = 20


def recover_and_exit(*, run_id: str, run_dir: Path | None, spent) -> None:
    """The stall path: bank what this attempt spent, relaunch resume ONCE, then exit.

    Closing the lid mid-run should not need a human to restart it. So the first stall of a run
    hands itself to ``newsroom resume`` (every finished step is on disk; resume redoes only the
    one in flight). A second stall of the same run does not: something is really wrong, and a
    loop of relaunches is how an unattended process spends money.
    """
    from algent_backend.agent_system.foundation import spend_budget

    try:
        spend_budget.record_partial(run_id, float(spent()))
    except Exception:  # noqa: BLE001 — the envelope then keeps the full cap reserved: safe side
        pass
    if run_dir is not None:
        marker = run_dir / "audit" / "auto_resumed.txt"
        try:
            if not marker.exists():
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text(time.strftime("%Y-%m-%d %H:%M:%S") + "\n", encoding="utf-8")
                _launch_resume(run_dir)
                print("[watchdog] relaunched as `newsroom resume` (once)", file=sys.stderr, flush=True)
        except Exception as exc:  # noqa: BLE001 — exiting is still right; resume by hand
            print(f"[watchdog] could not relaunch: {exc}", file=sys.stderr, flush=True)
    os._exit(3)


def _launch_resume(run_dir: Path) -> None:
    import subprocess

    script = ("import subprocess, sys, time; time.sleep(%d); sys.exit(subprocess.call("
              "[sys.executable, '-m', 'algent_backend.cli', 'newsroom', 'resume', '--run', %r]))"
              % (_RELAUNCH_DELAY_S, str(run_dir)))
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    log = open(run_dir / "audit" / "auto_resume.log", "ab")  # noqa: SIM115 — owned by the child
    subprocess.Popen([sys.executable, "-c", script], cwd=str(_BACKEND), stdout=log, stderr=log,
                     stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)


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
