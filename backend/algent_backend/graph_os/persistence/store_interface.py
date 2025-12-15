"""
Persistence interfaces for GraphOS stores.
"""
from __future__ import annotations

from typing import Protocol, Iterable

from ..core.primitives.snapshot import Snapshot
from ..graphops.op_types import GraphOp


class WorkspaceStore(Protocol):
    def load_snapshot(self, workspace_id: str) -> Snapshot:
        ...

    def append_ops(self, workspace_id: str, ops: Iterable[GraphOp]) -> None:
        ...

    def iter_ops(self, workspace_id: str) -> Iterable[GraphOp]:
        ...
