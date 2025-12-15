"""
GraphOS service entry point for workspace operations.
"""
from __future__ import annotations

from typing import Iterable

from ..core.primitives.snapshot import Snapshot
from ..graphops.op_types import GraphOp
from ..persistence.store_interface import WorkspaceStore


class GraphOSService:
    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store

    def get_snapshot(self, workspace_id: str) -> Snapshot:
        return self.store.load_snapshot(workspace_id)

    def apply_ops(self, workspace_id: str, ops: Iterable[GraphOp]) -> None:
        self.store.append_ops(workspace_id, ops)
