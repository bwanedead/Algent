"""
Algo Lab vocabulary pack (v0).
"""
from __future__ import annotations

from ..registry import VocabularyRegistry
from ..types import EdgeType, NodeKind, PropertySpec


PACK_VERSION = "algo_lab@v0"


def register(registry: VocabularyRegistry) -> None:
    registry.register_node_kind(
        NodeKind(
            name="lab.algo",
            description="Algo Lab workspace root node.",
            required_props=[
                PropertySpec(name="title", value_type="str", required=True),
            ],
            optional_props=[
                PropertySpec(name="description", value_type="str"),
            ],
        )
    )
    registry.register_node_kind(
        NodeKind(
            name="lab.algo.experiment",
            description="Algo Lab experiment definition.",
            required_props=[
                PropertySpec(name="title", value_type="str", required=True),
                PropertySpec(name="algo_name", value_type="str", required=True),
            ],
            optional_props=[
                PropertySpec(name="goal", value_type="str"),
                PropertySpec(name="notes", value_type="str"),
            ],
        )
    )
    registry.register_node_kind(
        NodeKind(
            name="lab.algo.run",
            description="Algo Lab run record.",
            required_props=[
                PropertySpec(name="title", value_type="str", required=True),
                PropertySpec(name="algo_name", value_type="str", required=True),
                PropertySpec(name="params", value_type="json", required=True),
                PropertySpec(name="seed", value_type="int", required=True),
                PropertySpec(name="status", value_type="str", required=True),
                PropertySpec(name="started_at_utc", value_type="str", required=True),
                PropertySpec(name="ended_at_utc", value_type="str", required=True),
            ],
            optional_props=[
                PropertySpec(name="summary", value_type="str"),
                PropertySpec(name="error", value_type="str"),
                PropertySpec(name="step_count", value_type="int"),
            ],
        )
    )
    registry.register_node_kind(
        NodeKind(
            name="lab.algo.artifact.metrics_timeseries",
            description="Metrics timeseries artifact from an Algo Lab run.",
            required_props=[
                PropertySpec(name="title", value_type="str", required=True),
                PropertySpec(name="metric_name", value_type="str", required=True),
                PropertySpec(name="data", value_type="json", required=True),
                PropertySpec(name="derived", value_type="bool", required=True),
                PropertySpec(name="source_run_id", value_type="str", required=True),
            ],
            optional_props=[
                PropertySpec(name="units", value_type="str"),
            ],
        )
    )
    registry.register_node_kind(
        NodeKind(
            name="note",
            description="Freeform annotation note.",
            required_props=[
                PropertySpec(name="title", value_type="str", required=True),
                PropertySpec(name="text", value_type="str", required=True),
            ],
        )
    )

    registry.register_edge_type(
        EdgeType(
            name="contains",
            description="Container relationship for lab workspace grouping.",
            allowed_src_kinds=["lab.algo"],
            allowed_dst_kinds=["lab.algo.experiment", "lab.algo.run"],
        )
    )
    registry.register_edge_type(
        EdgeType(
            name="has_run",
            description="Experiment to run relationship.",
            allowed_src_kinds=["lab.algo.experiment"],
            allowed_dst_kinds=["lab.algo.run"],
        )
    )
    registry.register_edge_type(
        EdgeType(
            name="produces",
            description="Run produced an artifact.",
            allowed_src_kinds=["lab.algo.run"],
            allowed_dst_kinds=["lab.algo.artifact.metrics_timeseries"],
        )
    )
    registry.register_edge_type(
        EdgeType(
            name="annotates",
            description="Note annotates a node.",
            allowed_src_kinds=["note"],
            allowed_dst_kinds=[
                "lab.algo",
                "lab.algo.experiment",
                "lab.algo.run",
                "lab.algo.artifact.metrics_timeseries",
            ],
        )
    )
    registry.register_edge_type(
        EdgeType(
            name="compares_to",
            description="Comparison edge between runs.",
            allowed_src_kinds=["lab.algo.run"],
            allowed_dst_kinds=["lab.algo.run"],
        )
    )
