"""
Validation helpers for graph operations.
"""
from __future__ import annotations

from typing import Dict, List

from .op_types import GraphOp
from ..core.primitives.edge import Edge
from ..core.primitives.node import Node
from ..core.primitives.snapshot import Snapshot
from ..core.vocab.registry import VocabularyRegistry
from ..core.vocab.rules import validate_edge, validate_node
from ..graphops.op_types import CreateEdge, CreateNode


def validate_ops(
    ops: list[GraphOp],
    snapshot: Snapshot | None = None,
    vocab: VocabularyRegistry | None = None,
) -> List[str]:
    errors: List[str] = []
    seen_ids = set()
    node_kinds: Dict[str, str] = {}
    if snapshot is not None:
        node_kinds = {node_id: node.kind for node_id, node in snapshot.nodes.items()}
    for op in ops:
        if op.op_id.value in seen_ids:
            errors.append(f"duplicate op id {op.op_id.value}")
        seen_ids.add(op.op_id.value)
        if vocab is None:
            continue
        if isinstance(op, CreateNode):
            node = Node(
                node_id=op.node_id,
                kind=op.kind,
                props=dict(op.props),
                created_at=op.timestamp,
                updated_at=op.timestamp,
            )
            errors.extend(validate_node(node, vocab))
            node_kinds[op.node_id.value] = op.kind
        elif isinstance(op, CreateEdge):
            src_kind = node_kinds.get(op.src.value)
            dst_kind = node_kinds.get(op.dst.value)
            edge = Edge(
                edge_id=op.edge_id,
                edge_type=op.edge_type,
                src=op.src,
                dst=op.dst,
                props=dict(op.props),
                created_at=op.timestamp,
                updated_at=op.timestamp,
            )
            errors.extend(validate_edge(edge, src_kind, dst_kind, vocab))
    return errors
