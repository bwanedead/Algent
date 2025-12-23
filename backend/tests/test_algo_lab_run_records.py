from __future__ import annotations

from pathlib import Path

from algent_backend.graph_os.core.ids import WorkspaceId
from algent_backend.graph_os.integration.labs.algo_lab_run_records import (
    build_run_record_ops_from_snapshot,
)
from algent_backend.graph_os.persistence.filesystem.commit_ledger_store import (
    CommitLedgerStore,
)
from algent_backend.graph_os.services.graph_os_service import GraphOSService
from algent_backend.labs.algo_lab.datasets import SequenceSpec
from algent_backend.labs.algo_lab.experiments import (
    SortingExperimentConfig,
    run_experiment,
)
from algent_backend.labs.algo_lab.run_protocols import canonical_json


def test_canonical_json_is_stable() -> None:
    payload_a = {"b": 2, "a": 1}
    payload_b = {"a": 1, "b": 2}
    assert canonical_json(payload_a) == canonical_json(payload_b)


def test_run_record_commit_and_replay(tmp_path: Path) -> None:
    store = CommitLedgerStore(tmp_path)
    service = GraphOSService(store)
    workspace = WorkspaceId.new().value
    cfg = SortingExperimentConfig(
        name="unit-run-record",
        algorithm="bubble_sort",
        dataset=SequenceSpec(size=8, seed=3),
    )
    result = run_experiment(cfg)
    snapshot = service.get_snapshot(workspace)
    ops = build_run_record_ops_from_snapshot(
        snapshot,
        result,
        actor="tester",
    )
    committed_snapshot = service.commit_ops(workspace, ops, actor="tester")
    reloaded_snapshot = service.get_snapshot(workspace)

    assert committed_snapshot == reloaded_snapshot
    run_nodes = [
        node
        for node in committed_snapshot.nodes.values()
        if node.kind == "lab.algo.run"
    ]
    assert len(run_nodes) == 1
    artifact_nodes = [
        node
        for node in committed_snapshot.nodes.values()
        if node.kind == "lab.algo.artifact.metrics_timeseries"
    ]
    assert artifact_nodes
    edge_types = {edge.edge_type for edge in committed_snapshot.edges.values()}
    assert "has_run" in edge_types
    assert "produces" in edge_types
