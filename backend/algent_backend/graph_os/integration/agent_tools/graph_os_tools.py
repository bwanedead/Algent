"""
Agent tool shims for GraphOS operations.
"""
from __future__ import annotations

from typing import Iterable

from ...services.graph_os_service import GraphOSService
from ...graphops.op_types import GraphOp


def apply_graph_ops_tool(service: GraphOSService, workspace_id: str, ops: Iterable[GraphOp]) -> dict:
    service.apply_ops(workspace_id, ops)
    return {"status": "ok"}
