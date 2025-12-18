"""
SQLite-backed workspace store.
"""
from __future__ import annotations

import sqlite3
from contextlib import nullcontext

from ...core.commit import Commit
from ...persistence.store_interface import WorkspaceLedgerState, WorkspaceStore


class SQLiteWorkspaceStore(WorkspaceStore):
    def __init__(self, path: str) -> None:
        self.path = path
        self._ensure_db()

    def _ensure_db(self) -> None:
        conn = sqlite3.connect(self.path)
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS ops (workspace_id TEXT, op BLOB)")
        finally:
            conn.close()

    def load_state(self, workspace_id: str) -> WorkspaceLedgerState:
        raise NotImplementedError

    def append_commit(self, commit: Commit) -> None:
        raise NotImplementedError

    def workspace_lock(self, workspace_id: str):
        return nullcontext()
