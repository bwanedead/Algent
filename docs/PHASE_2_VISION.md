# Phase 2 Vision: The Sprout Loop (Algo Lab + Agent Loop + Coral Reef)

Phase 1 built the **stem**: GraphOS as a deterministic, tamper-evident substrate (event-sourced commits, replay, invariants, single canonical write-path).
Phase 2 is the **sprout**: the first closed loop that touches reality, produces measurable artifacts, commits them into the substrate, and then uses those artifacts to choose the next action.

This document captures the full Phase 2 target: the **flywheel**—a compounding, self-improving system that can *learn what works*, *remember it*, and *petition for missing affordances* in a way that is safe, testable, and structurally sane.

---

## 1) The Core Idea

Phase 2 turns Algent from “a strong kernel” into **a living coordination organism**:

- It **acts** (runs a real experiment / pipeline step).
- It **observes** (metrics, traces, artifacts).
- It **commits** (a canonical run record into GraphOS).
- It **retrieves** (prior successful patterns).
- It **reflects** (summarizes outcomes + proposes next move).
- It **reports friction** (explicit “missing limb” / “tool I wish existed” signals).
- It repeats.

The point is not to build a giant “Agent OS” framework up front.
The point is to build **one honest loop** that produces reality-backed outputs and leaves behind a verifiable trail.

That loop becomes the seed crystal for everything else.

---

## 2) The Three-Layer Separation (Non-Negotiable)

To preserve sanity, swapability, and long-term evolution, we keep these three layers distinct:

### 2.1 GraphOS = Physics
GraphOS is the substrate of truth:
- append-only commits
- replayable state
- deterministic reducers
- invariants as “laws of physics”
- tamper evidence via hash-chaining

GraphOS does *not* “decide what is optimal.”
It only decides what is *valid* and what *happened*.

### 2.2 AgentOS = Behavior
AgentOS is the control loop:
- planning strategy
- tool calling
- evaluation criteria
- stop conditions
- exploration scheduling
- “pain signal” emission

AgentOS treats GraphOS as a provider (a tool / substrate), not as its identity.
AgentOS should remain pluggable across kernels.

### 2.3 Coral Reef = Culture
The “coral reef” is accumulated, reusable structure:
- successful templates
- canonical shapes for run records
- emergent vocabularies that survive contact with reality
- reusable op sequences (“moves”)
- “what worked before” distilled into retrievable priors

This is where practical intelligence compounds.
The reef can be stored inside GraphOS, indexed in RAG, exported/imported, versioned, compared, and transplanted.

**Physics is strict. Behavior is swappable. Culture is portable.**

---

## 3) Phase 2 Deliverable: One Flywheel That Works

Phase 2 is “done” when this exists end-to-end:

1. A **deterministic lab runner** can execute an experiment and produce artifacts.
2. A **canonical run record** is written to GraphOS for every run.
3. An **agent loop** can:
   - propose a run
   - execute it
   - commit it
   - summarize it
   - propose the next run
4. A **pattern memory** can retrieve prior runs/patterns relevant to the current task.
5. A **friction reporter** can persist “missing affordances” as first-class artifacts.

When that loop runs repeatedly, the system begins to:
- converge on stable graph shapes (reef formation)
- self-identify missing tools (friction stream)
- produce measurable improvement over time (compounding)

---

## 4) The Minimal “Reality Anchor”: Algo Lab Runner

Phase 2 begins with one real lab slice (Algo Lab). The runner is intentionally small:

- Input: **experiment name + params + seed**
- Output: **metrics + traces + artifacts** (tables, plots, summaries, etc.)
- Deterministic: same input → same output (or explicit controlled randomness via seed)

The runner is the grounding mechanism.
Without it, an agent can produce impressive structures without actually learning anything real.

---

## 5) Canonical Run Record (The First Reef Skeleton)

Every run produces a canonical “run record” subgraph.
This is the first place vocabulary matters.

A run record is not “random graph data.”
It is a stable shape that other layers can depend on.

**A run record should capture:**
- Experiment identity + version
- Run identity + timestamp + actor
- Parameter set (and its hash)
- Input dataset/spec (if applicable)
- Output metrics (structured)
- Output artifacts (trace tables, images, etc.)
- Lineage edges: derived-from, produced-by, summarizes, compares-to, etc.
- Optional: evaluation labels (good/bad), notes, tags

**Key principle:** the run record is *canonical* even if the UI and projections change.
Derived views are rebuildable; the record is the durable truth.

---

## 6) The Agent Loop Controller (The Embryo of AgentOS)

Phase 2 AgentOS is a disciplined loop, not a sprawling framework.

### 6.1 The loop in one sentence
**Plan → Act → Observe → Commit → Reflect → (Store Patterns + Report Friction) → Repeat**

### 6.2 Tool surface (minimal by design)
The agent should start with a small tool belt:
- read current graph state (snapshot + query helpers)
- run an experiment (Algo Lab runner)
- commit results (GraphOS commit_ops via a run-record builder)
- retrieve prior patterns (RAG / graph query)
- report friction (write a friction artifact)

