"""
Lineage and provenance helpers.
"""
from __future__ import annotations

from typing import Iterable

from ..graphops.op_log_types import LineageEntry


class GraphLineageService:
    def __init__(self, entries: Iterable[LineageEntry]) -> None:
        self.entries = list(entries)

    def history(self, node_id: str):
        return [entry for entry in self.entries if entry.op_payload.get("node_id") == node_id]
