"""
Graph operation definitions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, Mapping, Type

from ..core.ids import EdgeId, NodeId, OpId


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


class GraphOpRegistry:
    def __init__(self) -> None:
        self._registry: Dict[str, Type[GraphOp]] = {}

    def register(self, op_cls: Type["GraphOp"]) -> Type["GraphOp"]:
        self._registry[op_cls.op_type] = op_cls
        return op_cls

    def resolve(self, op_type: str) -> Type["GraphOp"]:
        try:
            return self._registry[op_type]
        except KeyError as exc:  # pragma: no cover - defensively fail fast
            raise ValueError(f"unknown operation type '{op_type}'") from exc


REGISTRY = GraphOpRegistry()


@dataclass(frozen=True)
class GraphOp:
    op_id: OpId
    actor: str
    expected_version: int
    timestamp: datetime

    op_type: ClassVar[str] = "graph_op"

    def payload(self) -> Dict[str, Any]:
        return {}

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "op_id": self.op_id.value,
            "op_type": self.op_type,
            "actor": self.actor,
            "expected_version": self.expected_version,
            "timestamp": self.timestamp.isoformat(),
        }
        payload.update(self.payload())
        return payload

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphOp":
        raise NotImplementedError


@REGISTRY.register
@dataclass(frozen=True)
class CreateNode(GraphOp):
    node_id: NodeId
    kind: str
    props: Mapping[str, Any] = field(default_factory=dict)

    op_type: ClassVar[str] = "create_node"

    def payload(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id.value,
            "kind": self.kind,
            "props": dict(self.props),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CreateNode":
        return cls(
            op_id=OpId.from_str(data["op_id"]),
            actor=data["actor"],
            expected_version=int(data["expected_version"]),
            timestamp=_parse_timestamp(data["timestamp"]),
            node_id=NodeId.from_str(data["node_id"]),
            kind=data["kind"],
            props=dict(data.get("props", {})),
        )


@REGISTRY.register
@dataclass(frozen=True)
class SetNodeProps(GraphOp):
    node_id: NodeId
    props: Mapping[str, Any] = field(default_factory=dict)

    op_type: ClassVar[str] = "set_node_props"

    def payload(self) -> Dict[str, Any]:
        return {"node_id": self.node_id.value, "props": dict(self.props)}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SetNodeProps":
        return cls(
            op_id=OpId.from_str(data["op_id"]),
            actor=data["actor"],
            expected_version=int(data["expected_version"]),
            timestamp=_parse_timestamp(data["timestamp"]),
            node_id=NodeId.from_str(data["node_id"]),
            props=dict(data.get("props", {})),
        )


@REGISTRY.register
@dataclass(frozen=True)
class CreateEdge(GraphOp):
    edge_id: EdgeId
    edge_type: str
    src: NodeId
    dst: NodeId
    props: Mapping[str, Any] = field(default_factory=dict)

    op_type: ClassVar[str] = "create_edge"

    def payload(self) -> Dict[str, Any]:
        return {
            "edge_id": self.edge_id.value,
            "edge_type": self.edge_type,
            "src": self.src.value,
            "dst": self.dst.value,
            "props": dict(self.props),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CreateEdge":
        return cls(
            op_id=OpId.from_str(data["op_id"]),
            actor=data["actor"],
            expected_version=int(data["expected_version"]),
            timestamp=_parse_timestamp(data["timestamp"]),
            edge_id=EdgeId.from_str(data["edge_id"]),
            edge_type=data["edge_type"],
            src=NodeId.from_str(data["src"]),
            dst=NodeId.from_str(data["dst"]),
            props=dict(data.get("props", {})),
        )


@REGISTRY.register
@dataclass(frozen=True)
class SetLayout(GraphOp):
    node_id: NodeId
    x: float
    y: float
    width: float
    height: float
    group_id: str | None = None
    parent_workspace_id: str | None = None

    op_type: ClassVar[str] = "set_layout"

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", float(self.x))
        object.__setattr__(self, "y", float(self.y))
        object.__setattr__(self, "width", float(self.width))
        object.__setattr__(self, "height", float(self.height))

    def payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "node_id": self.node_id.value,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }
        if self.group_id:
            payload["group_id"] = self.group_id
        if self.parent_workspace_id:
            payload["parent_workspace_id"] = self.parent_workspace_id
        return payload

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SetLayout":
        return cls(
            op_id=OpId.from_str(data["op_id"]),
            actor=data["actor"],
            expected_version=int(data["expected_version"]),
            timestamp=_parse_timestamp(data["timestamp"]),
            node_id=NodeId.from_str(data["node_id"]),
            x=float(data["x"]),
            y=float(data["y"]),
            width=float(data["width"]),
            height=float(data["height"]),
            group_id=data.get("group_id"),
            parent_workspace_id=data.get("parent_workspace_id"),
        )


def serialize_op(op: GraphOp) -> Dict[str, Any]:
    return op.to_dict()


def deserialize_op(payload: Dict[str, Any]) -> GraphOp:
    op_cls = REGISTRY.resolve(payload["op_type"])
    return op_cls.from_dict(payload)
