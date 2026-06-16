# North Star

This is the master mental model for Algent's agent system. It should preserve
the order in which the system is built, so future agentic systems can use it as
a recipe for laying down subsystems in a sane sequence.

## Core Idea

Algent is the agent operating environment.

LangChain, LangGraph, and LangSmith are useful tools, but they are not the
identity of the system.

```text
Algent owns the concepts.
Runtime rails execute the work.
External frameworks are selectable implementation paths.
```

## Build Order

The system should grow from the lowest useful layer upward.

1. Model interface

   Define how Algent names, selects, and resolves a model. This is the first
   brick because every agent eventually needs a model call.

2. Prompt and context assembly

   Define how Algent prepares the messages, instructions, task input, and
   contextual material sent to a model.

3. Runtime rail

   Define how an agent is executed. LangGraph is the first rail. Later rails can
   include a native Algent harness or direct SDK runner.

4. Run context

   Define the environment handed to a running agent: run id, workspace id, model
   resolver, artifact writer, event emitter, config, and other services.

5. Artifacts

   Define how agents produce durable outputs such as markdown, JSON, source
   snapshots, transcripts, media files, reports, and trace links.

6. Run events

   Define a neutral event stream for lifecycle and observability: run started,
   node started, artifact created, run completed, run failed.

7. Tools

   Define Algent-native tool contracts. Runtime adapters can wrap those tools
   for LangChain or other frameworks.

8. Run ledger

   Define the durable record of what happened: input, output, status, errors,
   artifacts, events, and decisions.

9. GraphOS projection

   Project important run records and artifacts into GraphOS when the agent
   system has enough real behavior to justify the graph vocabulary.

## Current Slice

Slice 0 proved model resolution:

```text
ModelSpec -> model resolver -> LangChain model object
```

Slice 1 proved runtime execution:

```text
RunRequest -> AgentRunContext -> RuntimeRegistry -> LangGraphAdapter
-> agents/hello_workflow/graph.py -> RunResult
```

Slice 2 makes agents first-class and adds an orchestration service:

```text
RunRequest -> RunService -> AgentRegistry.get(agent_id)
-> RuntimeRegistry.get(runtime) -> LangGraphAdapter.run(..., agent_spec)
-> RunResult
```

Slice 3 adds tools and the first real agent. `RunService` now also
resolves and builds the agent's tools and assembles the context:

```text
RunService -> resolve AgentSpec -> resolve + build tools
-> AgentRunContext(tools) -> LangGraphAdapter -> news_brief
-> web_search (Tavily) -> grounded brief -> RunResult
```

Slice 5 adds the sourcing portfolio: seven channel-organized tools
(search / social / depth / discovery) plus key management and the probe CLI.

Slice 6 (current) adds the harness layer — the run control plane every agent
runs on (see `HARNESS.md`):

```text
RunService -> RunRecorder -> runs_data/<run_id>/
  state.json + events.jsonl + timeline.md + result.json + done.json + artifacts/
CLI: python -m algent_backend.cli.runs start|status|watch|list|show
LangSmith trace per run (run_name = agent_id:run_id); token usage in the ledger
```

Together they establish these rules:

```text
Algent describes the model need.
The selected target decides how to instantiate it.

LangGraph is the runtime rail.
Algent's runtime module is the adapter boundary around that rail.

Algent owns agent lookup before runtime execution.
Runtime adapters execute resolved AgentSpecs; they do not own the catalog.

Algent decides tool availability (scope).
LangChain provides the concrete tool implementation.
```

See `RUNTIME_RAIL.md` for the runtime seam, `AGENT_DEFINITION.md` for
`AgentSpec`/`AgentRegistry`/`RunService`, `TOOLS.md` for the tool layer,
`NEWS_BRIEF_AGENT.md` for the first real agent, and `SOURCING_AND_PROVIDERS.md`
for how external connections (providers, tools, external agents) are organized.

## Standing Decisions

- Keep `agent_system` as the package name for now.
- Start with model resolution before runtime orchestration.
- Start with LangChain as the first model target.
- Start with LangGraph as the first runtime rail (Slice 1).
- Do not make GraphOS block the first working agent run.
- Do not build a native harness until there is pressure from a working slice.
- Do not design the full folder tree before the next layer earns its shape.
- Keep runtime adapters ignorant of the agent catalog; agent lookup is
  `RunService`'s job (Slice 2).
- Keep `AgentSpec` an in-process recipe (dataclass with callables), not a
  serializable contract; add a separate `AgentManifest` if serialization is
  needed later.
- Algent owns tool availability via scope (global/family/agent); concrete tools
  build themselves behind `ToolSpec.build` (Slice 3).
- Start news with deterministic search orchestration, not model-driven
  tool-calling; the latter can come later if a workflow needs it.
- Group external connection *config* by vendor in `config/providers/` (Axis 1);
  keep *mechanisms* (models, tools, external agents, rails) grouped by type in
  `agent_system/` (Axis 2). Provider folders declare; mechanisms consume;
  LangChain stays confined to named adapter edges. See `SOURCING_AND_PROVIDERS.md`.
- A model provider is just a vendor with a `model` surface; provider config
  (incl. the LLM brain's key) lives in `config/providers/`, not in the mechanisms.
- Distinguish the inward control CLI (`cli/`) from outward external agent systems
  (`external_agents/`, future) by direction of control; name X/Grok tools by
  trust level (`xai_x_search` derived, `x_api_*` canonical, `x_api_post` gated).

## Update Rule

When a new subsystem is added, update this folder with:

- what the subsystem is for
- why it comes at that point in the build order
- what it owns
- what it must not own
- how it relates to LangChain, LangGraph, GraphOS, and native systems
- a tiny example if that makes the idea easier to understand
