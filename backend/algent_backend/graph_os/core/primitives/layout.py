"""
Layout metadata primitives.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..ids import NodeId


@dataclass
class Layout:
    node_id: NodeId
    x: float
    y: float
    width: float
    height: float
    group_id: Optional[str] = None
    parent_workspace_id: Optional[str] = None
