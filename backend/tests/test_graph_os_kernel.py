from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from algent_backend.graph_os.core.errors import (
    CommitIntegrityError,
    GraphInvariantError,
    VersionMismatchError,
)
from algent_backend.graph_os.core.ids import EdgeId, NodeId, OpId, WorkspaceId
from algent_backend.graph_os.core.invariants import verify_snapshot
from algent_backend.graph_os.core.primitives.layout import Layout
from algent_backend.graph_os.core.primitives.snapshot import Snapshot
from algent_backend.graph_os.graphops.op_apply import apply_ops
from algent_backend.graph_os.graphops.op_types import (
    CreateEdge,
    CreateNode,
    GraphOp,
    SetLayout,
    SetNodeProps,
)
from algent_backend.labs.algo_lab.run_protocols import canonical_json
from algent_backend.graph_os.integration.agent_tools.graph_os_tools import (
    apply_graph_ops_tool,
)
from algent_backend.graph_os.persistence.filesystem.commit_ledger_store import (
    CommitLedgerStore,
)
from algent_backend.graph_os.services.graph_os_service import GraphOSService


BASE_TS = datetime(2025, 1, 1, tzinfo=timezone.utc)
ACTOR = "tester"


def _ts(offset_seconds: int) -> datetime:
    return BASE_TS + timedelta(seconds=offset_seconds)


def _commits_dir(root: Path, workspace_id: str) -> Path:
    normalized = WorkspaceId.from_str(workspace_id).value
    return root / "workspaces" / normalized / "commits"


def _seed_ops() -> tuple[list[GraphOp], NodeId, NodeId]:
    run_node = NodeId.new()
    chart_node = NodeId.new()
    edge = EdgeId.new()
    params_json = canonical_json({"algorithm": "bubble_sort", "seed": 7})
    metric_json = canonical_json({"points": [{"index": 0, "value": 1}]})
    ops: list[GraphOp] = [
        CreateNode(
            op_id=OpId.new(),
            actor="tester",
            expected_version=0,
            timestamp=_ts(0),
            node_id=run_node,
            kind="lab.algo.run",
            props={
                "title": "bubble_sort seed=7",
                "algo_name": "bubble_sort",
                "params": params_json,
                "seed": 7,
                "status": "success",
                "started_at_utc": _ts(0).isoformat().replace("+00:00", "Z"),
                "ended_at_utc": _ts(1).isoformat().replace("+00:00", "Z"),
            },
        ),
        CreateNode(
            op_id=OpId.new(),
            actor="tester",
            expected_version=1,
            timestamp=_ts(1),
            node_id=chart_node,
            kind="lab.algo.artifact.metrics_timeseries",
            props={
                "title": "accuracy series",
                "metric_name": "accuracy",
                "data": metric_json,
                "derived": True,
                "source_run_id": run_node.value,
            },
        ),
        CreateEdge(
            op_id=OpId.new(),
            actor="tester",
            expected_version=2,
            timestamp=_ts(2),
            edge_id=edge,
            edge_type="produces",
            src=run_node,
            dst=chart_node,
            props={},
        ),
        SetNodeProps(
            op_id=OpId.new(),
            actor="tester",
            expected_version=3,
            timestamp=_ts(3),
            node_id=run_node,
            props={"status": "success"},
        ),
        SetLayout(
            op_id=OpId.new(),
            actor="tester",
            expected_version=4,
            timestamp=_ts(4),
            node_id=run_node,
            x=10,
            y=20,
            width=320,
            height=200,
        ),
    ]
    return ops, run_node, chart_node


def test_apply_ops_builds_snapshot() -> None:
    workspace = WorkspaceId.new()
    snapshot = Snapshot.empty(workspace)
    ops, run_node, chart_node = _seed_ops()

    result = apply_ops(snapshot, ops)

    assert result.graph_version == len(ops)
    assert run_node.value in result.nodes
    assert chart_node.value in result.nodes
    assert len(result.edges) == 1
    run = result.nodes[run_node.value]
    assert run.props["status"] == "success"
    assert run.updated_at == _ts(3)
    assert run_node.value in result.layouts


def test_apply_ops_requires_sequential_versions() -> None:
    workspace = WorkspaceId.new()
    snapshot = Snapshot.empty(workspace)
    op = CreateNode(
        op_id=OpId.new(),
        actor="tester",
        expected_version=1,  # snapshot starts at version 0
        timestamp=_ts(0),
        node_id=NodeId.new(),
        kind="lab.algo.run",
        props={
            "title": "bubble_sort seed=0",
            "algo_name": "bubble_sort",
            "params": canonical_json({"algorithm": "bubble_sort", "seed": 0}),
            "seed": 0,
            "status": "success",
            "started_at_utc": _ts(0).isoformat().replace("+00:00", "Z"),
            "ended_at_utc": _ts(0).isoformat().replace("+00:00", "Z"),
        },
    )

    with pytest.raises(VersionMismatchError):
        apply_ops(snapshot, [op])


