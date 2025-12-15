"""
Typed identifiers for GraphOS entities.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4


@dataclass(frozen=True)
class WorkspaceId:
    value: UUID

    @staticmethod
    def new() -> "WorkspaceId":
        return WorkspaceId(uuid4())


@dataclass(frozen=True)
class NodeId:
    value: UUID

    @staticmethod
    def new() -> "NodeId":
        return NodeId(uuid4())


@dataclass(frozen=True)
class EdgeId:
    value: UUID

    @staticmethod
    def new() -> "EdgeId":
        return EdgeId(uuid4())


@dataclass(frozen=True)
class OpId:
    value: UUID

    @staticmethod
    def new() -> "OpId":
        return OpId(uuid4())
