"""
Export snapshots to RDF triples (placeholder).
"""
from __future__ import annotations

from ..core.primitives.snapshot import Snapshot


def export_rdf(snapshot: Snapshot) -> str:
    return f"rdf://workspace/{snapshot.workspace_id.value}"