def test_verify_snapshot_flags_orphan_layout() -> None:
    workspace = WorkspaceId.new()
    snapshot = Snapshot.empty(workspace)
    layout = Layout(node_id=NodeId.new(), x=0, y=0, width=100, height=100)
    snapshot.layouts[layout.node_id.value] = layout

    errors = verify_snapshot(snapshot)

    assert errors
    assert any("layout" in error for error in errors)


def test_graph_os_service_commits_through_log(tmp_path: Path) -> None:
    store = CommitLedgerStore(tmp_path)
    service = GraphOSService(store)
    workspace = WorkspaceId.new().value
    ops, *_ = _seed_ops()

    committed_snapshot = service.commit_ops(workspace, ops, actor=ACTOR)
    reloaded_snapshot = service.get_snapshot(workspace)

    assert committed_snapshot == reloaded_snapshot
    assert committed_snapshot.graph_version == len(ops)


def test_commit_ledger_replay_is_deterministic(tmp_path: Path) -> None:
    store = CommitLedgerStore(tmp_path)
    service = GraphOSService(store)
    workspace = WorkspaceId.new().value
    ops, *_ = _seed_ops()

    service.commit_ops(workspace, ops, actor=ACTOR)

    state_one = store.load_state(workspace)
    state_two = store.load_state(workspace)
    assert state_one.snapshot == state_two.snapshot
    assert state_one.head_hash == state_two.head_hash


def test_tmp_commit_files_are_ignored(tmp_path: Path) -> None:
    store = CommitLedgerStore(tmp_path)
    workspace = WorkspaceId.new().value
    commits_dir = _commits_dir(tmp_path, workspace)
    commits_dir.mkdir(parents=True, exist_ok=True)
    tmp_file = commits_dir / ".tmp_fake.json"
    tmp_file.write_text("partial", encoding="utf-8")

    state = store.load_state(workspace)

    assert state.snapshot.graph_version == 0
    assert state.next_seq == 1


def test_hash_tamper_detection(tmp_path: Path) -> None:
    store = CommitLedgerStore(tmp_path)
    service = GraphOSService(store)
    workspace = WorkspaceId.new().value
    ops, *_ = _seed_ops()

    service.commit_ops(workspace, ops, actor=ACTOR)
    commits_dir = _commits_dir(tmp_path, workspace)
    commit_file = commits_dir / "00000001.json"
    payload = json.loads(commit_file.read_text(encoding="utf-8"))
    payload["actor"] = "intruder"
    commit_file.write_text(json.dumps(payload, separators=(",", ":"), sort_keys=True), encoding="utf-8")

    with pytest.raises(CommitIntegrityError):
        store.load_state(workspace)


def test_duplicate_op_id_rejected_across_commits(tmp_path: Path) -> None:
    store = CommitLedgerStore(tmp_path)
    service = GraphOSService(store)
    workspace = WorkspaceId.new().value
    ops, run_node, _ = _seed_ops()
    service.commit_ops(workspace, ops, actor=ACTOR)
    duplicate_op = SetNodeProps(
        op_id=ops[0].op_id,
        actor=ACTOR,
        expected_version=len(ops),
        timestamp=_ts(10),
        node_id=run_node,
        props={"status": "again"},
    )

    with pytest.raises(GraphInvariantError):
        service.commit_ops(workspace, [duplicate_op], actor=ACTOR)


def test_commit_sequence_gap_detected(tmp_path: Path) -> None:
    store = CommitLedgerStore(tmp_path)
    service = GraphOSService(store)
    workspace = WorkspaceId.new().value
    ops, *_ = _seed_ops()

    service.commit_ops(workspace, ops, actor=ACTOR)
    commits_dir = _commits_dir(tmp_path, workspace)
    good_file = commits_dir / "00000001.json"
    renamed = commits_dir / "00000002.json"
    good_file.rename(renamed)

    with pytest.raises(CommitIntegrityError):
        store.load_state(workspace)


def test_apply_graph_ops_tool_uses_service_commit(tmp_path: Path) -> None:
    store = CommitLedgerStore(tmp_path)
    service = GraphOSService(store)
    workspace = WorkspaceId.new().value
    ops, *_ = _seed_ops()

    result = apply_graph_ops_tool(service, workspace, ACTOR, ops)

    assert result["graph_version"] == len(ops)
    commits_dir = _commits_dir(tmp_path, workspace)
    assert (commits_dir / "00000001.json").exists()
