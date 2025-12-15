"""
Graph node primitive.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict
from datetime import datetime

from ..ids import NodeId


@dataclass
class Node:
    node_id: NodeId
    kind: str
    props: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
