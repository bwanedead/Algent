"""
Persistence interfaces for GraphOS stores.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import ContextManager, Protocol, Set

from ..core.commit import Commit
from ..core.ids import WorkspaceId
from ..core.primitives.snapshot import Snapshot


@dataclass
class WorkspaceLedgerState:
    workspace_id: WorkspaceId
    snapshot: Snapshot
    next_seq: int
    head_hash: str | None
    seen_op_ids: Set[str]


class WorkspaceStore(Protocol):
    def load_state(self, workspace_id: str) -> WorkspaceLedgerState:
        ...

    def append_commit(self, commit: Commit) -> None:
        ...

    def workspace_lock(self, workspace_id: str) -> ContextManager[None]:
        ...
