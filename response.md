# Planning Notes: Phase 2 Architecture Grounding

Here is the most useful, concrete information to make the planning more complete and accurate, based on the current repo and the Phase 2 vision.

## What the codebase already implies (constraints + leverage)
- An "AgentOS embryo" already exists at `backend/algent_backend/agent_system/` (loops, providers, tool registry, orchestration). Renaming to AgentOS is a naming/API choice, not a structural blocker.
- GraphOS is already cleanly separated and has integration seams at `backend/algent_backend/graph_os/integration/` (agent tools and lab adapters). This is the correct place for "lab run -> GraphOps bundle" logic.
- GraphOps are minimal but sufficient for Phase 2 run records: `create_node`, `set_node_props`, `create_edge`, `set_layout`. There is no edge property update or delete yet, so run records should avoid those or you should add new ops.
- Vocabulary exists at `backend/algent_backend/graph_os/core/vocab/` but is not enforced. `graph_os/graphops/op_validate.py` only checks duplicate op IDs. This is a real choke point if you want typed, canonical run records.
- SQLite persistence is stubbed; filesystem ledger is the viable Phase 2 anchor unless sqlite is completed.

## Where the "flatness" is actually coming from
It is not primarily a missing folder problem. It is missing contracts and wiring:
- No canonical "run record" schema yet (node kinds, edge types, required props).
- No vocab registry wired into GraphOS validation.
- No formal adapter that translates a lab run into a GraphOps bundle.
- No friction report schema defined.

## Direct responses to the choke points in the conversation
- **AgentOS vs agent_system**: Keep `agent_system` for now; expose "AgentOS" at an API boundary or CLI layer. Structural separation matters more than renaming right now.
- **feedback/models.py unclear**: This should be the stable schema for friction reports (envelope fields + flexible `details` dict). If you want self-discovery, keep a fixed top-level and allow details to evolve, later promoting stable fields into vocab.
- **pattern catalog vs forgetting**: Treat pattern memory as a projection over canonical graph data, not a second truth. Implement "forgetting" as decay or ranking changes, not deletion from the ledger.
- **vocab inside GraphOS feels fused**: Keep registry interfaces in GraphOS so validation can happen, but keep vocab packs outside (or at least separated) so the coral reef can be detached and swapped.

## Missing info that would most improve planning accuracy
- The minimal Phase 2 run record schema (node kinds + edge types + required props).
- The intended persistence anchor (filesystem ledger vs finishing sqlite).
- Whether "AgentOS" should be a surface name or a formal package boundary in Phase 2.

## Practical recommendation for the inoculation phase
The highest-leverage decision is to define the canonical run record shape. Once that is fixed, directory structure and module boundaries fall into place with much less ambiguity.

## Current backend tree
```
algent_backend/
__init__.py
agent_system/
  __init__.py
  foundation/
    __init__.py
    agents/
      __init__.py
      agent_loop.py
      loops/
        __init__.py
        react_loop.py
      state_manager.py
    models/
      __init__.py
      model_registry.py
      providers/
        __init__.py
        anthropic_provider.py
        base_provider.py
        gemini_provider.py
        openai_provider.py
        xai_provider.py
    prompting/
      __init__.py
      prompt_builder.py
      registries/
        __init__.py
        base_prompts.py
  integration/
    __init__.py
    response_parser.py
    tool_registry.py
  orchestration/
    __init__.py
    orchestrator.py
api/
  __init__.py
  routes.py
app.py
commands/
  __init__.py
  dispatcher.py
  models.py
config/
  __init__.py
  credentials.py
  settings.py
graph_os/
  __init__.py
  core/
    commit.py
    errors.py
    ids.py
    invariants.py
    primitives/
      edge.py
      layout.py
      node.py
      snapshot.py
    vocab/
      registry.py
      rules.py
      types.py
  docs/
    graph-ethos.md
    graph-masterplan.md
    KERNEL_CONSTITUTION.md
  graphops/
    op_apply.py
    op_checkpoint.py
    op_log_types.py
    op_replay.py
    op_types.py
    op_validate.py
  integration/
    agent_tools/
      graph_os_tools.py
    labs/
      lab_node_templates.py
  persistence/
    filesystem/
      commit_ledger_store.py
      jsonl_oplog_store.py
      lock.py
      snapshot_store.py
    sqlite/
      migrations/
        0001_init.sql
        0002_indexes.sql
      sqlite_store.py
    store_interface.py
  projection/
    rag/
      rag_indexer.py
      rag_store_interface.py
      rag_textify.py
      stores/
        faiss_store.py
        sqlite_fts_store.py
    rdf/
      rdf_export.py
      rdf_mapping.py
      shacl_validate.py
  services/
    graph_export_service.py
    graph_lineage_service.py
    graph_os_service.py
    graph_query_service.py
  state/
    concurrency.py
    op_commit_state.py
    workspace_state.py
labs/
  __init__.py
  algo_lab/
    __init__.py
    algorithms/
    algorithms.py
      sorting.py
    datasets.py
    experiments.py
    metrics.py
    service.py
  news_hub/
    __init__.py
metrics/
  __init__.py
```
