"""
Alias maintained for backwards compatibility with old store import paths.
"""
from __future__ import annotations

from pathlib import Path

from .commit_ledger_store import CommitLedgerStore


class JsonlOpLogStore(CommitLedgerStore):
    def __init__(self, root_path: Path) -> None:  # pragma: no cover - shim
        super().__init__(root_path)
