# Sourcing, Providers, and External Agents

How Algent reaches the outside world — model APIs, search/data APIs, and whole
external agent systems — without tangling vendor config, capability, and the
LangChain boundary together.

## The governing idea: two axes that must not be conflated

External integration has two independent axes. Keeping them apart is what keeps
the system from needing a future refactor.

```text
Axis 1 — Provider (config / data), grouped by VENDOR.
Axis 2 — Mechanism (code that acts), grouped by TYPE, consuming Axis 1.
```

- **Axis 1 — `config/providers/`.** One module per vendor (openai, anthropic,
  google, xai, tavily, exa, brave, firecrawl, ...). Pure data: the credential
  key name and the *surfaces* the vendor offers (`model`, `x_search`,
  `grok_build`, `web_search`, ...). No secrets, no logic, no LangChain. This is
  the navigable home — "everything xAI lives here."
- **Axis 2 — the mechanisms** that read Axis 1: `foundation/models/` (model
  calls), `tools/sourcing/<channel>/` (callable tools), `external_agents/`
  (external harnesses, future), `runtime/adapters/` (whole-run execution).

**The rule:** *provider folders declare; mechanisms consume; LangChain is
confined to named adapter edges* (`models/targets/langchain.py`,
`runtime/adapters/langgraph.py`, tool `_wrap.py`). Neutral contracts
(`ModelSpec`, `ToolSpec`, `AgentSpec`, `RunRequest`) never name a vendor SDK or
LangChain.

## Why provider config lives in `config/`, not `agent_system/`

Provider config is *connection configuration*, and the credential layer
(`config/credentials.py`) must read it. If the provider data lived in
`agent_system/`, then `config -> agent_system` plus the existing
`agent_system -> config` would be an import cycle. So the *facts* about reaching
a vendor live in `config/providers/`; the *mechanisms* that use a vendor live in
`agent_system/`. Same two-axis split, expressed as package placement.

## The LLM brain is just one provider surface

A model provider is not special — it's a vendor with a `model` surface.
`providers/openai/` describes the OpenAI model surface; `providers/xai/`
describes Grok-as-model *and* `xai_x_search` *and* the Grok Build harness, all
under one credential. The model-calling *mechanism* stays in
`foundation/models/` (the `ModelSpec -> resolver -> target` seam is unchanged);
only the per-vendor *facts* it used to hardcode are read from `config/providers/`.

## Capability vs vendor in the tool layer

Tools are organized by **capability** (`channel`: search / social / depth /
discovery), not by vendor — because orchestration selects by what a tool *does*.
Vendor is secondary metadata. A "provider suite" (e.g. all of X) is a config
grouping in `config/providers/`, not a tool folder; the X tools themselves are
scattered by capability and each reads `providers/xai` or `providers/x`.

## X / xAI: four surfaces, four trust levels

Same vendor family, deliberately distinct contracts. Name by trust level so a
"Grok found something on X" is never confused with "we hold the raw X object."

```text
xai_x_search   Grok-mediated X search API   derived intelligence   (built)
x_api_*        raw X REST objects           canonical evidence     (future)
x_api_post     write/publish to X           side-effecting, gated  (future)
grok_build     Grok CLI as an external      derived, agentic       (future)
               agent system
```

`x_api_post` is the first *side-effecting* capability and is what will force a
permission model onto `ToolSpec` (`side_effect`, `requires_approval`) — gated
behind human approval (HITL). Everything else is a read behind the existing seam.

## Direction of control: inward CLI vs outward external agents

```text
cli/              INWARD  — how humans / scripts / other agents control Algent
external_agents/  OUTWARD — external agent systems Algent drives (Grok Build,
                            Codex, Claude Code, Gemini CLI, ...)
```

These point opposite directions — do not lump them as "CLIs." An external agent
system (harness + model, usually reached via a headless CLI) is consumed two ways
from one mechanism:

- **As a tool** — an Algent agent delegates a *bounded subtask* and gets a report
  back; Algent stays the orchestrator. A façade `ToolSpec` placed by function
  (e.g. a Grok-X-research discovery tool). *This is the common case.*
- **As a rail** — the external agent *is* the executor for the whole job
  (`AgentSpec.runtime = "codex"`). A `RuntimeAdapter`.

Decision rule: **bounded subtask, Algent in control → tool; hand off the whole
job → rail.** Both consume `external_agents/<vendor>`, which reads its config
from `config/providers/<vendor>`.

Observability at the boundary: an external agent is a black box. The mechanism
must capture its raw output as a run artifact and emit a boundary event, and its
result is treated as *derived intelligence*, never canonical evidence.

## What it owns / must not own

- `config/providers/` owns: per-vendor credential key names and surface lists.
  Must not own: secrets themselves, mechanism, LangChain, or capability/trust
  logic.
- The mechanisms own: how to call a model / build a tool / drive a harness /
  execute a run. They must not hardcode vendor key names — they read them.

## Status

- **Built:** `config/providers/` (per-vendor descriptors); `credentials.py` as
  pure resolver over the registry; `xai_x_search` (renamed from `x_search`).
- **Reserved convention (not built):** `external_agents/`; `x_api_*` / `x_api_post`
  tools; richer per-vendor config (endpoints, model catalogs, harness setup) that
  joins a provider module when that vendor grows a second surface; a `provider`
  metadata field on `ToolSpec` (add when grouping-by-provider has a reader).
