"""
Core invariants for snapshots and graph operations.
"""
from __future__ import annotations

from typing import List

from .primitives.snapshot import Snapshot


def verify_snapshot(snapshot: Snapshot) -> List[str]:
    errors: List[str] = []
    node_ids = set(snapshot.nodes.keys())

    if len(node_ids) != len(snapshot.nodes):
        errors.append("duplicate node identifiers detected")

    if snapshot.graph_version < 0:
        errors.append("graph version cannot be negative")

    for node_id, node in snapshot.nodes.items():
        if node.node_id.value != node_id:
            errors.append(f"node key mismatch for {node_id}")

    for edge_id, edge in snapshot.edges.items():
        if edge.src.value not in node_ids:
            errors.append(f"edge {edge_id} missing src node {edge.src}")
        if edge.dst.value not in node_ids:
            errors.append(f"edge {edge_id} missing dst node {edge.dst}")
        if edge.edge_id.value != edge_id:
            errors.append(f"edge key mismatch for {edge_id}")

    for layout_node_id, layout in snapshot.layouts.items():
        if layout.node_id.value not in node_ids:
            errors.append(f"layout for unknown node {layout_node_id}")
        if layout.node_id.value != layout_node_id:
            errors.append(f"layout key mismatch for {layout_node_id}")

    return errors
