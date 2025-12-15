"""
Lineage entry definitions for GraphOps log.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..core.ids import WorkspaceId, OpId


@dataclass
class LineageEntry:
    workspace_id: WorkspaceId
    op_id: OpId
    op_payload: dict
    created_at: datetime
