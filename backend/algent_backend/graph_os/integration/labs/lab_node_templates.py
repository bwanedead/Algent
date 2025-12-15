"""
Lab templates to map manifests into graph nodes.
"""
from __future__ import annotations

from typing import Dict, Any


def build_lab_node_template(lab_manifest: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "kind": lab_manifest.get("node_kind", "lab.generic"),
        "defaults": lab_manifest.get("defaults", {}),
    }
