"""
SQLite FTS baseline store.
"""
from __future__ import annotations

from typing import List, Tuple


class SQLiteFtsStore:
    def add(self, doc_id: str, text: str) -> None:
        pass

    def search(self, query: str, limit: int = 5) -> List[Tuple[str, float]]:
        return []
