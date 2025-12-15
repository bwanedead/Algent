"""
Optimistic concurrency helpers.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VersionVector:
    workspace_version: int

    def bump(self) -> None:
        self.workspace_version += 1
