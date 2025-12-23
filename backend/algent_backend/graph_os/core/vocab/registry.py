"""
Vocabulary registry keeps track of node and edge definitions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict

from .types import NodeKind, EdgeType


@dataclass
class VocabularyRegistry:
    version: str
    node_kinds: Dict[str, NodeKind] = field(default_factory=dict)
    edge_types: Dict[str, EdgeType] = field(default_factory=dict)

    def register_node_kind(self, node_kind: NodeKind) -> None:
        self.node_kinds[node_kind.name] = node_kind

    def register_edge_type(self, edge_type: EdgeType) -> None:
        self.edge_types[edge_type.name] = edge_type


_DEFAULT_REGISTRY = VocabularyRegistry(version="v0")
_DEFAULT_PACKS_LOADED = False


def _load_default_packs() -> None:
    global _DEFAULT_PACKS_LOADED
    if _DEFAULT_PACKS_LOADED:
        return
    from .packs import register_all

    register_all(_DEFAULT_REGISTRY)
    _DEFAULT_PACKS_LOADED = True


def get_registry() -> VocabularyRegistry:
    _load_default_packs()
    return _DEFAULT_REGISTRY