### 6.3 Why commits are required per step
A step “counts” only if its outputs are committed.
This prevents:
- silent drift
- lost provenance
- off-ledger state
- “it happened in chat but not in reality”

Exploration is cheap; finality is expensive.

---

## 7) Pattern Memory (RAG as Culture Retrieval)

The pattern memory is not “truth.”
It is an acceleration layer that maps back to truth.

Phase 2 memory does two things:
1. Retrieve relevant priors: “what templates, graphs, and moves worked in similar contexts?”
2. Store new priors: “this pattern worked (or failed) under these conditions.”

The memory can be backed by:
- GraphOS queries (canonical)
- RAG index over graph artifacts (derived, rebuildable)
- Hybrid: RAG retrieves candidates, GraphOS verifies and provides lineage

**Non-negotiable:** anything retrieved must be traceable back to canonical IDs and commits.

---

## 8) Friction Reporter (The Self-Healing Channel)

This is the “holy shit” lever.

After each loop, the system emits a structured friction report:
- what goal it attempted
- what it could not do cleanly
- which affordance was missing (tool/query/projection/primitive/permission)
- the workaround it used (if any)
- expected impact if the missing affordance existed
- confidence that this is truly missing vs. preference

These friction artifacts become:
- a backlog stream
- a measurable signal of where the system is constrained
- the driver of platform evolution under real pressure, not speculation

**Safety rule:** agents do not mutate the kernel directly.
They petition via friction, and changes are implemented through normal engineering gates (tests, invariants, review).

---

## 9) What Makes This System “Compounding”

The flywheel compounds because every cycle produces:

1. **Truth artifacts** (run records with measurable results)
2. **Reusable structure** (templates + stable shapes → reef growth)
3. **Acceleration** (retrieval of prior patterns reduces reinvention)
4. **Directed evolution** (friction reports become concrete build pressure)

Over time:
- the reef becomes a library of reusable cognitive organs (modules, schemas, workflows)
- agents become faster and more aligned because they reuse stable shapes
- engineering effort is guided by real constraints rather than hypothetical needs

---

## 10) What We Are NOT Building Yet (Explicit Non-Goals)

To avoid scope explosions, Phase 2 does not attempt:
- a full multi-agent economy or payment layer
- distributed consensus across machines
- a universal “everything lab”
- fully autonomous code deployment
- elaborate UI polish as a prerequisite

Phase 2 is a single honest loop + the minimal structures that make it durable, retrievable, and evolvable.

---

## 11) Hardening Requirements (Ethos & Sanity Constraints)

Phase 2 must preserve the kernel’s “invulnerability shield” posture.

### 11.1 Single canonical mutation path
All mutation goes through GraphOS service gating (commit_ops / dry_run_ops).
No subsystem “writes around” the kernel.

### 11.2 Determinism & canonicalization
- canonical serialization/hashing must be stable
- op payloads must be canonicalized (no type drift across write vs replay)
- replay must reproduce identical snapshots

### 11.3 Derived layers are disposable
- RAG indexes, projections, and caches are rebuildable
- the source of truth remains the commit ledger + replay rules

### 11.4 Strict separation of concerns
- Lab runner produces results; it does not define truth history
- Agent loop proposes; it does not bypass invariants
- Vocabulary defines meaning; it does not mutate state by itself

---

## 12) The Phase 2 “First Use Case” (Concrete)

The first demonstration loop should be brutally simple and real:

“Run three variations and summarize.”

- The agent retrieves prior runs (if any).
- It proposes three parameter variations.
- The runner executes them deterministically.
- The system commits three run records.
- The agent summarizes outcomes and proposes the next best experiment.
- The agent emits a friction report: what it wished it could query/compare/visualize.

If Phase 2 is healthy, this will immediately generate:
- useful run records
- pressure for a “compare runs” projection
- pressure for parameter hashing and standard hypothesis nodes
- pressure for better lineage queries

That pressure becomes the roadmap, generated by reality.

---

## 13) Success Criteria (Phase 2 Exit Conditions)

Phase 2 is complete when:
- A minimal lab runner exists and is callable.
- An agent can execute the full loop end-to-end.
- Every run yields a canonical committed run record.
- Memory retrieval can pull prior patterns and map back to canonical commits.
- Friction reports are produced and stored as first-class artifacts.
- The system can be restarted and replayed to reconstruct state exactly.

At that point, the platform stops being a concept and becomes a compounding machine.

---

## 14) Why This Matters

GraphOS makes truth durable.
Phase 2 makes improvement inevitable.

This is the moment Algent becomes a substrate where:
- exploration is fluid but recorded,
- finality is expensive but trustworthy,
- useful structures crystallize,
- and the system itself points to what it needs next.

That is the sprout.
That is the flywheel.
That is the beginning of the coral reef.
