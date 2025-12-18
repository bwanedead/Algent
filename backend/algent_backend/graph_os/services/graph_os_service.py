"""
GraphOS service entry point for workspace operations.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List, Sequence

from ..core.commit import build_commit
from ..core.errors import GraphInvariantError
from ..core.primitives.snapshot import Snapshot
from ..graphops.op_apply import apply_ops
from ..graphops.op_types import GraphOp
from ..graphops.op_validate import validate_ops
from ..persistence.store_interface import WorkspaceLedgerState, WorkspaceStore


class GraphOSService:
    def __init__(self, store: WorkspaceStore) -> None:
        self.store = store

    def get_snapshot(self, workspace_id: str) -> Snapshot:
        return self.store.load_state(workspace_id).snapshot

    def dry_run_ops(self, workspace_id: str, ops: Iterable[GraphOp]) -> Snapshot:
        state = self.store.load_state(workspace_id)
        op_list = self._prepare_ops(ops, state.seen_op_ids)
        return apply_ops(state.snapshot, op_list)

    def commit_ops(
        self,
        workspace_id: str,
        ops: Iterable[GraphOp],
        *,
        actor: str,
        message: str | None = None,
        tags: Sequence[str] | None = None,
    ) -> Snapshot:
        with self.store.workspace_lock(workspace_id):
            state = self.store.load_state(workspace_id)
            op_list = self._prepare_ops(ops, state.seen_op_ids)
            next_snapshot = apply_ops(state.snapshot, op_list)
            commit = build_commit(
                workspace_id=state.workspace_id,
                seq=state.next_seq,
                base_version=state.snapshot.graph_version,
                actor=actor,
                ops=op_list,
                timestamp=datetime.now(timezone.utc),
                prev_commit_hash=state.head_hash,
                message=message,
                tags=tags,
            )
            self.store.append_commit(commit)
            return next_snapshot

    def _prepare_ops(self, ops: Iterable[GraphOp], seen_op_ids: set[str]) -> List[GraphOp]:
        op_list = list(ops)
        errors = validate_ops(op_list)
        duplicates = sorted({op.op_id.value for op in op_list if op.op_id.value in seen_op_ids})
        if duplicates:
            errors.append(f"duplicate op ids already committed: {', '.join(duplicates)}")
        if errors:
            raise GraphInvariantError("; ".join(errors))
        return op_list
