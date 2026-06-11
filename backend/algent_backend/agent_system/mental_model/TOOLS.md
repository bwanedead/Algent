# Tools

This page explains how Algent gives agents capabilities (tool seam added in
Slice 3; sourcing portfolio in Slice 5). Tools
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

This wires the global + family + agent hierarchy now. All current sourcing
tools are `global`; family/agent scoping is exercised by tests and waits for the
first genuinely family-specific tool.

## The Sourcing Portfolio (Slice 5)

Sourcing tools live in `tools/sourcing/`, organized by **capability channel** —
one vendor per module, vendor imports lazy inside each `build()`:

```text
channel      tool_id           vendor       key             what it is for
search       web_search        Tavily       TAVILY_API_KEY  keyword web/news search
search       brave_search      Brave        BRAVE_API_KEY   independent-index diversity
search       semantic_search   Exa          EXA_API_KEY     meaning-based niche discovery
social       x_search          xAI Grok     XAI_API_KEY     live X posts/claims/sentiment
depth        fetch_content     trafilatura  (none)          full-page article extraction
                               + Firecrawl  FIRECRAWL_API_KEY  fallback for hard pages
discovery    rss_feed          feedparser   (none)          what outlets publish now
discovery    gdelt_events      GDELT        (none)          global breaking-news firehose
```

`ToolSpec.channel` tags each tool so future orchestration can fan out by
capability ("run all `search` tools, merge, dedupe") without naming vendors.
Agent code asks for tool ids, never vendors — swapping Exa out later touches one
module.

Keys load from environment, then `backend/.env` (copy `.env.example`), then OS
keyring. A missing key only disables the tools that need it — everything else
keeps working, because tools build lazily.

`x_search` is the special one: X has no affordable search API, so the tool asks
Grok (with xAI's server-side live search over X) to search and report with
citations. It is a model-call wearing a tool interface, and it uses the xAI
*provider* key.

To manually evaluate any vendor before wiring it into an agent:

```text
python -m algent_backend.cli.probe_tool --list
python -m algent_backend.cli.probe_tool web_search "ukraine ceasefire talks"
python -m algent_backend.cli.probe_tool fetch_content url=https://example.com/article
```

```text
Algent decides tool availability.
LangChain (or plain REST behind a StructuredTool) provides the implementation.
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
- `tools/sourcing/*` own concrete tool construction; this is where rail/service
  dependencies live, one vendor per module.
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
