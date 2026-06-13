# Harness Ethos

Adapted for Algent from the Plattera harness constitution. It exists to prevent
one specific architectural regression: deterministic runtime code quietly
reclaiming authorship over the agent's work.

The harness provides rails, persistence, execution, observability, and safety.
It does not exist to secretly become the investigator.

---

## 1. Core Rule

The harness may be deterministic in its **mechanics**.
It may not be deterministic in its **semantic authorship**.

The LLM is the engine that understands the task, forms the work, chooses the
focus, and decides what unresolved things mean. The harness is the structure
around that engine.

Allowed deterministic rails:

- persistence (run state, events, ledger, artifacts)
- budgets, retries, and safety limits
- tool execution that the agent requested
- schema/payload validation
- trace collection and projection (timeline, LangSmith weave)
- HITL transport state (carrying prompts and answers, not interpreting them)
- run continuity (checkpoints, resume mechanics)

Forbidden semantic authorship:

- choosing the agent's focus or next move on its behalf
- deciding that feedback has been semantically incorporated
- inferring progress from heuristic counts or signatures
- deciding continue-vs-stop because deterministic code thinks the work is done
- host-authored verdicts in any observability surface ("stuck", "spinning")

Mechanical steps (ranking math, dedupe, fetch) may exist — as servants invoked
by the model's intent, never as deciders of flow.

## 2. The Layer Model

Layers only look down:

1. **Harness** (`runs/`, `artifacts/`, CLI): run lifecycle, control plane,
   observability. Universal — every agent gets it for free. Knows nothing about
   what any agent means.
2. **Runtime rails** (`runtime/`): execute agent loops on a specific rail
   (LangGraph first). Rail-specific imports live here and nowhere above.
3. **Tools** (`tools/`): capabilities agents may use, with neutral specs.
4. **Agents** (`agents/`): prompts, tool selection, output contracts. Agents
   never write their own run files or invent their own monitoring.

If a new category of work appears and does not fit a layer, give it a new home
deliberately — do not blend it into the nearest existing file.

## 3. Observability Rule

Two trace layers, joined by run id:

- **Owned** (events.jsonl, timeline.md, ledger): what Algent always keeps,
  regardless of vendor. Facts only.
- **Rented** (LangSmith): deep payload-level traces. Useful, never load-bearing
  — losing it must lose depth, not history.

The human timeline is a pure renderer over events: it copies facts and
model-authored text, truncates long fields visibly, and never interprets.

## 4. Organic Growth Rule

Build the minimal sound foundation, then let agents and their needs be
discovered through real runs — not orchestrated top-down. When pressure reveals
a missing capability, add it at the right layer with its own home. Top-down
over-orchestration is the documented 10x-undo trap this ethos exists to avoid.
