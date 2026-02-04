"""Run Ralph Engine doctor checks via CLI."""

from __future__ import annotations

import subprocess
from typing import Optional


def run_doctor(project_root: str, run_id: Optional[str] = None) -> dict:
    command = ["ralph-engine", "doctor", project_root]
    if run_id:
        command.extend(["--run-id", run_id])

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )

    return {
        "command": " ".join(command),
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
