# Algent Backend (/backend/algent_backend) Architecture Report

## Scope
This report covers the Python backend package under `backend/algent_backend/`, focusing on module responsibilities, key flows, and extension points.

## Directory Tree (Focused)
```
backend/algent_backend/
├── __init__.py
├── app.py
├── api/
│   ├── __init__.py
│   └── routes.py
├── commands/
│   ├── __init__.py
│   ├── dispatcher.py
│   └── models.py
├── config/
│   ├── __init__.py
│   ├── credentials.py
│   └── settings.py
├── metrics/
│   └── __init__.py
├── agent_system/
│   ├── __init__.py
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── response_parser.py
│   │   └── tool_registry.py
│   ├── foundation/
│   │   ├── __init__.py
│   │   ├── agents/
│   │   │   ├── __init__.py
│   │   │   ├── agent_loop.py
│   │   │   ├── state_manager.py
│   │   │   └── loops/
│   │   │       ├── __init__.py
│   │   │       └── react_loop.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── model_registry.py
│   │   │   └── providers/
│   │   │       ├── __init__.py
│   │   │       ├── base_provider.py
│   │   │       ├── anthropic_provider.py
│   │   │       ├── gemini_provider.py
│   │   │       ├── openai_provider.py
│   │   │       └── xai_provider.py
│   │   └── prompting/
│   │       ├── __init__.py
│   │       ├── prompt_builder.py
│   │       └── registries/
│   │           ├── __init__.py
│   │           └── base_prompts.py
│   └── orchestration/
│       ├── __init__.py
│       └── orchestrator.py
├── labs/
│   ├── __init__.py
│   ├── algo_lab/
│   │   ├── __init__.py
│   │   ├── algorithms.py
│   │   ├── datasets.py
│   │   ├── experiments.py
│   │   ├── metrics.py
│   │   ├── service.py
│   │   └── algorithms/
│   │       └── sorting.py
│   └── news_hub/
│       └── __init__.py
└── graph_os/
    ├── __init__.py
    ├── docs/
    │   ├── graph-ethos.md
    │   ├── graph-masterplan.md
    │   └── KERNEL_CONSTITUTION.md
    ├── core/
    │   ├── commit.py
    │   ├── errors.py
    │   ├── ids.py
    │   ├── invariants.py
    │   ├── primitives/
    │   │   ├── edge.py
    │   │   ├── layout.py
    │   │   ├── node.py
    │   │   └── snapshot.py
    │   └── vocab/
    │       ├── registry.py
    │       ├── rules.py
    │       └── types.py
    ├── graphops/
    │   ├── op_apply.py
    │   ├── op_checkpoint.py
    │   ├── op_log_types.py
    │   ├── op_replay.py
    │   ├── op_types.py
    │   └── op_validate.py
    ├── integration/
    │   ├── agent_tools/
    │   │   └── graph_os_tools.py
    │   └── labs/
    │       └── lab_node_templates.py
    ├── persistence/
    │   ├── store_interface.py
    │   ├── filesystem/
    │   │   ├── commit_ledger_store.py
    │   │   ├── jsonl_oplog_store.py
    │   │   ├── lock.py
    │   │   └── snapshot_store.py
    │   └── sqlite/
    │       ├── sqlite_store.py
    │       └── migrations/
    │           ├── 0001_init.sql
    │           └── 0002_indexes.sql
    ├── projection/
    │   ├── rdf/
    │   │   ├── rdf_export.py
    │   │   ├── rdf_mapping.py
    │   │   └── shacl_validate.py
    │   └── rag/
    │       ├── rag_indexer.py
    │       ├── rag_store_interface.py
    │       ├── rag_textify.py
    │       └── stores/
    │           ├── faiss_store.py
    │           └── sqlite_fts_store.py
    ├── services/
    │   ├── graph_export_service.py
    │   ├── graph_lineage_service.py
    │   ├── graph_os_service.py
    │   └── graph_query_service.py
    └── state/
        ├── concurrency.py
        ├── op_commit_state.py
        └── workspace_state.py
```

## High-Level Responsibilities
- `app.py`: stdlib HTTP entrypoint (health + credential updates).
- `api/`: placeholder handlers mirroring entrypoint logic.
- `config/`: environment-backed settings + credential storage helpers.
- `commands/`: typed commands and dispatcher for routing.
- `agent_system/`: agent loops, model registry, prompting, tool integration, orchestration.
- `labs/`: domain-specific labs (Algo Lab implemented; News Hub stub).
- `graph_os/`: graph-native workspace substrate (ops, commit ledger, projections).

## Key Runtime Flows
- Backend entry: `/health` and `/credentials` via stdlib HTTP server.
- Command dispatch: `CommandDispatcher` routes `Command` by name.
- Agent loop: `AgentLoop` logs to `ConversationState`; `Orchestrator` runs loops.
- Algo Lab: `AlgoLabService` builds config, generates dataset, runs algorithm, computes metrics.
- GraphOS: `GraphOSService` validates ops, applies reducer, builds commit, appends to ledger.

## GraphOS Subsystem Summary
- Canonical truth is the GraphOps commit ledger.
- Ops include create node, set node props, create edge, set layout.
- Commit hashing and deterministic serialization are enforced.
- Store interface exists; sqlite/filesystem stores are scaffolding.
- Query/export/lineage services are minimal stubs.

## Extension Points
- Swap stdlib server for FastAPI/Flask using `api/` handlers.
- Implement `WorkspaceStore` persistence (ledger + snapshots).
- Expand GraphOps set (delete/update edges/nodes, grouping, layout ops).
- Implement vocabulary registry + validation.
- Wire labs and agents into GraphOS via tool shims.

## Notable Gaps
- `SQLiteWorkspaceStore.load_state/append_commit` not implemented.
- GraphOS query/export/lineage services are minimal.
- Agent loops are skeletons; no real model call orchestration yet.

## Background Context (Ethos + Vision)
- Structural soundness, separation of concerns, persistence as truth, clarity over cleverness.
- GraphOS: GraphOps log is the authoritative truth; stable IDs + typed vocab; separation of meaning/presentation/lineage; deterministic commits.
- Vision: universal agent ecosystem, graph-native workspace OS, Algo Lab for emergent algorithm behaviors.
