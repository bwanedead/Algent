"""
Checkpoint helpers for snapshots.
"""
from __future__ import annotations

from ..core.primitives.snapshot import Snapshot


def create_checkpoint(snapshot: Snapshot) -> dict:
    return {
        "workspace_id": snapshot.workspace_id.value,
        "nodes": list(snapshot.nodes.keys()),
        "edges": list(snapshot.edges.keys()),
        "graph_version": snapshot.graph_version,
    }
