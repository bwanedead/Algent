# Agent System Mental Model

This folder is a human-facing guide to the agent system. It is here to make the
architecture understandable before it becomes large. As we build, this guide
should be updated with the concepts, decisions, and examples that make the
system easier to reason about.

## North Star

Algent is the agent operating environment. It should be able to define, run,
inspect, and compose agents without becoming dependent on one external agent
framework.

LangChain, LangGraph, and LangSmith are useful first tools:

- LangChain can provide model and tool integration wrappers.
- LangGraph can provide a workflow/runtime rail for stateful agent execution.
- LangSmith can provide traces and debugging views.

But Algent should own the stable concepts: agent definitions, model selection,
run lifecycle, artifacts, logs, and eventual GraphOS-backed lineage.

## The Basic Stack

Think of the agent system as a set of layers:

1. Model interface

   How Algent contacts an LLM provider such as OpenAI, Anthropic, or Google.
   The first planned piece is a neutral `ModelSpec` that can be resolved into a
   LangChain chat model now, and a native SDK client later.

2. Prompt and context

   The messages and instructions sent to the model. LangChain can carry message
   objects, but Algent should decide what identity, task, memory, and state are
   included.

3. Runtime rail

   The engine that executes the agent. LangGraph is the first rail. Later rails
   might include an Algent-native harness, a direct SDK runner, or another agent
   framework.

4. Run context

   The environment around a running agent: run id, workspace id, model resolver,
   artifact writer, event emitter, config, secrets, and trace metadata.

5. Tools

   Callable capabilities that let an agent affect the world: fetch data, query a
   graph, write a file, call an API, or perform a transformation. Algent should
   own the canonical tool contracts, even when a runtime wraps them for its own
   format.

6. Artifacts

   Durable outputs produced by agents: markdown, JSON, source snapshots,
   transcripts, audio, images, videos, reports, and trace links.

7. Run ledger and operational truth

   The neutral record of what happened during a run: inputs, status, events,
   outputs, errors, artifacts, and decisions. GraphOS can later become the
   stronger lineage substrate, but it does not need to block the first working
   agent run.

## Key Distinctions

### Algent Agent vs LangChain Agent

An Algent agent is a portable system concept: what the agent is for, what input
it accepts, what model it wants, what runtime rail it uses, what tools it can
access, and what artifacts it produces.

A LangChain agent is one possible implementation detail inside the LangChain or
LangGraph ecosystem.

The goal is not to make every agent instantly portable across every runtime. The
goal is to keep the outer Algent contract stable so new rails can be added
without rewriting the whole system.

### Runtime State vs Operational Truth

LangGraph can manage execution state: graph state, checkpoints, interrupts, and
resume behavior.

Algent should manage operational truth: run records, artifacts, decisions,
source lineage, and durable outputs.

Short version:

```text
LangGraph manages execution state.
Algent manages operational truth.
```

### Model Provider SDK vs LangChain Integration

Provider SDKs are the raw API clients, such as `openai`, `anthropic`, or Google
model SDKs.

LangChain integration packages, such as `langchain-openai` or
`langchain-anthropic`, wrap those providers in LangChain's common model
interfaces.

Algent should describe model needs neutrally. Runtime-specific layers can decide
whether to instantiate a LangChain wrapper or a direct SDK client.

## First Build Sequence

The system should grow from small, understandable pieces.

1. Neutral model selection

   Define how Algent names a model and resolves it into a concrete callable
   object. This proves that LangChain is a target, not the core identity.

2. One simple model call

   Use the resolver to call a model through the first target. Keep this small so
   the model layer is easy to understand.

3. Minimal LangGraph workflow

   Add one tiny graph: input text -> model node -> artifact output -> result.

4. Artifact writer

   Save one durable output and return a stable artifact reference.

5. Neutral run events

   Emit events such as `run.started`, `node.started`, `artifact.created`, and
   `run.completed`.

6. Agent definition

   Introduce a small `AgentSpec` only after the runtime and model needs are
   clearer from the first working example.

7. Run ledger and GraphOS projection

   Record run history in a neutral way first. Later, project important records
   into GraphOS for lineage and workspace-level truth.

## What We Are Avoiding Early

- A full AgentOS rename before the shape has proven itself.
- GraphOS integration before one agent can run.
- Tool calling before the first workflow needs a tool.
- LangSmith tracing before local run events and artifacts exist.
- A universal runtime abstraction that is not validated by a working run.
- Deleting old placeholder modules before the new path replaces them.

## Working Vocabulary

- AgentSpec: Algent's description of an agent.
- ModelSpec: Algent's neutral description of a requested model.
- Runtime rail: an execution backend such as LangGraph or a future native
  harness.
- Runtime adapter: code that lets Algent run an agent on a specific rail.
- Run context: services and metadata handed to a running agent.
- Run event: neutral lifecycle/log event emitted while a run executes.
- Run result: terminal outcome of a run.
- ArtifactRef: durable pointer to an output produced by an agent.
- Operational truth: the durable Algent-owned record of what happened and what
  was produced.

## Update Rule

When a new piece of the agent system is added, update this folder with:

- what the piece is for
- what it owns
- what it must not own
- how it relates to LangChain, LangGraph, GraphOS, and future native systems
- a tiny example if that makes the idea easier to understand
