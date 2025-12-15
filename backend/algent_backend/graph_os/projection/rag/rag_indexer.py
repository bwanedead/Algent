"""
Index graph ops into retrieval stores.
"""
from __future__ import annotations

from typing import Iterable

from ...graphops.op_types import GraphOp


def index_ops(ops: Iterable[GraphOp]) -> None:
    for _ in ops:
        continue
