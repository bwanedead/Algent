"""
Filesystem workspace lock helper.
"""
from __future__ import annotations

import json
import os
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ...core.errors import WorkspaceLockError


class WorkspaceFileLock(AbstractContextManager[None]):
    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path
        self._acquired = False

    def __enter__(self) -> None:
        self.acquire()
        return None

    def __exit__(self, exc_type, exc, tb) -> Optional[bool]:
        self.release()
        return None

    def acquire(self) -> None:
        if self._acquired:
            return
        payload = {
            "pid": os.getpid(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            fd = os.open(self.lock_path, flags)
        except FileExistsError as exc:  # noqa: PERF203 - explicit for clarity
            raise WorkspaceLockError(
                f"workspace lock already held at {self.lock_path}"
            ) from exc
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload))
                handle.flush()
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            raise
        self._acquired = True

    def release(self) -> None:
        if not self._acquired:
            return
        try:
            os.unlink(self.lock_path)
        except FileNotFoundError:
            pass
        finally:
            self._acquired = False
