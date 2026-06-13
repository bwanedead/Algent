"""
Shared filesystem io for the control plane: atomic writes.

Watchers poll these files while a run is live, so every full-file write goes
through temp-file + replace — a reader never sees a torn document.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_text(target: Path, body: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_json_file(target: Path, payload: Any) -> None:
    atomic_write_text(target, json.dumps(payload, ensure_ascii=False, indent=2, default=str))
