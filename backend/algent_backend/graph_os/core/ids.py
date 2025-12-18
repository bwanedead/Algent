"""
Typed identifiers for GraphOS entities.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4


def _normalize_uuid(value: str | UUID) -> str:
    if isinstance(value, UUID):
        return value.hex
    if not isinstance(value, str):
        raise TypeError("identifier values must be strings or UUID objects")
    candidate = value.replace("-", "").strip()
    if not candidate:
        raise ValueError("identifier value cannot be empty")
    try:
        return UUID(hex=candidate).hex
    except ValueError as exc:  # pragma: no cover - defensive path
        raise ValueError(f"invalid UUID value '{value}'") from exc


@dataclass(frozen=True)
class WorkspaceId:
    value: str

    @staticmethod
    def new() -> "WorkspaceId":
        return WorkspaceId(uuid4().hex)

    @staticmethod
    def from_str(value: str) -> "WorkspaceId":
        return WorkspaceId(_normalize_uuid(value))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class NodeId:
    value: str

    @staticmethod
    def new() -> "NodeId":
        return NodeId(uuid4().hex)

    @staticmethod
    def from_str(value: str) -> "NodeId":
        return NodeId(_normalize_uuid(value))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class EdgeId:
    value: str

    @staticmethod
    def new() -> "EdgeId":
        return EdgeId(uuid4().hex)

    @staticmethod
    def from_str(value: str) -> "EdgeId":
        return EdgeId(_normalize_uuid(value))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class OpId:
    value: str

    @staticmethod
    def new() -> "OpId":
        return OpId(uuid4().hex)

    @staticmethod
    def from_str(value: str) -> "OpId":
        return OpId(_normalize_uuid(value))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class CommitId:
    value: str

    @staticmethod
    def new() -> "CommitId":
        return CommitId(uuid4().hex)

    @staticmethod
    def from_str(value: str) -> "CommitId":
        return CommitId(_normalize_uuid(value))

    def __str__(self) -> str:
        return self.value
