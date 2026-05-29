# Base Infrastructure

This page explains the basic infrastructure that the agent system is expected
to grow around. It is not a final folder map. It is a mental model for the
subsystems that are likely to appear as the system becomes real.

## Purpose

Base infrastructure is the stable platform layer around agents.

It should answer:

```text
What does Algent own regardless of which runtime rail executes the agent?
```

## Core Platform Pieces

### Model Interface

The model interface describes and resolves LLM access.

It should let Algent say:

```text
provider = openai
model = some-model-id
target = langchain
```

without making every agent import provider-specific or LangChain-specific
classes directly.

### Prompt And Context

Prompt and context assembly decides what gets sent to the model.

This includes:

- system instructions
- task input
- relevant context
- memory or prior state
- tool results
- run-specific constraints

LangChain can carry messages, but Algent should decide what the messages mean.

### Runtime Rail

A runtime rail is the execution backend.

Examples:

- `langgraph`: first planned workflow runtime
- `native`: possible future Algent harness
- `direct_sdk`: possible simple one-shot model runner

The rail runs the workflow. Algent owns the surrounding contract.

### Run Context

Run context is the environment passed into a running agent.

It eventually contains services such as:

- run id
- workspace id
- model resolver
- artifact writer
- event emitter
- config access
- secret access
- trace metadata

The goal is to avoid each runtime inventing its own way to access platform
services.

### Artifacts

Artifacts are durable outputs produced by agents.

Examples:

- markdown brief
- normalized source JSON
- transcript
- report
- audio file
- video file
- trace reference

Artifacts are not just logs. They are reusable products of agent work.

### Run Events

Run events are the neutral event stream that describes what happened while an
agent ran.

Examples:

- `run.started`
- `model.resolved`
- `node.started`
- `artifact.created`
- `run.completed`
- `run.failed`

Runtime-specific details can be mapped into these neutral events.

### Tools

Tools let an agent affect the world.

Examples:

- fetch a URL
- query GraphOS
- write an artifact
- call an external API
- transform a file

Algent should own the canonical tool contracts. Runtime adapters can translate
those tools into LangChain tools or another runtime's format.

### Run Ledger

The run ledger is the durable record of what happened.

It should record:

- input
- selected model
- selected runtime
- status
- events
- artifacts
- errors
- final result

GraphOS can later become a projection or stronger lineage layer for important
run records.

## Dependency Direction

The clean dependency direction should be:

```text
definitions -> platform services -> runtime adapters -> concrete agents
```

External frameworks should sit behind adapters or targets.

The important rule:

```text
LangChain and LangGraph should not leak into every subsystem.
```

## What This Page Is Not

This page is not a commitment to build every package immediately.

It is a map of the likely base infrastructure so each new piece can be placed
with a clear reason instead of becoming a flat or monolithic pile.
