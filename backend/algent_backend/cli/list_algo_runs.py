"""
List Algo Lab run records from a workspace.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from ..graph_os.core.ids import WorkspaceId
from ..graph_os.persistence.filesystem.commit_ledger_store import CommitLedgerStore
from ..graph_os.services.graph_os_service import GraphOSService


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List Algo Lab runs in a workspace.")
    parser.add_argument("--workspace", required=True, help="Workspace id to inspect.")
    parser.add_argument("--store-root", help="Root directory for GraphOS commit ledger.")
    parser.add_argument("--limit", type=int, default=10, help="Number of runs to list.")
    return parser.parse_args()


def _parse_params(raw: str) -> Dict[str, Any]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def main() -> int:
    args = _parse_args()
    workspace_id = WorkspaceId.from_str(args.workspace).value
    store_root = Path(args.store_root) if args.store_root else Path.cwd() / ".graphos"
    store = CommitLedgerStore(store_root)
    graph_service = GraphOSService(store)
    snapshot = graph_service.get_snapshot(workspace_id)

    run_nodes = [
        node for node in snapshot.nodes.values() if node.kind == "lab.algo.run"
    ]
    run_nodes.sort(key=lambda node: node.created_at, reverse=True)
    run_nodes = run_nodes[: max(args.limit, 0)]

    print("Workspace:", workspace_id)
    print("Store root:", store_root)
    print("Graph version:", snapshot.graph_version)
    print("Runs:", len(run_nodes))

    for node in run_nodes:
        params = _parse_params(node.props.get("params", "{}"))
        dataset = params.get("dataset") or {}
        size = dataset.get("size")
        seed = dataset.get("seed")
        algo_name = node.props.get("algo_name")
        edges = [
            edge
            for edge in snapshot.edges.values()
            if edge.edge_type == "produces" and edge.src.value == node.node_id.value
        ]
        artifact_ids = [edge.dst.value for edge in edges]
        print("---")
        print("Run:", node.node_id.value)
        print("Title:", node.props.get("title"))
        print("Algorithm:", algo_name)
        print("Seed:", seed)
        print("Size:", size)
        print("Status:", node.props.get("status"))
        print("Artifacts:", artifact_ids)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
