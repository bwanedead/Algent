"""
Reducer that applies graph ops to snapshots.
"""
from __future__ import annotations

from typing import Iterable

from ..core.errors import GraphInvariantError, VersionMismatchError
from ..core.invariants import verify_snapshot
from ..core.primitives.edge import Edge
from ..core.primitives.layout import Layout
from ..core.primitives.node import Node
from ..core.primitives.snapshot import Snapshot
from .op_types import CreateEdge, CreateNode, GraphOp, SetLayout, SetNodeProps


def apply_ops(snapshot: Snapshot, ops: Iterable[GraphOp]) -> Snapshot:
    working_snapshot = snapshot.clone()
    for op in ops:
        if op.expected_version != working_snapshot.graph_version:
            raise VersionMismatchError(op.expected_version, working_snapshot.graph_version)
        _apply_single_op(working_snapshot, op)
        working_snapshot.graph_version += 1
    errors = verify_snapshot(working_snapshot)
    if errors:
        raise GraphInvariantError("; ".join(errors))
    return working_snapshot


def _apply_single_op(snapshot: Snapshot, op: GraphOp) -> None:
    if isinstance(op, CreateNode):
        _apply_create_node(snapshot, op)
    elif isinstance(op, SetNodeProps):
        _apply_set_node_props(snapshot, op)
    elif isinstance(op, CreateEdge):
        _apply_create_edge(snapshot, op)
    elif isinstance(op, SetLayout):
        _apply_set_layout(snapshot, op)
    else:  # pragma: no cover - defensive path for future ops
        raise GraphInvariantError(f"unhandled op type '{op.op_type}'")


def _apply_create_node(snapshot: Snapshot, op: CreateNode) -> None:
    node_key = op.node_id.value
    if node_key in snapshot.nodes:
        raise GraphInvariantError(f"node {node_key} already exists")
    snapshot.nodes[node_key] = Node(
        node_id=op.node_id,
        kind=op.kind,
        props=dict(op.props),
        created_at=op.timestamp,
        updated_at=op.timestamp,
    )


def _apply_set_node_props(snapshot: Snapshot, op: SetNodeProps) -> None:
    node_key = op.node_id.value
    node = snapshot.nodes.get(node_key)
    if not node:
        raise GraphInvariantError(f"cannot set props for missing node {node_key}")
    node.props.update(op.props)
    node.updated_at = op.timestamp


def _apply_create_edge(snapshot: Snapshot, op: CreateEdge) -> None:
    src_key = op.src.value
    dst_key = op.dst.value
    if src_key not in snapshot.nodes:
        raise GraphInvariantError(f"edge source {src_key} missing")
    if dst_key not in snapshot.nodes:
        raise GraphInvariantError(f"edge destination {dst_key} missing")
    edge_key = op.edge_id.value
    if edge_key in snapshot.edges:
        raise GraphInvariantError(f"edge {edge_key} already exists")
    snapshot.edges[edge_key] = Edge(
        edge_id=op.edge_id,
        edge_type=op.edge_type,
        src=op.src,
        dst=op.dst,
        props=dict(op.props),
        created_at=op.timestamp,
        updated_at=op.timestamp,
    )


def _apply_set_layout(snapshot: Snapshot, op: SetLayout) -> None:
    node_key = op.node_id.value
    if node_key not in snapshot.nodes:
        raise GraphInvariantError(f"cannot set layout for missing node {node_key}")
    existing_layout = snapshot.layouts.get(node_key)
    created_at = existing_layout.created_at if existing_layout else op.timestamp
    snapshot.layouts[node_key] = Layout(
        node_id=op.node_id,
        x=op.x,
        y=op.y,
        width=op.width,
        height=op.height,
        group_id=op.group_id,
        parent_workspace_id=op.parent_workspace_id,
        created_at=created_at,
        updated_at=op.timestamp,
    )
