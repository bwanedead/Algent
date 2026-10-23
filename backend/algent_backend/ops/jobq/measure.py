"""
What the runner measures about the machine and its children: peak RSS of a job's process tree, available memory, and the resident services' RSS.

Peak RSS comes from ``os.wait4`` on the child, whose rusage covers the child and its waited-for descendants (the python process, the shell script, the
tools it ran), so no sampling thread is needed. Windows has no ``wait4``: the peak is then unknown (None), never a guess.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from . import flags

_PEAKS_KB: list[int] = []


def reset() -> None:
    _PEAKS_KB.clear()


def note_child_rss_kb(kb: int) -> None:
    _PEAKS_KB.append(kb)


def peak_mb() -> float | None:
    """Largest child RSS reaped since ``reset()``, MB; None where it cannot be measured."""
    return round(max(_PEAKS_KB) / 1024, 1) if _PEAKS_KB else None


def reap(proc: subprocess.Popen) -> int:
    """Wait for ``proc`` like ``proc.wait()`` and note its tree's peak RSS."""
    if not hasattr(os, "wait4"):
        return proc.wait()
    _, status, ru = os.wait4(proc.pid, 0)
    proc.returncode = os.waitstatus_to_exitcode(status)
    note_child_rss_kb(int(ru.ru_maxrss / 1024) if sys.platform == "darwin" else int(ru.ru_maxrss))
    return proc.returncode


def call(cmd: list[str], cwd: str | None = None) -> int:
    """``subprocess.call`` that measures the peak. On any exception (a preemption SIGTERM) the child's group is terminated first."""
    proc = subprocess.Popen(cmd, cwd=cwd, start_new_session=hasattr(os, "wait4"))
    try:
        return reap(proc)
    except BaseException:
        terminate(proc)
        raise


def terminate(proc: subprocess.Popen) -> None:
    try:
        if hasattr(os, "killpg"):
            os.killpg(proc.pid, 15)
        else:
            proc.terminate()
    except OSError:
        pass


def mem_available_mb() -> float | None:
    from algent_backend.ops import doctor

    return doctor.Probes().mem_available_mb()


def services_rss_mb(proc_root: Path = Path("/proc")) -> dict[str, float]:
    """Current RSS of each resident service (flags.SERVICE_MATCH), MB; a service not found is absent. Linux only; {} elsewhere."""
    out: dict[str, float] = {}
    try:
        entries = [p for p in proc_root.iterdir() if p.name.isdigit()]
    except OSError:
        return out
    for p in entries:
        try:
            cmd = (p / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
            for name, needles in flags.SERVICE_MATCH.items():
                if all(n in cmd for n in needles):
                    kb = next(int(line.split()[1]) for line in (p / "status").read_text().splitlines() if line.startswith("VmRSS:"))
                    out[name] = out.get(name, 0.0) + kb / 1024
        except (OSError, StopIteration, ValueError):
            continue
    return {k: round(v, 1) for k, v in out.items()}
