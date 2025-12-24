from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from algent_backend.graph_os.core.errors import GraphInvariantError
from algent_backend.graph_os.core.ids import EdgeId, NodeId, OpId, WorkspaceId
from algent_backend.graph_os.graphops.op_types import CreateEdge, CreateNode
from algent_backend.graph_os.persistence.filesystem.commit_ledger_store import (
    CommitLedgerStore,
)
from algent_backend.graph_os.services.graph_os_service import GraphOSService
from algent_backend.labs.algo_lab.run_protocols import canonical_json


BASE_TS = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _run_props(seed: int = 0) -> dict:
    return {
        "title": f"bubble_sort seed={seed}",
        "algo_name": "bubble_sort",
        "params": canonical_json({"algorithm": "bubble_sort", "seed": seed}),
        "seed": seed,
        "status": "success",
        "started_at_utc": BASE_TS.isoformat().replace("+00:00", "Z"),
        "ended_at_utc": BASE_TS.isoformat().replace("+00:00", "Z"),
    }


def _metrics_props(run_id: str) -> dict:
    return {
        "title": "accuracy series",
        "metric_name": "accuracy",
        "data": canonical_json({"points": [{"index": 0, "value": 1}]}),
        "derived": True,
        "source_run_id": run_id,
    }


def test_unknown_node_kind_rejected(tmp_path: Path) -> None:
    store = CommitLedgerStore(tmp_path)
    service = GraphOSService(store)
    workspace = WorkspaceId.new().value
    op = CreateNode(
        op_id=OpId.new(),
        actor="tester",
        expected_version=0,
        timestamp=BASE_TS,
        node_id=NodeId.new(),
        kind="unknown.kind",
        props={"title": "bad"},
    )

    with pytest.raises(GraphInvariantError):
        service.commit_ops(workspace, [op], actor="tester")


def test_missing_required_props_rejected(tmp_path: Path) -> None:
    store = CommitLedgerStore(tmp_path)
    service = GraphOSService(store)
    workspace = WorkspaceId.new().value
    op = CreateNode(
        op_id=OpId.new(),
        actor="tester",
        expected_version=0,
        timestamp=BASE_TS,
        node_id=NodeId.new(),
        kind="lab.algo.run",
        props={"title": "missing fields"},
    )

    with pytest.raises(GraphInvariantError):
        service.commit_ops(workspace, [op], actor="tester")


def test_edge_kind_mismatch_rejected(tmp_path: Path) -> None:
    store = CommitLedgerStore(tmp_path)
    service = GraphOSService(store)
    workspace = WorkspaceId.new().value
    note_id = NodeId.new()
    artifact_id = NodeId.new()
    ops = [
        CreateNode(
            op_id=OpId.new(),
            actor="tester",
            expected_version=0,
            timestamp=BASE_TS,
            node_id=note_id,
            kind="note",
            props={"title": "note", "text": "test"},
        ),
        CreateNode(
            op_id=OpId.new(),
            actor="tester",
            expected_version=1,
            timestamp=BASE_TS,
            node_id=artifact_id,
            kind="lab.algo.artifact.metrics_timeseries",
            props=_metrics_props(note_id.value),
        ),
        CreateEdge(
            op_id=OpId.new(),
            actor="tester",
            expected_version=2,
            timestamp=BASE_TS,
            edge_id=EdgeId.new(),
            edge_type="produces",
            src=note_id,
            dst=artifact_id,
            props={},
        ),
    ]

    with pytest.raises(GraphInvariantError):
        service.commit_ops(workspace, ops, actor="tester")


def test_edge_validation_is_order_independent(tmp_path: Path) -> None:
    store = CommitLedgerStore(tmp_path)
    service = GraphOSService(store)
    workspace = WorkspaceId.new().value
    run_id = NodeId.new()
    artifact_id = NodeId.new()
    ops = [
        CreateEdge(
            op_id=OpId.new(),
            actor="tester",
            expected_version=0,
            timestamp=BASE_TS,
            edge_id=EdgeId.new(),
            edge_type="produces",
            src=run_id,
            dst=artifact_id,
            props={},
        ),
        CreateNode(
            op_id=OpId.new(),
            actor="tester",
            expected_version=1,
            timestamp=BASE_TS,
            node_id=run_id,
            kind="lab.algo.run",
            props=_run_props(),
        ),
        CreateNode(
            op_id=OpId.new(),
            actor="tester",
            expected_version=2,
            timestamp=BASE_TS,
            node_id=artifact_id,
            kind="lab.algo.artifact.metrics_timeseries",
            props=_metrics_props(run_id.value),
        ),
    ]

    snapshot = service.commit_ops(workspace, ops, actor="tester")
    assert snapshot.edges
