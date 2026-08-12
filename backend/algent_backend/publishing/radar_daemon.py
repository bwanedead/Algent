"""
The radar supervisor — "leave it running" mode.

One loop that does two jobs on different clocks: refresh discovery every couple of hours, and
release one queued post about once an hour with enough jitter that it never looks like a
metronome. Everything it needs to survive is on disk, because the thing it must survive is the
laptop lid closing mid-cycle.

DESIGN RULE: STOPPING MUST BE THE MOST RELIABLE OPERATION HERE.

The operator will sometimes want it off while having no agent available and no patience for
debugging — so stopping does not depend on the loop being healthy, on signals being delivered,
or on Python being reachable. A stop request is a FILE. The loop checks for it between every
step and exits; if the loop is wedged and cannot check, ``stop`` escalates to a tree-kill of the
recorded pid. Either way the answer to "is it off" is a question about the filesystem and the
process table, not about whether some daemon agreed to die.

Liveness is judged with the house probe, never a local ``os.kill(pid, 0)`` — on Windows that
signal number is CTRL_C_EVENT and a dead pid reports as alive, which would make ``status`` say
"running" forever after a crash.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from algent_backend.agent_system.runs.control_plane.liveness import process_alive
from algent_backend.agent_system.runs.control_plane.process_tree import terminate_tree

_STATE_DIR = Path("runs_data")
PID_FILE = _STATE_DIR / "radar_daemon.json"
STOP_FILE = _STATE_DIR / "radar_daemon.stop"
LOG_FILE = _STATE_DIR / "radar_daemon.log"

#: Defaults, overridable per start. Discovery is the expensive clock; posting is the visible one.
DISCOVERY_EVERY_MIN = 120
POST_EVERY_MIN = 40
#: Posting cadence is drawn from a window around POST_EVERY_MIN rather than fixed, so the
#: timeline never shows a post on a fixed beat. Roughly 25-55 minutes at the default.
POST_JITTER_MIN = 15
#: How often the loop wakes to check the clocks and the stop file. Short so a stop is felt
#: almost immediately; the loop does nothing on the vast majority of ticks.
HEARTBEAT_S = 5


@dataclass
class DaemonState:
    pid: int
    started_at: str
    discovery_every_min: int = DISCOVERY_EVERY_MIN
    post_every_min: int = POST_EVERY_MIN
    last_discovery_at: str = ""
    last_post_at: str = ""
    next_post_at: str = ""
    posts_sent: int = 0
    sweeps_run: int = 0
    errors: list[str] = field(default_factory=list)
    stopped_at: str = ""


def _now() -> datetime:
    return datetime.now(UTC)


def log(line: str) -> None:
    """Append a timestamped line and echo it. The log is the operator's window when no agent is."""
    stamp = _now().strftime("%Y-%m-%d %H:%M:%S")
    text = f"[{stamp}] {line}"
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(text + "\n")
    print(text, flush=True)


def read_state() -> DaemonState | None:
    if not PID_FILE.exists():
        return None
    try:
        return DaemonState(**json.loads(PID_FILE.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def write_state(state: DaemonState) -> None:
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")


def running() -> tuple[bool, DaemonState | None]:
    """(is it actually alive, recorded state). A stale pid file is not 'running'."""
    state = read_state()
    if state is None or state.stopped_at:
        return False, state
    return process_alive(state.pid), state


def request_stop() -> None:
    STOP_FILE.parent.mkdir(parents=True, exist_ok=True)
    STOP_FILE.write_text(_now().isoformat(), encoding="utf-8")


def stop_requested() -> bool:
    return STOP_FILE.exists()


def clear_stop() -> None:
    STOP_FILE.unlink(missing_ok=True)


def stop(*, timeout_s: float = 20.0) -> dict[str, Any]:
    """Ask it to stop, then make sure. Returns a report the operator can read at a glance."""
    alive, state = running()
    request_stop()
    if not alive:
        # Nothing to kill: either never started, already exited, or the lid closed on it.
        if state is not None:
            state.stopped_at = _now().isoformat()
            write_state(state)
        clear_stop()
        return {"was_running": False, "stopped": True,
                "note": "no live radar process — nothing to stop"}

    assert state is not None
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not process_alive(state.pid):
            state.stopped_at = _now().isoformat()
            write_state(state)
            clear_stop()
            return {"was_running": True, "stopped": True, "pid": state.pid,
                    "how": "graceful — the loop saw the stop file and exited"}
        time.sleep(0.5)

    # It did not go quietly — most often because it is blocked inside a discovery subprocess,
    # which can run for minutes and cannot poll the stop file. Escalate rather than wait: a
    # radar that cannot be turned off on demand is worse than a discovery cycle thrown away.
    # Killing the TREE matters here, since the child t0 run must die with it; the newsroom run
    # lock it leaves behind is reclaimed by the next run's stale-pid recovery.
    killed = terminate_tree(state.pid)
    time.sleep(1.0)
    gone = not process_alive(state.pid)
    state.stopped_at = _now().isoformat() if gone else ""
    write_state(state)
    if gone:
        clear_stop()
    return {"was_running": True, "stopped": gone, "pid": state.pid,
            "how": "force — the loop did not exit in time, so its process tree was killed",
            "signalled": killed}
