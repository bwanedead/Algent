"""
Graph edge primitive.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict

from ..ids import EdgeId, NodeId


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Edge:
    edge_id: EdgeId
    edge_type: str
    src: NodeId
    dst: NodeId
    props: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def clone(self) -> "Edge":
        return Edge(
            edge_id=self.edge_id,
            edge_type=self.edge_type,
            src=self.src,
            dst=self.dst,
            props=dict(self.props),
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
