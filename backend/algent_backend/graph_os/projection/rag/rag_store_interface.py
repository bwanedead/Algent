"""
Interface for RAG stores.
"""
from __future__ import annotations

from typing import Protocol, List, Tuple


class RagStore(Protocol):
    def add(self, doc_id: str, text: str) -> None:
        ...

    def search(self, query: str, limit: int = 5) -> List[Tuple[str, float]]:
        ...
