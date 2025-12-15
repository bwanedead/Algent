"""
SQLite-backed workspace store.
"""
from __future__ import annotations

import sqlite3
from typing import Iterable

from ...core.primitives.snapshot import Snapshot
from ...graphops.op_types import GraphOp


class SQLiteWorkspaceStore:
    def __init__(self, path: str) -> None:
        self.path = path
        self._ensure_db()

    def _ensure_db(self) -> None:
        conn = sqlite3.connect(self.path)
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS ops (workspace_id TEXT, op BLOB)")
        finally:
            conn.close()

    def load_snapshot(self, workspace_id: str) -> Snapshot:
        raise NotImplementedError

    def append_ops(self, workspace_id: str, ops: Iterable[GraphOp]) -> None:
        conn = sqlite3.connect(self.path)
        try:
            conn.executemany(
                "INSERT INTO ops(workspace_id, op) VALUES (?, ?)",
                [(workspace_id, b"") for _ in ops],
            )
            conn.commit()
        finally:
            conn.close()

    def iter_ops(self, workspace_id: str) -> Iterable[GraphOp]:
        return []
