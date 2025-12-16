"""
Immutable snapshot of workspace state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from ..ids import WorkspaceId
from .edge import Edge
from .layout import Layout
from .node import Node


@dataclass
class Snapshot:
    workspace_id: WorkspaceId
    nodes: Dict[str, Node] = field(default_factory=dict)
    edges: Dict[str, Edge] = field(default_factory=dict)
    layouts: Dict[str, Layout] = field(default_factory=dict)
    vocab_version: str | None = None
    graph_version: int = 0

    @staticmethod
    def empty(workspace_id: WorkspaceId) -> "Snapshot":
        return Snapshot(workspace_id=workspace_id)

    def clone(self) -> "Snapshot":
        return Snapshot(
            workspace_id=self.workspace_id,
            nodes={node_id: node.clone() for node_id, node in self.nodes.items()},
            edges={edge_id: edge.clone() for edge_id, edge in self.edges.items()},
            layouts={node_id: layout.clone() for node_id, layout in self.layouts.items()},
            vocab_version=self.vocab_version,
            graph_version=self.graph_version,
        )
