"""
Filesystem-based JSONL op log store.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, List

from ...core.ids import WorkspaceId
from ...core.primitives.snapshot import Snapshot
from ...graphops.op_apply import apply_ops
from ...graphops.op_types import GraphOp, deserialize_op, serialize_op
from ..store_interface import WorkspaceStore


class JsonlOpLogStore(WorkspaceStore):
    """
    Minimal append-only log that stores one workspace per file.
    """

    def __init__(self, root_path: Path) -> None:
        self.root_path = root_path
        self.root_path.mkdir(parents=True, exist_ok=True)

    def _normalize_workspace_id(self, workspace_id: str) -> WorkspaceId:
        return WorkspaceId.from_str(workspace_id)

    def _log_path(self, workspace_id: str) -> Path:
        normalized = self._normalize_workspace_id(workspace_id)
        return self.root_path / f"{normalized.value}.jsonl"

    def load_snapshot(self, workspace_id: str) -> Snapshot:
        workspace = self._normalize_workspace_id(workspace_id)
        snapshot = Snapshot.empty(workspace)
        ops = self.iter_ops(workspace_id)
        if not ops:
            return snapshot
        return apply_ops(snapshot, ops)

    def append_ops(self, workspace_id: str, ops: Iterable[GraphOp]) -> None:
        path = self._log_path(workspace_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for op in ops:
                payload = serialize_op(op)
                handle.write(json.dumps(payload, sort_keys=True))
                handle.write("\n")

    def iter_ops(self, workspace_id: str) -> List[GraphOp]:
        path = self._log_path(workspace_id)
        if not path.exists():
            return []
        ops: List[GraphOp] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                payload = json.loads(line)
                ops.append(deserialize_op(payload))
        return ops
