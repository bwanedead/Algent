"""
Graph edge primitive.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict
from datetime import datetime

from ..ids import EdgeId, NodeId


@dataclass
class Edge:
    edge_id: EdgeId
    edge_type: str
    src: NodeId
    dst: NodeId
    props: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
