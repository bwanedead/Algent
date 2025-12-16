"""
Snapshot filesystem store.
"""
from __future__ import annotations

from pathlib import Path
import json

from ...core.primitives.snapshot import Snapshot


class SnapshotStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, snapshot: Snapshot) -> None:
        payload = {
            "workspace_id": snapshot.workspace_id.value,
            "node_count": len(snapshot.nodes),
            "edge_count": len(snapshot.edges),
            "graph_version": snapshot.graph_version,
        }
        self.path.write_text(json.dumps(payload), encoding="utf-8")
