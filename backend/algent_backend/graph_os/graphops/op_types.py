"""
Graph operation definitions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from ..core.ids import NodeId, EdgeId, OpId


@dataclass
class GraphOp:
    op_id: OpId
    op_type: str


@dataclass
class CreateNode(GraphOp):
    node_id: NodeId
    kind: str
    props: Dict[str, Any]


@dataclass
class SetNodeProps(GraphOp):
    node_id: NodeId
    props: Dict[str, Any]


@dataclass
class ConnectEdge(GraphOp):
    edge_id: EdgeId
    edge_type: str
    src: NodeId
    dst: NodeId
    props: Dict[str, Any]
