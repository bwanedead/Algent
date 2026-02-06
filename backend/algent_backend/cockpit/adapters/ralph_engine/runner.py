"""Launch Ralph Engine commands in a new terminal window (Windows)."""

from __future__ import annotations

import subprocess


def run_in_terminal(command: str, title: str) -> dict:
    if not command:
        return {"status": "error", "message": "command is required"}

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
        subprocess.Popen(cmd)
        return {"status": "ok", "command": command, "title": title}
    except Exception as exc:  # pragma: no cover - OS-specific
        return {"status": "error", "message": str(exc), "command": command, "title": title}
