"""
Vocabulary type definitions for node kinds and edge types.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class PropertySpec:
    name: str
    value_type: str
    description: str = ""
    required: bool = False


@dataclass
class NodeKind:
    name: str
    description: str
    required_props: List[PropertySpec] = field(default_factory=list)
    optional_props: List[PropertySpec] = field(default_factory=list)


@dataclass
class EdgeType:
    name: str
    description: str
    allowed_src_kinds: List[str]
    allowed_dst_kinds: List[str]
    props: List[PropertySpec] = field(default_factory=list)
