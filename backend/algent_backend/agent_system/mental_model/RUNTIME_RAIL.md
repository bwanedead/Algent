# Runtime Rail

This page explains how Algent executes agents through a runtime rail without
letting LangGraph leak into every subsystem.

## Core Rule

```text
LangGraph is the runtime rail.
agent_system/runtime/ is Algent's adapter boundary.
agents/* own graph shapes and the agent catalog.
runs/ owns execution request, context, and result.

Runtime adapters execute resolved AgentSpecs.
They do not own the agent catalog.
```

## Flow

As of Slice 2, orchestration runs through `RunService`:

```text
RunRequest -> RunService
  -> AgentRegistry.get(agent_id)
  -> RuntimeRegistry.get(runtime)
  -> LangGraphAdapter.run(request, context, agent_spec)
  -> RunResult
```

A caller describes *what* to run. `RunService` resolves the agent and the rail.
The adapter executes the already-resolved `AgentSpec` — it does not look agents
up. The agent module owns the graph's nodes and state shape.

See `AGENT_DEFINITION.md` for `AgentSpec`, `AgentRegistry`, and `RunService`.

## Ownership

### `runs/`

Neutral run contracts:

- `RunRequest` — agent id, input payload, runtime name
- `AgentRunContext` — platform services (run id, model resolver for now)
- `RunResult` — status, output, optional error

`runs/` must not import LangGraph.

### `runtime/`

Algent's runtime seam:

- `base.py` — `RuntimeAdapter` protocol (no LangGraph; `AgentSpec` only under
  `TYPE_CHECKING`)
- `registry.py` — adapter lookup and default registration (lookup only)
- `langgraph.py` — executes the handed `AgentSpec` via the rail's invocation
  contract (`build_graph(...)` returns something with `.invoke(input)`); the
  LangGraph import lives in `agents/*/graph.py`, not here

Callers reach rail adapters through `RunService` (which uses `RuntimeRegistry`),
not by importing `langgraph.py` directly.

### `agents/*/graph.py`

Concrete workflow definitions. This is where `StateGraph`, `START`, and `END`
belong. Graph builders receive `AgentRunContext` and close over it so nodes can
resolve models through `ModelResolver` without importing provider wrappers.

### `foundation/models/targets/langchain.py`

Still the only place that imports LangChain provider wrappers (`ChatOpenAI`, etc.).
Graph nodes get models via `context.model_resolver.resolve(...)`.

## What This Layer Still Omits

- artifact writer
- run event stream
- run ledger / persistence
- LangSmith tracing
- checkpointing
- tools
- dynamic agent discovery

Those are later slices.

## Example

```python
request = RunRequest(agent_id="hello_workflow", input={"topic": "LangGraph"})
context = AgentRunContext(run_id="run-1", model_resolver=ModelResolver())
result = RunService().run(request, context)
```

The hello workflow resolves a model, calls it once inside `generate_brief`, and
returns `{"topic": "...", "brief": "..."}` in `RunResult.output`.
