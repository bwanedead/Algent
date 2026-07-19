"""
Process liveness — is the OS process behind a run still there?

Pure OS mechanics (the same category as ``fsio``), living in the control plane because the *state*
layer needs it: a run whose process has vanished must not keep reporting ``running``. The CLI
re-exports this rather than owning a second copy.
"""

from __future__ import annotations

import sys

_STILL_ACTIVE = 259
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def process_alive(pid: int | None) -> bool:
    """Best-effort liveness check; errs on 'alive' so a watcher never false-alarms.

    Windows note: ``os.kill(pid, 0)`` is NOT a probe there (a non-console signal value terminates
    the process), so we query via OpenProcess instead.
    """
    if pid is None:
        return False
    if sys.platform == "win32":
        return _alive_windows(pid)
    import os

    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return True


def _alive_windows(pid: int) -> bool:
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
    except Exception:  # noqa: BLE001 — an unprobeable process is assumed alive, never falsely dead
        return True
