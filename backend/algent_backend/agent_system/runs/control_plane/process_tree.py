"""
Process-tree kill + timeout run — Windows-safe nested CLI cleanup.

``subprocess.run(..., timeout=)`` only kills the direct child. On Windows, npm ``.cmd``
shims spawn grandchildren (node/codex/grok) that keep burning RAM after a timeout or a
force-killed parent. One helper: own process group + tree-kill on timeout / cancel.
"""

from __future__ import annotations

import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any

from .liveness import process_alive

#: How often to look at the progress probe while a child runs. Short enough to notice a stall
#: promptly, long enough that watching costs nothing next to a multi-minute subprocess.
_POLL_S = 5.0


def terminate_tree(pid: int | None) -> bool:
    """Hard-kill ``pid`` and its descendants. Returns whether a live process was signalled."""
    if pid is None or not process_alive(pid):
        return False
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                capture_output=True,
                check=False,
            )
        else:
            import os
            import signal

            try:
                os.killpg(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                os.kill(pid, signal.SIGTERM)
        return True
    except Exception:  # noqa: BLE001 — best-effort cleanup
        return False


def run_capturing(
    argv: list[str],
    *,
    timeout: float,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    encoding: str = "utf-8",
    errors: str = "replace",
    idle_timeout: float = 0.0,
    progress: Callable[[], object] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Like ``subprocess.run`` with capture, but tree-kills on timeout.

    Starts a new process group/session so Windows ``taskkill /T`` and Unix ``killpg``
    can reap the whole CLI tree (shim → node → agent).

    ``progress`` makes the deadline STOP MEANING "how long may this take" and start meaning
    "how long may this take while doing nothing". Pass a cheap callable returning some token
    that changes while the child is working (file count and size under its scratch folder, say):
    the wait then only expires after ``idle_timeout`` with an unchanged token, or at ``timeout``
    as an absolute backstop. Without it, behaviour is the previous single blocking wait.

    This exists because a fixed ceiling cannot tell a stuck child from a slow one, and ours was
    set inside the range where work actually finishes — measured over nine figures, two succeeded
    at 601s and 605s against a 600s cap, and one was killed at 602s. Killing a worker that is
    still writing files buys nothing; it spends the full ceiling and returns no artifact.
    """
    kwargs: dict[str, Any] = {
        "args": argv,
        "cwd": cwd,
        "env": env,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": encoding,
        "errors": errors,
    }
    if sys.platform == "win32":
        # CREATE_NEW_PROCESS_GROUP so taskkill /T can target this tree.
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    else:
        kwargs["start_new_session"] = True

    proc = subprocess.Popen(**kwargs)
    deadline = time.monotonic() + timeout
    last_progress = time.monotonic()
    token = progress() if progress else None
    try:
        while True:
            # Without a progress probe this is exactly the old single blocking wait.
            slice_s = timeout if progress is None else min(_POLL_S, max(0.1, deadline - time.monotonic()))
            try:
                stdout, stderr = proc.communicate(timeout=slice_s)
                break
            except subprocess.TimeoutExpired:
                if progress is None:
                    raise
                now = time.monotonic()
                current = progress()
                if current != token:
                    token, last_progress = current, now
                # Still working, still inside the absolute backstop → let it work.
                if now - last_progress < idle_timeout and now < deadline:
                    continue
                raise
    except subprocess.TimeoutExpired:
        terminate_tree(proc.pid)
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", ""
        raise subprocess.TimeoutExpired(
            cmd=argv, timeout=timeout, output=stdout, stderr=stderr,
        ) from None
    return subprocess.CompletedProcess(
        argv, proc.returncode if proc.returncode is not None else -1, stdout, stderr,
    )
