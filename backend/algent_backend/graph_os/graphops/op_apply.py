"""
Reducer that applies graph ops to snapshots.
"""
from __future__ import annotations

from typing import Iterable

from ..core.primitives.snapshot import Snapshot
from ..core.primitives.node import Node
from ..core.primitives.edge import Edge
from ..core.invariants import verify_snapshot
from ..core.errors import GraphInvariantError
from .op_types import GraphOp, CreateNode, SetNodeProps, ConnectEdge


def apply_ops(snapshot: Snapshot, ops: Iterable[GraphOp]) -> Snapshot:
    for op in ops:
        if isinstance(op, CreateNode):
            snapshot.nodes[op.node_id.value.hex] = Node(op.node_id, op.kind, op.props)
        elif isinstance(op, SetNodeProps):
            node = snapshot.nodes.get(op.node_id.value.hex)
            if node:
                node.props.update(op.props)
        elif isinstance(op, ConnectEdge):
            snapshot.edges[op.edge_id.value.hex] = Edge(op.edge_id, op.edge_type, op.src, op.dst, op.props)
    errors = verify_snapshot(snapshot)
    if errors:
        raise GraphInvariantError("; ".join(errors))
    return snapshot
