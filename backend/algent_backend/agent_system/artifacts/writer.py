"""
ArtifactWriter — writes run-scoped artifact files and returns refs.

One writer per run, rooted at that run's artifacts directory. The optional
``on_written`` hook lets the harness observe writes (emit an event, collect refs
for the result) without the writer knowing what observation means.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .refs import ArtifactRef

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


class ArtifactWriter:
    """Writes artifacts under one run's artifacts directory."""

    def __init__(
        self,
        artifacts_dir: Path,
        run_id: str,
        on_written: Callable[[ArtifactRef], None] | None = None,
    ) -> None:
        self._dir = artifacts_dir
        self._run_id = run_id
        self._on_written = on_written

    def write_text(self, name: str, content: str, kind: str = "text") -> ArtifactRef:
        return self._write(name, content.encode("utf-8"), kind)

    def write_json(self, name: str, payload: Any, kind: str = "json") -> ArtifactRef:
        body = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        return self._write(name, body.encode("utf-8"), kind)

    def write_bytes(self, name: str, data: bytes, kind: str = "binary") -> ArtifactRef:
        """Persist raw bytes (e.g. a produced chart image) into the run's artifacts."""
        return self._write(name, data, kind)

    def _write(self, name: str, data: bytes, kind: str) -> ArtifactRef:
        safe = _SAFE_NAME.sub("_", name).strip("._") or "artifact"
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / safe
        path.write_bytes(data)

        ref = ArtifactRef(
            artifact_id=str(uuid4()),
            run_id=self._run_id,
            name=name,
            kind=kind,
            relative_path=safe,
            created_at=datetime.now(UTC).isoformat(),
            size_bytes=len(data),
        )
        if self._on_written is not None:
            self._on_written(ref)
        return ref
