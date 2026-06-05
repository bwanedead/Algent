# Runtime Rail

This page explains how Algent executes agents through a runtime rail without
letting LangGraph leak into every subsystem.

## Core Rule

```text
LangGraph is the runtime rail.
agent_system/runtime/ is Algent's adapter boundary.
agents/* own graph shapes.
runs/ owns execution request, context, and result.
```

## Flow

Slice 1 proves this path:

```text
RunRequest -> AgentRunContext -> RuntimeRegistry -> LangGraphAdapter
-> agents/hello_workflow/graph.py -> RunResult
```

A caller describes *what* to run. The registry selects *which rail* executes it.
The adapter translates neutral contracts into LangGraph invocation. The agent
module owns the graph's nodes and state shape.

## Ownership

### `runs/`

Neutral run contracts:

- `RunRequest` — agent id, input payload, runtime name
- `AgentRunContext` — platform services (run id, model resolver for now)
- `RunResult` — status, output, optional error

`runs/` must not import LangGraph.

### `runtime/`

Algent's runtime seam:

- `base.py` — `RuntimeAdapter` protocol (no LangGraph)
- `registry.py` — adapter lookup and default registration
- `langgraph.py` — LangGraph compile/invoke adapter

Callers reach rail adapters through `RuntimeRegistry`, not by importing
`langgraph.py` directly.

### `agents/*/graph.py`

Concrete workflow definitions. This is where `StateGraph`, `START`, and `END`
belong. Graph builders receive `AgentRunContext` and close over it so nodes can
resolve models through `ModelResolver` without importing provider wrappers.

### `foundation/models/targets/langchain.py`

Still the only place that imports LangChain provider wrappers (`ChatOpenAI`, etc.).
Graph nodes get models via `context.model_resolver.resolve(...)`.

## What Slice 1 Deliberately Omits

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
result = RuntimeRegistry().run(request, context)
```

The hello workflow resolves a model, calls it once inside `generate_brief`, and
returns `{"topic": "...", "brief": "..."}` in `RunResult.output`.
