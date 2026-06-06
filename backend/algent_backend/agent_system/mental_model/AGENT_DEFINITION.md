# Agent Definition

This page explains how Algent represents an agent and orchestrates a run, added
in Slice 2. It builds on the model interface (Slice 0) and the runtime rail
(Slice 1).

## The Pieces

```text
AgentSpec      = in-process recipe for an agent
AgentRegistry  = the known agent catalog
RunRequest     = a request to execute an agent
RunService     = orchestrates lookup and execution
RuntimeAdapter = executes a resolved agent on its rail
```

## Flow

```text
RunRequest
  -> RunService
  -> AgentRegistry.get(agent_id)      # resolve the AgentSpec
  -> RuntimeRegistry.get(runtime)     # resolve the rail adapter
  -> tool_registry.resolve_for(spec)  # resolve + build the agent's tools
  -> AgentRunContext(run_id, model_resolver, tools)   # RunService assembles it
  -> LangGraphAdapter.run(request, context, agent_spec)
  -> RunResult
```

The key improvement over Slice 1: **agent lookup happens before runtime
execution**. The runtime adapter no longer knows the agent catalog — it executes
whatever `AgentSpec` it is handed.

## AgentSpec

`AgentSpec` is an in-process recipe, not a serializable wire contract. It carries
Python callables (`build_graph`), so it is a frozen dataclass, not a Pydantic
model. It stays neutral about the rail: `build_graph` returns `Any` and the spec
never imports LangGraph types.

```text
agent_id      stable identifier
name          human-facing label
runtime       which rail executes it (e.g. "langgraph")
build_graph   callable(context) -> runnable graph object
description   optional
default_model optional ModelSpec
family        optional grouping for tool scope (e.g. "news")
tool_ids      explicit tool ids the agent needs (e.g. ("web_search",))
```

If a serializable UI/GraphOS description is needed later, introduce a separate
`AgentManifest` rather than overloading `AgentSpec`.

## AgentRegistry

A small, explicit catalog: `register`, `get`, `list`, and
`default_agent_registry()`. No dynamic discovery, plugin system, or filesystem
scanning — agents are registered in code. `default_agent_registry()` explicitly
registers `hello_workflow.SPEC`.

`get` raises `ValueError` for an unknown agent, mirroring `RuntimeRegistry.get`.
`RunService` catches that and returns a failed `RunResult`.

## RunService

The single orchestration entrypoint. It looks up the `AgentSpec`, selects the
runtime adapter, and calls it. Lookup failures (unknown agent, unknown runtime)
become a failed `RunResult` rather than an exception, because this is the
user-facing control point.

As of Slice 3, `RunService` owns context creation: it generates the `run_id`
(uuid), resolves and builds the agent's tools, and assembles the
`AgentRunContext` before calling the adapter. Collaborators are injected through
the constructor (`agent_registry`, `runtime_registry`, `model_resolver`,
`tool_registry`), which keeps it test-friendly with fakes. The method is
`run(request)`.

## What It Owns / Must Not Own

- `AgentSpec` owns the agent recipe; it must not own rail types or execution.
- `AgentRegistry` owns the known catalog; it must not scan or discover.
- `RunService` owns orchestration; it may import `agents` and `runtime`.
- The neutral run primitives (`runs/models.py`, `runs/context.py`) must not
  import `agents`, `runtime`, LangGraph, or LangChain.

## Still Omitted

- agent manifests / serializable descriptions
- plugin discovery, filesystem scanning
- artifacts, run events, persistence
- LangSmith, GraphOS projection, native runtime
- schema validation for agent inputs/outputs

(Tools arrived in Slice 3 — see `TOOLS.md`.) The rest are later slices.
