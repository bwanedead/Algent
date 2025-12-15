"""
Core invariants for snapshots and graph operations.
"""
from __future__ import annotations

from typing import List

from .primitives.snapshot import Snapshot


def verify_snapshot(snapshot: Snapshot) -> List[str]:
    errors: List[str] = []
    node_ids = set(snapshot.nodes.keys())
    for edge_id, edge in snapshot.edges.items():
        if edge.src.value.hex not in node_ids:
            errors.append(f"edge {edge_id} missing src node")
        if edge.dst.value.hex not in node_ids:
            errors.append(f"edge {edge_id} missing dst node")
    return errors
