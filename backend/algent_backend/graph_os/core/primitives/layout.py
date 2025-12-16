"""
Layout metadata primitives.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from ..ids import NodeId


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Layout:
    node_id: NodeId
    x: float
    y: float
    width: float
    height: float
    group_id: Optional[str] = None
    parent_workspace_id: Optional[str] = None
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    def clone(self) -> "Layout":
        return Layout(
            node_id=self.node_id,
            x=self.x,
            y=self.y,
            width=self.width,
            height=self.height,
            group_id=self.group_id,
            parent_workspace_id=self.parent_workspace_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
