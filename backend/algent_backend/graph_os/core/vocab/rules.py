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
    missing = [
        spec.name
        for spec in definition.required_props
        if spec.name not in node.props
    ]
    if missing:
        errors.append(
            f"node '{node.node_id.value}' missing required props: {', '.join(sorted(missing))}"
        )
    return errors


def validate_edge(
    edge: Edge,
    src_kind: str | None,
    dst_kind: str | None,
    vocab: VocabularyRegistry,
) -> List[str]:
    errors: List[str] = []
    definition = vocab.edge_types.get(edge.edge_type)
    if not definition:
        errors.append(f"unknown edge type '{edge.edge_type}'")
        return errors
    if src_kind is None or dst_kind is None:
        errors.append(
            f"edge '{edge.edge_id.value}' missing src/dst kinds for validation"
        )
        return errors
    if (
        definition.allowed_src_kinds
        and src_kind not in definition.allowed_src_kinds
    ):
        errors.append(
            f"edge '{edge.edge_id.value}' invalid src kind '{src_kind}' for '{edge.edge_type}'"
        )
    if (
        definition.allowed_dst_kinds
        and dst_kind not in definition.allowed_dst_kinds
    ):
        errors.append(
            f"edge '{edge.edge_id.value}' invalid dst kind '{dst_kind}' for '{edge.edge_type}'"
        )
    required_props = [
        spec.name for spec in definition.props if spec.required
    ]
    missing = [name for name in required_props if name not in edge.props]
    if missing:
        errors.append(
            f"edge '{edge.edge_id.value}' missing required props: {', '.join(sorted(missing))}"
        )
    return errors
