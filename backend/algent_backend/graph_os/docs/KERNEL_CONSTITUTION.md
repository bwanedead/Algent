# GraphOS Kernel Constitution

## Purpose

GraphOS is a graph-native substrate where **agents and humans share the same primitives** for building and evolving a workspace. The kernel defines the minimal “physics + grammar” required for a stable, replayable, and extensible graph system.

The kernel exists to guarantee **reliability, determinism, and composability** as complexity scales.

## Kernel Boundary

**Kernel** means: **core primitives + GraphOps (mutation contract) + invariants/validation + deterministic serialization/replay rules**.

Anything outside this boundary (UI renderers, lab logic, indexing, search, metrics, embeddings, RDF exports, etc.) is a **projection** or **integration** and must not redefine canonical truth.

## Canonical Truth

GraphOS has exactly one source of truth:

**The canonical operation log (GraphOps log) is authoritative.**

All durable changes to the graph must be represented as GraphOps appended to the canonical log. “Current state” snapshots may exist, but only as **derived** materializations of the log.

## Determinism

Applying a sequence of GraphOps to an initial empty state must deterministically produce the same canonical graph state.

Practically: **all entropy must live inside ops** (IDs, timestamps if used, seeds if randomness matters). Replay must never depend on “now,” hidden randomness, unordered iteration, or environment-specific side effects.

## Ops-Only Mutation

No subsystem (UI, labs, agents, services) is allowed to mutate canonical graph state directly.

The only legal write-path is:

**propose ops → validate → apply → append to log → return updated state/diff**

If you need a “fast path,” it must still end as GraphOps.

## Invariants

The kernel enforces “physics invariants” that prevent corrupted state.

At minimum:

* IDs are unique and well-formed.
* Edges cannot point to missing nodes.
* Ops must be valid for the current graph version (no silent conflicts).
* Canonical state must remain internally consistent after every commit.

Higher-level meaning rules (schemas, allowed edge types between node kinds, required fields, etc.) belong to the **vocabulary layer** and are versioned, not ad hoc.

## Identity

Every entity has a stable internal identity:

* **Internal ID**: opaque, immutable, globally unique within a workspace graph.
* **External identity (optional)**: semantic identifiers or references used for integration, merging, RDF mapping, or cross-workspace linking.

Internal IDs are never reused. External identity is allowed to evolve, be missing, or be refined over time.

## Properties and Vocabulary

The kernel supports flexible properties, but **prevents semantic chaos** by requiring a vocabulary discipline:

* Node/edge “kinds” and edge “types” come from a registry (even if permissive early).
* The vocabulary may start loose, but must be able to harden over time via versioned definitions.
* Agents may propose new vocabulary entries, but vocabulary changes are explicit operations, not implicit drift.

## Granularity Policy

GraphOps represent **meaningful intent**, not raw UI telemetry.

Layout/view changes may be persisted, but should be committed as coarse “end-of-interaction” ops (e.g., drag-end), not pixel-by-pixel streaming. Canonical history should remain readable and replayable at scale.

## Projections, Caches, and Derived Systems

Anything that can be regenerated from canonical state is a **projection** (or cache) and is never allowed to become a second truth.

Examples: materialized snapshots, search indices, RAG vector indices, RDF exports, metrics, thumbnails, UI caches.

If a projection disagrees with canonical state, the projection is wrong and must be rebuilt.

## Concurrency and Ordering

The canonical log defines a single total order of committed ops (e.g., monotonically increasing sequence numbers).

Concurrency is resolved explicitly via version checks and rebase/retry, not via silent last-write-wins behavior that would undermine determinism.

## Compatibility Commitments

GraphOS is designed LPG-first but must remain compatible with future “hardened semantics”:

* RDF/ontology and rule/inference layers may be added as projections or overlays.
* RAG may index graph slices and artifacts, but retrieval must map back to canonical IDs.
* Export/import must preserve identity and meaning to the extent possible.

These additions must never weaken kernel determinism or canonical truth.

## Testing and Non-Regression

Kernel behavior is treated as load-bearing infrastructure.

Every new op type or invariant requires tests that prove:

* deterministic replay
* invariant preservation
* canonical serialization stability (where applicable)
* conflict handling (version checks)

Breaking kernel contracts requires an explicit versioned migration plan.
