"""
Export helpers for snapshots.
"""
from __future__ import annotations

import json

from ..core.primitives.snapshot import Snapshot


class GraphExportService:
    def export_json(self, snapshot: Snapshot) -> str:
        payload = {
            "workspace_id": snapshot.workspace_id.value,
            "node_count": len(snapshot.nodes),
            "edge_count": len(snapshot.edges),
            "graph_version": snapshot.graph_version,
        }
        return json.dumps(payload)
