"""
Adapter that turns Algo Lab runs into GraphOps bundles.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from ...core.ids import EdgeId, NodeId, OpId
from ...graphops.op_types import CreateEdge, CreateNode, GraphOp
from ...core.primitives.snapshot import Snapshot
from ....labs.algo_lab.experiments import ExperimentResult
from ....labs.algo_lab.run_protocols import AlgoRunResult
from ....labs.algo_lab.service import AlgoLabService
from ...services.graph_os_service import GraphOSService


def build_run_record_ops(
    result: ExperimentResult,
    *,
    actor: str,
    now_utc: datetime | None = None,
    base_version: int,
    algo_node_id: NodeId | None = None,
    experiment_node_id: NodeId | None = None,
    run_node_id: NodeId | None = None,
) -> List[GraphOp]:
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    run_record = AlgoRunResult.from_experiment_result(result, now_utc=now_utc)
    ops: List[GraphOp] = []
    expected_version = base_version

    def next_expected() -> int:
        nonlocal expected_version
        current = expected_version
        expected_version += 1
        return current

    if algo_node_id is None:
        algo_node_id = NodeId.new()
        ops.append(
            CreateNode(
                op_id=OpId.new(),
                actor=actor,
                expected_version=next_expected(),
                timestamp=now_utc,
                node_id=algo_node_id,
                kind="lab.algo",
                props={"title": "Algo Lab"},
            )
        )

    if experiment_node_id is None:
        experiment_node_id = NodeId.new()
        ops.append(
            CreateNode(
                op_id=OpId.new(),
                actor=actor,
                expected_version=next_expected(),
                timestamp=now_utc,
                node_id=experiment_node_id,
                kind="lab.algo.experiment",
                props=run_record.experiment.to_node_props(),
            )
        )
        ops.append(
            CreateEdge(
                op_id=OpId.new(),
                actor=actor,
                expected_version=next_expected(),
                timestamp=now_utc,
                edge_id=EdgeId.new(),
                edge_type="contains",
                src=algo_node_id,
                dst=experiment_node_id,
                props={},
            )
        )

    if run_node_id is None:
        run_node_id = NodeId.new()
        ops.append(
            CreateNode(
                op_id=OpId.new(),
                actor=actor,
                expected_version=next_expected(),
                timestamp=now_utc,
                node_id=run_node_id,
                kind="lab.algo.run",
                props=run_record.run.to_node_props(),
            )
        )
        ops.append(
            CreateEdge(
                op_id=OpId.new(),
                actor=actor,
                expected_version=next_expected(),
                timestamp=now_utc,
                edge_id=EdgeId.new(),
                edge_type="contains",
                src=algo_node_id,
                dst=run_node_id,
                props={},
            )
        )
        ops.append(
            CreateEdge(
                op_id=OpId.new(),
                actor=actor,
                expected_version=next_expected(),
                timestamp=now_utc,
                edge_id=EdgeId.new(),
                edge_type="has_run",
                src=experiment_node_id,
                dst=run_node_id,
                props={},
            )
        )

    for metric in run_record.metrics:
        metric_node_id = NodeId.new()
        props = {
            "title": f"{metric.metric_name} series",
            "metric_name": metric.metric_name,
            "data": metric.data_json(),
            "derived": True,
            "source_run_id": run_node_id.value,
        }
        if metric.units:
            props["units"] = metric.units
        ops.append(
            CreateNode(
                op_id=OpId.new(),
                actor=actor,
                expected_version=next_expected(),
                timestamp=now_utc,
                node_id=metric_node_id,
                kind="lab.algo.artifact.metrics_timeseries",
                props=props,
            )
        )
        ops.append(
            CreateEdge(
                op_id=OpId.new(),
                actor=actor,
                expected_version=next_expected(),
                timestamp=now_utc,
                edge_id=EdgeId.new(),
                edge_type="produces",
                src=run_node_id,
                dst=metric_node_id,
                props={},
            )
        )

    return ops


def build_run_record_ops_from_snapshot(
    snapshot: Snapshot,
    result: ExperimentResult,
    *,
    actor: str,
    now_utc: datetime | None = None,
    algo_node_id: NodeId | None = None,
    experiment_node_id: NodeId | None = None,
    run_node_id: NodeId | None = None,
) -> List[GraphOp]:
    return build_run_record_ops(
        result,
        actor=actor,
        now_utc=now_utc,
        base_version=snapshot.graph_version,
        algo_node_id=algo_node_id,
        experiment_node_id=experiment_node_id,
        run_node_id=run_node_id,
    )


def run_sorting_and_commit(
    lab_service: AlgoLabService,
    graph_service: GraphOSService,
    workspace_id: str,
    payload: dict,
    *,
    actor: str,
    algo_node_id: NodeId | None = None,
    experiment_node_id: NodeId | None = None,
    run_node_id: NodeId | None = None,
) -> ExperimentResult:
    result = lab_service.run_sorting(payload)
    snapshot = graph_service.get_snapshot(workspace_id)
    ops = build_run_record_ops_from_snapshot(
        snapshot,
        result,
        actor=actor,
        algo_node_id=algo_node_id,
        experiment_node_id=experiment_node_id,
        run_node_id=run_node_id,
    )
    graph_service.commit_ops(workspace_id, ops, actor=actor)
    return result
