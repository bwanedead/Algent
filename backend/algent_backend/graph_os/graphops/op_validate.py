"""
Validation helpers for graph operations.
"""
from __future__ import annotations

from typing import List

from .op_types import GraphOp


def validate_ops(ops: list[GraphOp]) -> List[str]:
    errors: List[str] = []
    seen_ids = set()
    for op in ops:
        if op.op_id in seen_ids:
            errors.append(f"duplicate op id {op.op_id}")
        seen_ids.add(op.op_id)
    return errors
