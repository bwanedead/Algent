"""
Validation helpers enforcing vocabulary rules.
"""
from __future__ import annotations

from typing import List

from ..primitives.edge import Edge
from ..primitives.node import Node
from .registry import VocabularyRegistry


def validate_node(node: Node, vocab: VocabularyRegistry) -> List[str]:
    errors: List[str] = []
    definition = vocab.node_kinds.get(node.kind)
    if not definition:
        errors.append(f"unknown node kind '{node.kind}'")
    return errors


def validate_edge(edge: Edge, vocab: VocabularyRegistry) -> List[str]:
    errors: List[str] = []
    definition = vocab.edge_types.get(edge.edge_type)
    if not definition:
        errors.append(f"unknown edge type '{edge.edge_type}'")
    return errors
