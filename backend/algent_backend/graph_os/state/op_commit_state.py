"""
Operation commit lifecycle states.
"""
from __future__ import annotations

from enum import Enum


class OpCommitState(Enum):
    APPLYING = "applying"
    COMMITTED = "committed"
    FAILED = "failed"
