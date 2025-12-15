"""
Checkpoint helpers for snapshots.
"""
from __future__ import annotations

from ..core.primitives.snapshot import Snapshot


def create_checkpoint(snapshot: Snapshot) -> dict:
    return {
        "workspace_id": snapshot.workspace_id.value.hex,
        "nodes": list(snapshot.nodes.keys()),
        "edges": list(snapshot.edges.keys()),
    }
