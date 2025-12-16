from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from algent_backend.graph_os.core.errors import VersionMismatchError
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
from algent_backend.graph_os.persistence.filesystem.jsonl_oplog_store import JsonlOpLogStore
from algent_backend.graph_os.services.graph_os_service import GraphOSService


BASE_TS = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _ts(offset_seconds: int) -> datetime:
    return BASE_TS + timedelta(seconds=offset_seconds)


def _seed_ops() -> tuple[list[GraphOp], NodeId, NodeId]:
    run_node = NodeId.new()
    chart_node = NodeId.new()
    edge = EdgeId.new()
    ops: list[GraphOp] = [
        CreateNode(
            op_id=OpId.new(),
            actor="tester",
            expected_version=0,
            timestamp=_ts(0),
            node_id=run_node,
            kind="lab.run",
            props={"status": "running"},
        ),
        CreateNode(
            op_id=OpId.new(),
            actor="tester",
            expected_version=1,
            timestamp=_ts(1),
            node_id=chart_node,
            kind="artifact.chart",
            props={"title": "Accuracy"},
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
            props={"confidence": 0.74},
        ),
        SetNodeProps(
            op_id=OpId.new(),
            actor="tester",
            expected_version=3,
            timestamp=_ts(3),
            node_id=run_node,
            props={"status": "completed"},
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
    assert run.props["status"] == "completed"
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
        kind="lab.run",
        props={},
    )

    with pytest.raises(VersionMismatchError):
        apply_ops(snapshot, [op])


def test_jsonl_oplog_store_replays_deterministically(tmp_path: Path) -> None:
    store = JsonlOpLogStore(tmp_path)
    workspace = WorkspaceId.new().value
    ops, *_ = _seed_ops()

    store.append_ops(workspace, ops)

    reread_ops = store.iter_ops(workspace)
    assert reread_ops == ops

    replayed_snapshot = store.load_snapshot(workspace)
    replay_again = apply_ops(Snapshot.empty(WorkspaceId.from_str(workspace)), reread_ops)
    assert replayed_snapshot == replay_again


def test_verify_snapshot_flags_orphan_layout() -> None:
    workspace = WorkspaceId.new()
    snapshot = Snapshot.empty(workspace)
    layout = Layout(node_id=NodeId.new(), x=0, y=0, width=100, height=100)
    snapshot.layouts[layout.node_id.value] = layout

    errors = verify_snapshot(snapshot)

    assert errors
    assert any("layout" in error for error in errors)


def test_graph_os_service_commits_through_log(tmp_path: Path) -> None:
    store = JsonlOpLogStore(tmp_path)
    service = GraphOSService(store)
    workspace = WorkspaceId.new().value
    ops, *_ = _seed_ops()

    committed_snapshot = service.commit_ops(workspace, ops)
    reloaded_snapshot = service.get_snapshot(workspace)

    assert committed_snapshot == reloaded_snapshot
    assert committed_snapshot.graph_version == len(ops)
