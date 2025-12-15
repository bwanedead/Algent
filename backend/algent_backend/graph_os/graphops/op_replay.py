"""
Replay op logs into snapshots.
"""
from __future__ import annotations

from typing import Iterable

from ..core.primitives.snapshot import Snapshot
from .op_types import GraphOp
from .op_apply import apply_ops


def replay(snapshot: Snapshot, ops: Iterable[GraphOp]) -> Snapshot:
    return apply_ops(snapshot, ops)
