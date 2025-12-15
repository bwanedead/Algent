"""
Workspace state tracking.
"""
from __future__ import annotations

from enum import Enum


class WorkspaceState(Enum):
    ACTIVE = "active"
    LOCKED = "locked"
    MIGRATING = "migrating"
