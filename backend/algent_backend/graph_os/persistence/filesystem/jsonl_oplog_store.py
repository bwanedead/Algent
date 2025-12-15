"""
Filesystem stores for debugging.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable
import json

from ...graphops.op_types import GraphOp


class JsonlOpLogStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append_ops(self, ops: Iterable[GraphOp]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            for op in ops:
                handle.write(json.dumps({"op_id": op.op_id.value.hex, "op_type": op.op_type}))
                handle.write("\n")
