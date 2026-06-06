# Tools

This page explains how Algent gives agents capabilities, added in Slice 3. Tools
are **capabilities, not artifacts** — they let an agent *act* (search the web,
later: query a graph, call an API). They are not the durable outputs a run
produces (those come in a later artifacts slice).

## The Pieces

```text
ToolSpec      = tool metadata + an in-process builder
ToolRegistry  = the known tool catalog + scope resolution
AgentRunContext.tools = the concrete tools built for one run
```

## Scope

Tool availability is a simple string convention, not a permissions engine:

```text
global              every agent gets it
family:<family>     agents in a family (e.g. family:news)
agent:<agent_id>    one specific agent
```

`ToolRegistry.resolve_for(agent_spec)` returns the tools an agent may use:
any tool whose scope is `global`, the agent's `family:<family>`, or
`agent:<agent_id>` — plus any tool the agent names explicitly in `tool_ids`
(an escape hatch that ignores scope). A required `tool_id` that is not registered
is a configuration error and raises `ValueError` (which `RunService` turns into a
failed `RunResult`) rather than failing opaquely later inside the graph.

This wires the global + family + agent hierarchy now, even though only
`global:web_search` exists today.

## web_search (Tavily)

The first concrete tool. `tools/shared/web_search.py` is the only place
`langchain_tavily` is imported, and the import is lazy (inside the builder) so
the neutral tool layer stays light. Its API key comes from Algent's config
layer (`get_service_api_key("tavily")`), keyed under `TAVILY_API_KEY` — a
*service* key, kept separate from model-provider keys.

```text
Algent decides tool availability.
LangChain provides the concrete tool implementation.
```

## How a tool reaches an agent

```text
RunService.run(request)
  -> resolve AgentSpec
  -> tool_registry.resolve_for(agent_spec)   # which tools by scope/id
  -> AgentRunContext(tools=ResolvedTools(...))  # lazy mapping, handed to the graph
  -> graph node: context.tools["web_search"].invoke({"query": topic})  # builds here
```

`RunService` assembles the context (including tools) *after* resolving the
`AgentSpec`. Tools are **built lazily**: `ResolvedTools` constructs a tool only on
first access and caches it, so a no-tool agent never builds (or requires
credentials for) a global tool it doesn't use. The graph node uses the tool; it
never constructs one.

## What This Layer Owns / Must Not Own

- `ToolSpec` / `ToolRegistry` own metadata and scope resolution; they import no
  LangChain/LangGraph (`AgentSpec` only under `TYPE_CHECKING`).
- `tools/shared/*` own concrete tool construction; this is where rail/service
  dependencies live.
- The neutral run primitives (`runs/models.py`, `runs/context.py`) must not
  import tools' concrete dependencies — `context.tools` holds built objects typed
  as `Any`.

## What This Slice Deliberately Omits

- permissions / approval / human review of tool use
- MCP tool loading, dynamic discovery
- `tools/adapters/` (premature until a second tool target appears)
- model-driven tool-calling (`bind_tools`); v0 orchestration is deterministic
- artifacts / durable output storage

Those are later slices.

## Note: lazy building

Global tools resolve for every agent, but `ResolvedTools` only builds one when a
node accesses it. This is what keeps `hello_workflow` (and any future no-tool
agent) runnable without a `TAVILY_API_KEY`, even though `web_search` is global.
