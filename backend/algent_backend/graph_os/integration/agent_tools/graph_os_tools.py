"""
Agent tool shims for GraphOS operations.
"""
from __future__ import annotations

from typing import Iterable, Sequence

from ...graphops.op_types import GraphOp
from ...services.graph_os_service import GraphOSService


def apply_graph_ops_tool(
    service: GraphOSService,
    workspace_id: str,
    actor: str,
    ops: Iterable[GraphOp],
    *,
    dry_run: bool = False,
    message: str | None = None,
    tags: Sequence[str] | None = None,
) -> dict:
    if dry_run:
        snapshot = service.dry_run_ops(workspace_id, ops)
    else:
        snapshot = service.commit_ops(
            workspace_id,
            ops,
            actor=actor,
            message=message,
            tags=tags,
        )
    return {"status": "ok", "graph_version": snapshot.graph_version}
