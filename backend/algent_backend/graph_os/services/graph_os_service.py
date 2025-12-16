"""
GraphOS service entry point for workspace operations.
"""
from __future__ import annotations

from typing import Iterable, List

from ..core.errors import GraphInvariantError
from ..core.primitives.snapshot import Snapshot
from ..graphops.op_apply import apply_ops
from ..graphops.op_types import GraphOp
from ..graphops.op_validate import validate_ops
from ..persistence.store_interface import WorkspaceStore


class GraphOSService:
    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store

    def get_snapshot(self, workspace_id: str) -> Snapshot:
        return self.store.load_snapshot(workspace_id)

    def dry_run_ops(self, workspace_id: str, ops: Iterable[GraphOp]) -> Snapshot:
        op_list = self._prepare_ops(ops)
        snapshot = self.get_snapshot(workspace_id)
        return apply_ops(snapshot, op_list)

    def commit_ops(self, workspace_id: str, ops: Iterable[GraphOp]) -> Snapshot:
        op_list = self._prepare_ops(ops)
        next_snapshot = apply_ops(self.get_snapshot(workspace_id), op_list)
        self.store.append_ops(workspace_id, op_list)
        return next_snapshot

    def _prepare_ops(self, ops: Iterable[GraphOp]) -> List[GraphOp]:
        op_list = list(ops)
        errors = validate_ops(op_list)
        if errors:
            raise GraphInvariantError("; ".join(errors))
        return op_list
