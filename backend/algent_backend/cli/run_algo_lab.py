"""
Minimal CLI to run an Algo Lab experiment and commit a run record.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from ..graph_os.core.ids import NodeId, WorkspaceId
from ..graph_os.integration.labs.algo_lab_run_records import (
    build_run_record_ops_from_snapshot,
)
from ..graph_os.persistence.filesystem.commit_ledger_store import CommitLedgerStore
from ..graph_os.services.graph_os_service import GraphOSService
from ..labs.algo_lab.service import AlgoLabService


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Algo Lab and commit a run record.")
    parser.add_argument("--workspace", help="Workspace id to append to.")
    parser.add_argument("--store-root", help="Root directory for GraphOS commit ledger.")
    parser.add_argument("--algorithm", default="bubble_sort", help="Sorting algorithm name.")
    parser.add_argument("--name", default="cli-run", help="Experiment name.")
    parser.add_argument("--seed", type=int, default=0, help="Dataset seed.")
    parser.add_argument("--size", type=int, default=32, help="Dataset size.")
    parser.add_argument("--actor", default="cli", help="Actor name for the commit.")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    workspace_id = args.workspace or WorkspaceId.new().value
    store_root = Path(args.store_root) if args.store_root else Path.cwd() / ".graphos"
    store = CommitLedgerStore(store_root)
    graph_service = GraphOSService(store)
    lab_service = AlgoLabService()

    payload = {
        "name": args.name,
        "algorithm": args.algorithm,
        "dataset": {
            "size": args.size,
            "seed": args.seed,
        },
    }
    result = lab_service.run_sorting(payload)
    snapshot = graph_service.get_snapshot(workspace_id)
    run_node_id = NodeId.new()
    ops = build_run_record_ops_from_snapshot(
        snapshot,
        result,
        actor=args.actor,
        run_node_id=run_node_id,
    )
    graph_service.commit_ops(workspace_id, ops, actor=args.actor)
    updated_snapshot = graph_service.get_snapshot(workspace_id)
    metric_nodes = [
        node
        for node in updated_snapshot.nodes.values()
        if node.kind == "lab.algo.artifact.metrics_timeseries"
        and node.props.get("source_run_id") == run_node_id.value
    ]

    print("Workspace:", workspace_id)
    print("Store root:", store_root)
    print("Graph version:", updated_snapshot.graph_version)
    print("Run node:", run_node_id.value)
    print("Metric artifacts:", [node.node_id.value for node in metric_nodes])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
