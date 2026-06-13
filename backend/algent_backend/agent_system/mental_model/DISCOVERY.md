# Discovery Agents

The first agent-native loop in Algent, and the template every later agent clones.

## What a discovery agent is

It surveys information sources and returns *candidate topics worth deeper work* —
it does not write the final article or brief. Output is a `DiscoveryResult`
(a capped list of `TopicCandidate`s) written as an artifact, which a downstream
research/brief agent consumes as its topic. Discovery is one of two ways a topic
enters the pipeline: you inject one, or a discovery run proposes some.

## The agent loop

Every agent stands on the same reusable loop: a model with tools bound, looping
model -> tool -> model until it decides it is done. That loop is LangGraph's
prebuilt `create_react_agent`, wrapped once in `agents/loop.py`. Algent supplies
the model, the resolved tool menu, the composed prompt, and a structured output
schema; LangChain/LangGraph owns the looping, tool selection, and execution.

`discovery/base/loop.py` wraps that ReAct agent in a thin graph so discovery's
input (optional `goal` + candidate cap) and output (`DiscoveryResult` artifact)
match run conventions instead of raw chat messages. The cap is enforced
mechanically after the model returns — discipline serving authorship, not
replacing it.

## Discovery as a class (composition, not inheritance)

`agents/discovery/` is a family package:

- `base/` — shared machinery: `contracts.py` (output types), `loop.py` (the
  discovery loop), `prompts.py` (the discovery class prompt layer).
- `general/` — the first specialty: open or goal-injected broad survey. Future
  specialties (`breaking_news/`, `investigative/`) clone this shape with their
  own prompt layer, tool menu, and cap semantics.

"Discovery-ness" is `family="discovery"` + living here + using `base/` — not an
`AgentSpec` subclass.

## Layered prompting

Prompts compose broad to specific via `prompting/compose_system_prompt(*layers)`,
to arbitrary depth:

```text
UNIVERSAL_AGENT_BASE   (agent_system/prompting/base.py — every agent)
  -> DISCOVERY_BASE    (discovery/base/prompts.py — the class)
    -> GENERAL_DISCOVERY (discovery/general/prompts.py — the specialty)
```

A runtime `goal` is an additional task-level layer (it shapes the loop's first
message), kept out of the fixed system prompt. Each layer is its own findable
module, so prompt surfaces are edited in isolation.

## Tool menu

The agent binds exactly the tools it lists in `tool_ids` (starting with
`gdelt_events` + `rss_feed`). Widening the sweep is a one-line change to
`TOOL_IDS`; the loop binds whatever is listed. Algent's `resolve_for` decides
what is available; the agent decides what it binds.

## Deferred

Multi-surface fan-out + agentic unification (a LangGraph graduation when one
agent over many surfaces strains), the `breaking_news` specialty (significance
threshold, fast tempo), scheduling, and the candidate -> research-run split.
