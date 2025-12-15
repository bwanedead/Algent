"""
RDF mapping utilities.
"""
from __future__ import annotations

from typing import Dict

from ...core.vocab.types import NodeKind, EdgeType


def map_node_kind(kind: NodeKind) -> str:
    return f"https://algent.dev/graph/{kind.name}"


def map_edge_type(edge_type: EdgeType) -> str:
    return f"https://algent.dev/graph/{edge_type.name}"
