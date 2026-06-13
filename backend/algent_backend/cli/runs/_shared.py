"""
Shared CLI mechanics: JSON output, input parsing, process liveness.

Mechanics only — nothing here may interpret run semantics.
"""

from __future__ import annotations

import json
import sys
from typing import Any


def print_json(payload: Any) -> None:
    """Print the command's single JSON document."""
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, default=str)
    sys.stdout.write("\n")


def parse_input_arg(
    input_json: str | None, topic: str | None, goal: str | None = None
) -> dict[str, Any]:
    """Build the run input from ``--input`` JSON and/or the ``--topic``/``--goal`` shortcuts."""
    payload: dict[str, Any] = {}
    if input_json:
        parsed = json.loads(input_json)
        if not isinstance(parsed, dict):
            raise ValueError("--input must be a JSON object")
        payload.update(parsed)
    if topic is not None:
        payload["topic"] = topic
    if goal is not None:
        payload["goal"] = goal
    return payload


def pid_alive(pid: int | None) -> bool:
    """Best-effort liveness check; errs on 'alive' so watchers don't false-alarm.

    Windows note: ``os.kill(pid, 0)`` is NOT a probe on Windows (any non-console
    signal value terminates the process), so we query via OpenProcess instead.
    """
    if pid is None:
        return False
    if sys.platform == "win32":
        return _pid_alive_windows(pid)
    import os

    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return True


_STILL_ACTIVE = 259
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _pid_alive_windows(pid: int) -> bool:
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return exit_code.value == _STILL_ACTIVE
            return True
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return True
