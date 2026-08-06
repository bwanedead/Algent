"""
Process-tree kill + timeout run — Windows-safe nested CLI cleanup.

``subprocess.run(..., timeout=)`` only kills the direct child. On Windows, npm ``.cmd``
shims spawn grandchildren (node/codex/grok) that keep burning RAM after a timeout or a
force-killed parent. One helper: own process group + tree-kill on timeout / cancel.
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

from .liveness import process_alive


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
) -> subprocess.CompletedProcess[str]:
    """Like ``subprocess.run`` with capture, but tree-kills on timeout.

    Starts a new process group/session so Windows ``taskkill /T`` and Unix ``killpg``
    can reap the whole CLI tree (shim → node → agent).
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
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
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
