# News Brief Agent

`news_brief` is Algent's first *real* agent (Slice 3). Unlike `hello_workflow`
(a no-tool regression path), it performs live web search through the tool seam
and writes a brief grounded in the results.

## Shape

```text
family    = "news"
tool_ids  = ("web_search",)
runtime   = "langgraph"

START -> research_and_brief -> END
```

Inside `research_and_brief`:

```text
1. read topic from state
2. search_tool = context.tools["web_search"]
3. results = search_tool.invoke({"query": topic})
4. resolved = context.model_resolver.resolve(DEFAULT_MODEL)
5. response = resolved.client.invoke([system_prompt, user_prompt(topic, results)])
6. return {"search_results": results, "brief": response_text}
```

## Why Deterministic Orchestration First

v0 does **not** use model-driven tool-calling (`bind_tools`, a ReAct loop where
the model decides whether/when to search). The node searches explicitly, then
asks the model to write the brief.

This is deliberate. The news vision needs editorial reliability and perspective
coverage. That is better served by planned, orchestrated searches than by a loop
that searches however it feels. Model-driven tool-calling is useful and can come
later, but it is not the right first shape for a perspective-balanced product.

## Prompt Rules

The prompt (in `prompts.py`, separate from graph wiring) requires the model to:

- ground the brief strictly in the search results
- separate facts from interpretation
- surface differing perspectives only where the results support them
- note uncertainty or missing evidence
- not fabricate sources, and not claim a perspective the results don't show

## Where This Goes Next

The single node is v0. The intended expansion:

```text
search_by_perspective -> analyze_overlap_conflict -> write_brief
```

with planned searches (mainstream, multiple political/regional framings) that
LangGraph orchestrates. The Slice 3 win is that real internet search now flows
through Algent's tool seam, so that expansion is additive.
