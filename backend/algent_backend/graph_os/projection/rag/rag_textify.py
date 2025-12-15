"""
Text rendering helpers for RAG.
"""
from __future__ import annotations

from ..core.primitives.snapshot import Snapshot


def node_to_text(snapshot: Snapshot, node_id: str) -> str:
    node = snapshot.nodes.get(node_id)
    if not node:
        return ""
    return f"{node.kind}: {node.props}"
