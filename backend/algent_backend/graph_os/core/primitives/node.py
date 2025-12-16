"""
Graph node primitive.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict

from ..ids import NodeId


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Node:
    node_id: NodeId
    kind: str
    props: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def clone(self) -> "Node":
        return Node(
            node_id=self.node_id,
            kind=self.kind,
            props=dict(self.props),
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
