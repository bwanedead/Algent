"""
Immutable snapshot of workspace state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from ..ids import WorkspaceId
from .node import Node
from .edge import Edge
from .layout import Layout


@dataclass
class Snapshot:
    workspace_id: WorkspaceId
    nodes: Dict[str, Node] = field(default_factory=dict)
    edges: Dict[str, Edge] = field(default_factory=dict)
    layouts: Dict[str, Layout] = field(default_factory=dict)
    vocab_version: str | None = None
