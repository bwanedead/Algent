"""
Structured graph query helpers.
"""
from __future__ import annotations

from ..core.primitives.snapshot import Snapshot


class GraphQueryService:
    def __init__(self, snapshot: Snapshot) -> None:
        self.snapshot = snapshot

    def nodes_by_kind(self, kind: str):
        return [node for node in self.snapshot.nodes.values() if node.kind == kind]
