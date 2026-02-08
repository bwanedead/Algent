"""Launch Ralph Engine commands in a new terminal window (Windows)."""

from __future__ import annotations

import subprocess
from shutil import which
from typing import Optional


def _spawn_windows_terminal(command: str, cwd: Optional[str], title: str) -> bool:
    wt = which("wt.exe") or which("wt")
    if not wt:
        return False

    shell = which("pwsh") or which("powershell") or "powershell"
    args = [wt, "new-tab"]
    if cwd:
        args.extend(["-d", cwd])
    args.extend([shell, "-NoExit", "-Command", command])

    try:
        subprocess.Popen(args)
        return True
    except Exception:
        return False


def run_in_terminal(command: str, title: str, cwd: Optional[str] = None) -> dict:
    if not command:
        return {"status": "error", "message": "command is required"}

    if _spawn_windows_terminal(command, cwd, title):
        return {"status": "ok", "command": command, "title": title, "terminal": "windows-terminal"}

    cmd = [
        "cmd.exe",
        "/c",
        "start",
        title,
        "cmd.exe",
        "/k",
        command,
    ]
    try:
        subprocess.Popen(cmd, cwd=cwd)
        return {"status": "ok", "command": command, "title": title, "terminal": "cmd"}
    except Exception as exc:  # pragma: no cover - OS-specific
        return {"status": "error", "message": str(exc), "command": command, "title": title}
